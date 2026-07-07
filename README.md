<p align="center">
  <img src="img/app-store.svg" alt="Open WebUI logo" width="80" height="80">
</p>

# Open WebUI + Ollama Nextcloud ExApp

A Nextcloud External Application (ExApp) that bundles [Open WebUI](https://openwebui.com) (chat interface) and [Ollama](https://ollama.com) (LLM inference) into a single container managed by Nextcloud's AppAPI.

## Features

- **All-in-one AI Chat** - Open WebUI frontend + Ollama backend in a single ExApp
- **Beautiful Chat Interface** - Modern, intuitive UI for interacting with AI
- **Local LLM Inference** - Run models locally with Ollama (no external API needed)
- **Auto Model Pull** - Automatically downloads a default model on first start
- **Conversation History** - Persistent chat history with search
- **Document Upload** - RAG capabilities with file uploads
- **Ollama API** - Expose Ollama API for other apps (e.g., n8n workflows)
- **Mobile Friendly** - Responsive design works on all devices

## Requirements

- Nextcloud 30 or higher
- [AppAPI](https://apps.nextcloud.com/apps/app_api) installed and configured
- Docker with a configured Deploy Daemon (HaRP recommended)
- Sufficient RAM (4GB minimum, 8GB+ recommended for larger models)
- GPU support optional but recommended for performance

## Installation

### Via Nextcloud App Store

1. Install and enable the **AppAPI** app in Nextcloud
2. Configure a Deploy Daemon
3. Search for "Open WebUI" in the External Apps section
4. Click Install

### Manual Installation

```bash
# Register the ExApp with Nextcloud
occ app_api:app:register \
    open_webui \
    <your-daemon-name> \
    --info-xml https://raw.githubusercontent.com/ConductionNL/open-webui-nextcloud/main/appinfo/info.xml \
    --force-scopes
```

## Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `OLLAMA_DEFAULT_MODEL` | Model to auto-pull on first start | Not set |
| `OLLAMA_NUM_PARALLEL` | Number of parallel Ollama requests | 1 |
| `OLLAMA_KEEP_ALIVE` | How long to keep models loaded | 5m |
| `OLLAMA_MAX_LOADED_MODELS` | Max models loaded simultaneously | 1 |
| `OLLAMA_FLASH_ATTENTION` | Enable flash attention | false |
| `OPENAI_API_BASE_URL` | Additional OpenAI-compatible API URL | Not set |
| `OPENAI_API_KEY` | API key for OpenAI endpoint | Not set |
| `ENABLE_SIGNUP` | Allow user registration | false |

### Recommended Models

| Model | Size | Best For |
|-------|------|----------|
| `llama3.2:1b` | ~1.3 GB | Quick responses, low resource usage |
| `llama3.2:3b` | ~2.0 GB | Good balance of speed and quality |
| `mistral:7b` | ~4.1 GB | High quality general purpose |
| `gemma2:9b` | ~5.4 GB | Strong reasoning and coding |

## Usage

After installation, Open WebUI appears as a top menu item in Nextcloud.

### Ollama API Access

Other ExApps (like n8n) can access the Ollama API through the proxy:

```
https://your-nextcloud/index.php/apps/app_api/proxy/open_webui/ollama/api/tags
https://your-nextcloud/index.php/apps/app_api/proxy/open_webui/ollama/api/generate
https://your-nextcloud/index.php/apps/app_api/proxy/open_webui/ollama/api/chat
```

Or connect directly from other containers on the same Docker network:

```
http://openregister-exapp-openwebui:11434
```

## Development

### Building the Docker Image

```bash
docker build -t open-webui-exapp:dev .
```

### Running Locally

```bash
docker run -it --rm \
    -e APP_ID=open_webui \
    -e APP_SECRET=dev-secret \
    -e APP_HOST=0.0.0.0 \
    -e APP_PORT=23000 \
    -e APP_PERSISTENT_STORAGE=/data \
    -e NEXTCLOUD_URL=http://localhost:8080 \
    -e OLLAMA_DEFAULT_MODEL=llama3.2:1b \
    -p 23000:23000 \
    open-webui-exapp:dev
```

### Testing Endpoints

```bash
# Health check
curl http://localhost:23000/heartbeat

# Ollama API (list models)
curl http://localhost:23000/ollama/api/tags
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│            Nextcloud + AppAPI                    │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│     Open WebUI ExApp Container                   │
│  ┌───────────────────────────────────────────┐  │
│  │  FastAPI Wrapper (port 23000)             │  │
│  │  - /heartbeat, /init, /enabled            │  │
│  │  - /ollama/* → Ollama API (port 11434)    │  │
│  │  - /* → Open WebUI (port 8080)            │  │
│  │  - AppAPIAuthMiddleware                   │  │
│  │  - Iframe loader JS                       │  │
│  └──────────┬──────────────┬─────────────────┘  │
│             │              │                     │
│  ┌──────────▼──────┐  ┌───▼─────────────────┐  │
│  │ Ollama (11434)  │  │ Open WebUI (8080)   │  │
│  │ LLM inference   │  │ Chat interface      │  │
│  │ Model storage   │  │ User management     │  │
│  └─────────────────┘  │ Conversation history│  │
│                        └─────────────────────┘  │
│                                                  │
│  /data/                                          │
│  ├── ollama_models/  (downloaded LLM models)     │
│  └── ...             (WebUI data, secrets)       │
└─────────────────────────────────────────────────┘
```

## Integration Stack

For the best experience, install both ExApps:

1. **Open WebUI ExApp** - AI chat + Ollama inference (this app)
2. **n8n ExApp** - Workflow automation with AI (can use Ollama from this app)

## License

EUPL-1.2 - See [LICENSE](LICENSE) for details.

## Links

- [Open WebUI Documentation](https://docs.openwebui.com)
- [Ollama Documentation](https://ollama.com)
- [Nextcloud AppAPI Documentation](https://docs.nextcloud.com/server/stable/developer_manual/exapp_development/Introduction.html)
- [Conduction](https://conduction.nl)
