"""
Open WebUI ExApp - Nextcloud External Application wrapper for Open WebUI chat interface.

This module provides the lifecycle endpoints required by Nextcloud's AppAPI
to manage the Open WebUI container as an external application.
"""

import os
import json
import time
import subprocess
import threading
import secrets
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse


# Configuration from environment
APP_ID = os.environ.get("APP_ID", "open_webui")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
APP_SECRET = os.environ.get("APP_SECRET", "")
APP_HOST = os.environ.get("APP_HOST", "0.0.0.0")
APP_PORT = int(os.environ.get("APP_PORT", "9000"))
NEXTCLOUD_URL = os.environ.get("NEXTCLOUD_URL", "http://nextcloud")

# Open WebUI configuration
WEBUI_PORT = 8080
WEBUI_PROCESS = None
INIT_PROGRESS = 0


def get_nc_headers() -> dict:
    """Get headers for Nextcloud API calls."""
    import base64
    auth = base64.b64encode(f":{APP_SECRET}".encode()).decode()
    return {
        "EX-APP-ID": APP_ID,
        "EX-APP-VERSION": APP_VERSION,
        "AUTHORIZATION-APP-API": auth,
    }


async def report_status(progress: int):
    """Report initialization progress to Nextcloud."""
    global INIT_PROGRESS
    INIT_PROGRESS = progress
    try:
        async with httpx.AsyncClient() as client:
            await client.put(
                f"{NEXTCLOUD_URL}/ocs/v1.php/apps/app_api/apps/status",
                headers=get_nc_headers(),
                json={"progress": progress},
                timeout=10,
            )
    except Exception as e:
        print(f"Failed to report status: {e}")


async def detect_ollama_url() -> str:
    """Try to detect Ollama ExApp URL."""
    # Check if explicitly set
    if os.environ.get("OLLAMA_BASE_URL"):
        return os.environ["OLLAMA_BASE_URL"]

    # Try to find Ollama ExApp via Nextcloud API
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{NEXTCLOUD_URL}/ocs/v1.php/apps/app_api/apps",
                headers=get_nc_headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                apps = resp.json().get("ocs", {}).get("data", [])
                for app in apps:
                    if app.get("id") == "ollama" and app.get("enabled"):
                        # Use the proxy URL
                        return f"{NEXTCLOUD_URL}/index.php/apps/app_api/proxy/ollama"
    except Exception as e:
        print(f"Failed to detect Ollama: {e}")

    # Default to common Docker network name
    return "http://ollama:11434"


def start_webui():
    """Start the Open WebUI server process."""
    global WEBUI_PROCESS

    env = os.environ.copy()

    # Configure Open WebUI
    env["PORT"] = str(WEBUI_PORT)
    env["HOST"] = "0.0.0.0"

    # Use persistent storage
    storage_path = env.get("APP_PERSISTENT_STORAGE", "/data")
    env["DATA_DIR"] = storage_path
    os.makedirs(storage_path, exist_ok=True)

    # Disable signup by default (use Nextcloud auth)
    env.setdefault("ENABLE_SIGNUP", "false")

    # Disable telemetry
    env["SCARF_NO_ANALYTICS"] = "true"
    env["DO_NOT_TRACK"] = "true"

    # Secret key for sessions
    if not env.get("WEBUI_SECRET_KEY"):
        key_file = f"{storage_path}/.secret_key"
        if os.path.exists(key_file):
            with open(key_file, "r") as f:
                env["WEBUI_SECRET_KEY"] = f.read().strip()
        else:
            env["WEBUI_SECRET_KEY"] = secrets.token_hex(32)
            with open(key_file, "w") as f:
                f.write(env["WEBUI_SECRET_KEY"])

    # Start Open WebUI using uvicorn (the same way start.sh does)
    WEBUI_PROCESS = subprocess.Popen(
        [
            "python3", "-m", "uvicorn", "open_webui.main:app",
            "--host", "0.0.0.0",
            "--port", str(WEBUI_PORT),
            "--forwarded-allow-ips", "*"
        ],
        env=env,
        cwd="/app/backend",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Log output in background
    def log_output():
        for line in WEBUI_PROCESS.stdout:
            print(f"[webui] {line.decode().strip()}")

    threading.Thread(target=log_output, daemon=True).start()


async def wait_for_webui(timeout: int = 90) -> bool:
    """Wait for Open WebUI to become healthy."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://localhost:{WEBUI_PORT}/health", timeout=5)
                if resp.status_code == 200:
                    return True
        except Exception:
            pass
        await report_status(int((time.time() - start) / timeout * 90))
        time.sleep(2)
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    print(f"Starting Open WebUI ExApp v{APP_VERSION}")
    yield
    # Cleanup
    if WEBUI_PROCESS:
        WEBUI_PROCESS.terminate()
        WEBUI_PROCESS.wait(timeout=10)


app = FastAPI(lifespan=lifespan)


@app.get("/heartbeat")
async def heartbeat():
    """Health check endpoint required by AppAPI."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://localhost:{WEBUI_PORT}/health", timeout=5)
            if resp.status_code == 200:
                return JSONResponse({"status": "ok"})
    except Exception:
        pass
    return JSONResponse({"status": "error"}, status_code=503)


@app.post("/init")
async def init(background_tasks: BackgroundTasks):
    """Initialization endpoint required by AppAPI."""

    async def do_init():
        await report_status(0)

        # Detect Ollama URL
        ollama_url = await detect_ollama_url()
        os.environ["OLLAMA_BASE_URL"] = ollama_url
        print(f"Using Ollama URL: {ollama_url}")
        await report_status(10)

        # Start Open WebUI
        start_webui()
        await report_status(20)

        # Wait for WebUI to be ready
        if await wait_for_webui():
            await report_status(100)
            print("Open WebUI initialization complete")
        else:
            print("Open WebUI failed to start within timeout")

    background_tasks.add_task(do_init)
    return JSONResponse({"status": "init_started"})


@app.put("/enabled")
async def enabled(request: Request):
    """Enable/disable endpoint required by AppAPI."""
    data = await request.json()
    is_enabled = data.get("enabled", False)

    if is_enabled:
        if not WEBUI_PROCESS or WEBUI_PROCESS.poll() is not None:
            start_webui()
    else:
        if WEBUI_PROCESS and WEBUI_PROCESS.poll() is None:
            WEBUI_PROCESS.terminate()

    return JSONResponse({"status": "ok"})


# Proxy all other requests to Open WebUI
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy(request: Request, path: str):
    """Proxy requests to Open WebUI."""
    try:
        url = f"http://localhost:{WEBUI_PORT}/{path}"
        body = await request.body()

        headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ("host", "connection", "transfer-encoding")
        }

        # Inject Nextcloud user info if available
        nc_user = request.headers.get("NC-USER-ID")
        if nc_user:
            headers["X-User-Id"] = nc_user

        async with httpx.AsyncClient() as client:
            # Check for streaming endpoints
            is_streaming = path.startswith("api/chat") or "stream" in request.query_params

            if is_streaming and request.method == "POST":
                # Handle streaming responses
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
                # Regular request
                resp = await client.request(
                    method=request.method,
                    url=url,
                    content=body,
                    headers=headers,
                    params=request.query_params,
                    timeout=300,
                )

                # Filter response headers
                response_headers = {
                    k: v for k, v in resp.headers.items()
                    if k.lower() not in ("transfer-encoding", "content-encoding")
                }

                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    headers=response_headers,
                )
    except Exception as e:
        return JSONResponse(
            {"error": str(e)},
            status_code=502,
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)
