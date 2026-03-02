"""Open WebUI ExApp - Nextcloud External Application with built-in Ollama LLM inference."""

import asyncio
import logging
import os
import secrets
import subprocess
import threading
import typing
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from nc_py_api import NextcloudApp
from nc_py_api.ex_app import (
    nc_app,
    persistent_storage,
    run_app,
    setup_nextcloud_logging,
)
from nc_py_api.ex_app.integration_fastapi import AppAPIAuthMiddleware


# ── Logging ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="[%(funcName)s]: %(message)s",
    datefmt="%H:%M:%S",
)
LOGGER = logging.getLogger("open_webui")
LOGGER.setLevel(logging.DEBUG)


# ── Configuration ───────────────────────────────────────────────────
OLLAMA_PORT = 11434
OLLAMA_URL = f"http://localhost:{OLLAMA_PORT}"
WEBUI_PORT = 8080
WEBUI_URL = f"http://localhost:{WEBUI_PORT}"

OLLAMA_PROCESS = None
WEBUI_PROCESS = None

# Detect HaRP mode and set proxy prefix accordingly
APP_ID = os.environ.get("APP_ID", "open_webui")
HARP_ENABLED = bool(os.environ.get("HP_SHARED_KEY"))
if HARP_ENABLED:
    PROXY_PREFIX = f"/exapps/{APP_ID}"
else:
    PROXY_PREFIX = f"/index.php/apps/app_api/proxy/{APP_ID}"


# ── Ollama Process Management ────────────────────────────────────────
def start_ollama():
    """Start the Ollama server process."""
    global OLLAMA_PROCESS

    if OLLAMA_PROCESS is not None and OLLAMA_PROCESS.poll() is None:
        return

    env = os.environ.copy()
    storage_path = persistent_storage()

    # Ollama configuration
    env["OLLAMA_HOST"] = f"0.0.0.0:{OLLAMA_PORT}"
    env["OLLAMA_MODELS"] = os.path.join(storage_path, "ollama_models")
    os.makedirs(env["OLLAMA_MODELS"], exist_ok=True)

    # Performance tuning from env vars
    if os.environ.get("OLLAMA_NUM_PARALLEL"):
        env["OLLAMA_NUM_PARALLEL"] = os.environ["OLLAMA_NUM_PARALLEL"]
    if os.environ.get("OLLAMA_MAX_LOADED_MODELS"):
        env["OLLAMA_MAX_LOADED_MODELS"] = os.environ["OLLAMA_MAX_LOADED_MODELS"]
    if os.environ.get("OLLAMA_KEEP_ALIVE"):
        env["OLLAMA_KEEP_ALIVE"] = os.environ["OLLAMA_KEEP_ALIVE"]
    if os.environ.get("OLLAMA_FLASH_ATTENTION"):
        env["OLLAMA_FLASH_ATTENTION"] = os.environ["OLLAMA_FLASH_ATTENTION"]

    OLLAMA_PROCESS = subprocess.Popen(
        ["ollama", "serve"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    def log_output():
        for line in OLLAMA_PROCESS.stdout:
            LOGGER.info("[ollama] %s", line.decode().strip())

    threading.Thread(target=log_output, daemon=True).start()
    LOGGER.info("Ollama started with PID: %d", OLLAMA_PROCESS.pid)


def stop_ollama():
    """Stop the Ollama server process."""
    global OLLAMA_PROCESS
    if OLLAMA_PROCESS is not None:
        OLLAMA_PROCESS.terminate()
        try:
            OLLAMA_PROCESS.wait(timeout=30)
        except subprocess.TimeoutExpired:
            OLLAMA_PROCESS.kill()
        OLLAMA_PROCESS = None
        LOGGER.info("Ollama stopped")


async def wait_for_ollama(timeout: int = 60) -> bool:
    """Wait for Ollama to become healthy."""
    for _ in range(timeout):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{OLLAMA_URL}/api/tags", timeout=5)
                if resp.status_code == 200:
                    return True
        except Exception:
            pass
        await asyncio.sleep(1)
    return False


async def pull_default_model():
    """Pull the default model if OLLAMA_DEFAULT_MODEL is configured."""
    model = os.environ.get("OLLAMA_DEFAULT_MODEL")
    if not model:
        LOGGER.info("No OLLAMA_DEFAULT_MODEL configured, skipping model pull")
        return

    # Check if model already exists
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags", timeout=10)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                for m in models:
                    if m.get("name", "").startswith(model):
                        LOGGER.info("Model %s already available", model)
                        return
    except Exception:
        pass

    LOGGER.info("Pulling default model: %s (this may take a while)...", model)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/pull",
                json={"name": model, "stream": False},
            )
            if resp.status_code == 200:
                LOGGER.info("Model %s pulled successfully", model)
            else:
                LOGGER.error("Failed to pull model %s: %s", model, resp.text)
    except Exception as e:
        LOGGER.error("Error pulling model %s: %s", model, e)


# ── Open WebUI Process Management ────────────────────────────────────
def start_webui():
    """Start the Open WebUI server process."""
    global WEBUI_PROCESS

    if WEBUI_PROCESS is not None and WEBUI_PROCESS.poll() is None:
        return

    env = os.environ.copy()
    storage_path = persistent_storage()

    # Configure Open WebUI
    env["PORT"] = str(WEBUI_PORT)
    env["HOST"] = "0.0.0.0"
    env["DATA_DIR"] = storage_path
    os.makedirs(storage_path, exist_ok=True)

    # Point Open WebUI to local Ollama
    env["OLLAMA_BASE_URL"] = OLLAMA_URL

    # Disable signup by default (use Nextcloud auth)
    env.setdefault("ENABLE_SIGNUP", "false")

    # Disable telemetry
    env["SCARF_NO_ANALYTICS"] = "true"
    env["DO_NOT_TRACK"] = "true"

    # Secret key for sessions
    if not env.get("WEBUI_SECRET_KEY"):
        key_file = os.path.join(storage_path, ".webui_secret_key")
        if os.path.exists(key_file):
            with open(key_file, "r") as f:
                env["WEBUI_SECRET_KEY"] = f.read().strip()
        else:
            env["WEBUI_SECRET_KEY"] = secrets.token_hex(32)
            with open(key_file, "w") as f:
                f.write(env["WEBUI_SECRET_KEY"])

    WEBUI_PROCESS = subprocess.Popen(
        [
            "python3", "-m", "uvicorn", "open_webui.main:app",
            "--host", "0.0.0.0",
            "--port", str(WEBUI_PORT),
            "--forwarded-allow-ips", "*",
        ],
        env=env,
        cwd="/app/backend",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    def log_output():
        for line in WEBUI_PROCESS.stdout:
            LOGGER.info("[webui] %s", line.decode().strip())

    threading.Thread(target=log_output, daemon=True).start()
    LOGGER.info("Open WebUI started with PID: %d", WEBUI_PROCESS.pid)


def stop_webui():
    """Stop the Open WebUI server process."""
    global WEBUI_PROCESS
    if WEBUI_PROCESS is not None:
        WEBUI_PROCESS.terminate()
        try:
            WEBUI_PROCESS.wait(timeout=30)
        except subprocess.TimeoutExpired:
            WEBUI_PROCESS.kill()
        WEBUI_PROCESS = None
        LOGGER.info("Open WebUI stopped")


async def wait_for_webui(timeout: int = 120) -> bool:
    """Wait for Open WebUI to become healthy."""
    for _ in range(timeout):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{WEBUI_URL}/health", timeout=5)
                if resp.status_code == 200:
                    return True
        except Exception:
            pass
        await asyncio.sleep(1)
    return False


# ── Lifespan ────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_nextcloud_logging("open_webui", logging_level=logging.WARNING)
    LOGGER.info("Starting Open WebUI ExApp")
    start_ollama()
    start_webui()
    yield
    stop_webui()
    stop_ollama()
    LOGGER.info("Open WebUI ExApp shutdown complete")


# ── FastAPI App ─────────────────────────────────────────────────────
APP = FastAPI(lifespan=lifespan)
APP.add_middleware(AppAPIAuthMiddleware)


# ── Inline iframe loader JS ────────────────────────────────────────
IFRAME_LOADER_JS = f"""
(function() {{
    var style = document.createElement('style');
    style.textContent =
        '#content.app-app_api {{' +
        '  margin-top: var(--header-height) !important;' +
        '  height: var(--body-height) !important;' +
        '  width: calc(100% - var(--body-container-margin) * 2) !important;' +
        '  border-radius: var(--body-container-radius) !important;' +
        '  overflow: hidden !important;' +
        '  padding: 0 !important;' +
        '}}' +
        '#content.app-app_api > iframe {{ width: 100%; height: 100%; border: none; display: block; }}';
    document.head.appendChild(style);

    function setup() {{
        var content = document.getElementById('content');
        if (!content) return;
        content.innerHTML = '';
        var iframe = document.createElement('iframe');
        iframe.src = '{PROXY_PREFIX}/';
        iframe.allow = 'clipboard-read; clipboard-write';
        content.appendChild(iframe);
    }}

    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', setup);
    }} else {{
        setup();
    }}
}})();
""".strip()


@APP.get("/js/open-webui-iframe-loader.js")
async def iframe_loader():
    """Serve the inline iframe loader script."""
    return Response(
        content=IFRAME_LOADER_JS,
        media_type="application/javascript",
    )


# ── Enabled Handler ────────────────────────────────────────────────
def enabled_handler(enabled: bool, nc: NextcloudApp) -> str:
    """Handle app enable/disable events."""
    if enabled:
        LOGGER.info("Enabling Open WebUI ExApp")
        nc.ui.resources.set_script(
            "top_menu", "open_webui", "js/open-webui-iframe-loader"
        )
        nc.ui.top_menu.register(
            "open_webui", "Open WebUI", "ex_app/img/app.svg", True
        )
        start_ollama()
        start_webui()
    else:
        LOGGER.info("Disabling Open WebUI ExApp")
        nc.ui.resources.delete_script(
            "top_menu", "open_webui", "js/open-webui-iframe-loader"
        )
        nc.ui.top_menu.unregister("open_webui")
        stop_webui()
        stop_ollama()
    return ""


# ── Required Endpoints ──────────────────────────────────────────────
@APP.get("/heartbeat")
async def heartbeat_callback():
    """Heartbeat endpoint for AppAPI health checks."""
    return JSONResponse(content={"status": "ok"})


@APP.post("/init")
async def init_callback(
    b_tasks: BackgroundTasks,
    nc: typing.Annotated[NextcloudApp, Depends(nc_app)],
):
    """Initialization endpoint called by AppAPI after installation."""
    b_tasks.add_task(init_task, nc)
    return JSONResponse(content={})


@APP.put("/enabled")
def enabled_callback(
    enabled: bool,
    nc: typing.Annotated[NextcloudApp, Depends(nc_app)],
):
    """Enable/disable callback from AppAPI."""
    return JSONResponse(content={"error": enabled_handler(enabled, nc)})


async def init_task(nc: NextcloudApp):
    """Background task for initialization with progress reporting."""
    nc.set_init_status(0)
    LOGGER.info("Starting initialization...")

    # Start Ollama
    start_ollama()
    nc.set_init_status(10)

    # Wait for Ollama
    if await wait_for_ollama():
        LOGGER.info("Ollama is ready")
        nc.set_init_status(20)
    else:
        LOGGER.error("Ollama failed to start within timeout")

    # Pull default model in background (don't block init)
    asyncio.create_task(pull_default_model())
    nc.set_init_status(30)

    # Start Open WebUI
    start_webui()
    nc.set_init_status(40)

    # Wait for Open WebUI
    if await wait_for_webui():
        nc.set_init_status(80)
        LOGGER.info("Open WebUI is ready")

        # Register UI elements
        nc.ui.resources.set_script(
            "top_menu", "open_webui", "js/open-webui-iframe-loader"
        )
        nc.ui.top_menu.register(
            "open_webui", "Open WebUI", "ex_app/img/app.svg", True
        )
        nc.set_init_status(100)
        LOGGER.info("Initialization complete")
    else:
        LOGGER.error("Open WebUI failed to start within timeout")


# ── Ollama API Proxy ────────────────────────────────────────────────
@APP.api_route(
    "/ollama/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
async def ollama_proxy(request: Request, path: str):
    """Proxy requests to Ollama API (for external consumers like n8n)."""
    try:
        url = f"{OLLAMA_URL}/{path}"
        body = await request.body()

        headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ("host", "connection", "transfer-encoding", "accept-encoding")
        }

        async with httpx.AsyncClient() as client:
            # Check for streaming Ollama requests
            is_streaming = False
            if request.method == "POST" and body:
                try:
                    import json
                    payload = json.loads(body)
                    is_streaming = payload.get("stream", True)
                except (json.JSONDecodeError, AttributeError):
                    pass

            if is_streaming and request.method == "POST":
                async def stream_response():
                    async with client.stream(
                        method=request.method,
                        url=url,
                        content=body,
                        headers=headers,
                        params=request.query_params,
                        timeout=600,
                    ) as resp:
                        async for chunk in resp.aiter_bytes():
                            yield chunk

                return StreamingResponse(
                    stream_response(),
                    media_type="application/x-ndjson",
                )
            else:
                resp = await client.request(
                    method=request.method,
                    url=url,
                    content=body,
                    headers=headers,
                    params=request.query_params,
                    timeout=300,
                )
                resp_headers = {
                    k: v for k, v in resp.headers.items()
                    if k.lower() not in ("transfer-encoding", "content-encoding", "content-length")
                }
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    headers=resp_headers,
                )
    except httpx.RequestError as e:
        LOGGER.error("Ollama proxy error: %s", str(e))
        return JSONResponse({"error": f"Ollama proxy error: {str(e)}"}, status_code=502)


# ── Catch-All Proxy (Open WebUI) ──────────────────────────────────
@APP.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
async def proxy(request: Request, path: str):
    """Proxy all other requests to Open WebUI."""
    # Serve ex_app static files (icons, JS) directly from disk
    if path.startswith("ex_app/"):
        file_path = Path(__file__).parent.parent.parent / path
        if file_path.is_file():
            from starlette.responses import FileResponse
            return FileResponse(str(file_path))

    try:
        url = f"{WEBUI_URL}/{path}"
        body = await request.body()

        headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ("host", "connection", "transfer-encoding", "accept-encoding")
        }

        # Inject Nextcloud user info if available
        nc_user = request.headers.get("NC-USER-ID")
        if nc_user:
            headers["X-User-Id"] = nc_user

        async with httpx.AsyncClient() as client:
            # Check for streaming chat endpoints
            is_streaming = path.startswith("api/chat") or "stream" in request.query_params

            if is_streaming and request.method == "POST":
                async def stream_response():
                    async with client.stream(
                        method=request.method,
                        url=url,
                        content=body,
                        headers=headers,
                        params=request.query_params,
                        timeout=600,
                    ) as resp:
                        async for chunk in resp.aiter_bytes():
                            yield chunk

                return StreamingResponse(
                    stream_response(),
                    media_type="text/event-stream",
                )
            else:
                resp = await client.request(
                    method=request.method,
                    url=url,
                    content=body,
                    headers=headers,
                    params=request.query_params,
                    timeout=300,
                )
                resp_headers = {
                    k: v for k, v in resp.headers.items()
                    if k.lower() not in ("transfer-encoding", "content-encoding", "content-length")
                }
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    headers=resp_headers,
                )
    except httpx.RequestError as e:
        LOGGER.error("Proxy error: %s", str(e))
        return JSONResponse({"error": f"Proxy error: {str(e)}"}, status_code=502)


# ── Entry Point ─────────────────────────────────────────────────────
if __name__ == "__main__":
    os.chdir(Path(__file__).parent)
    run_app(APP, log_level="info")
