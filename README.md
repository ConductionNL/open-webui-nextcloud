# Open WebUI Nextcloud ExApp

A Nextcloud External Application (ExApp) that integrates [Open WebUI](https://openwebui.com) - a feature-rich chat interface for LLMs - directly into Nextcloud.

## Features

- **Beautiful Chat Interface** - Modern, intuitive UI for interacting with AI
- **Multiple Model Support** - Connect to Ollama, OpenAI, or any compatible API
- **Conversation History** - Persistent chat history with search
- **Document Upload** - RAG capabilities with file uploads
- **Multi-user Support** - Each Nextcloud user gets their own workspace
- **Mobile Friendly** - Responsive design works on all devices

## Requirements

- Nextcloud 30 or higher
- [AppAPI](https://apps.nextcloud.com/apps/app_api) installed and configured
- Docker with a configured Deploy Daemon (HaRP recommended)
- [Ollama ExApp](https://github.com/ConductionNL/ollama-nextcloud) (recommended) or external LLM API

## Installation

### Via Nextcloud App Store

1. Install and enable the **AppAPI** app in Nextcloud
2. Configure a Deploy Daemon
3. Install the **Ollama ExApp** first (recommended)
4. Search for "Open WebUI" in the External Apps section
5. Click Install

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
| `OLLAMA_BASE_URL` | URL to Ollama API | Auto-detect from Ollama ExApp |
| `OPENAI_API_BASE_URL` | OpenAI-compatible API URL | Not set |
| `OPENAI_API_KEY` | API key for OpenAI endpoint | Not set |
| `ENABLE_SIGNUP` | Allow user registration | false |

## Usage

After installation, access Open WebUI through Nextcloud:

```
https://your-nextcloud/index.php/apps/app_api/proxy/open_webui
```

Or use the External Apps section in Nextcloud's admin panel.

### First Time Setup

1. Open the WebUI through Nextcloud
2. Create an admin account (first user becomes admin)
3. Configure your LLM backend in Settings
4. Start chatting!

### Connecting to Ollama

If you have the Ollama ExApp installed, Open WebUI will automatically detect and connect to it. No manual configuration needed.

### Connecting to External APIs

To use OpenAI or other compatible APIs:

1. Go to Settings in Open WebUI
2. Add your API endpoint and key
3. Select your preferred model

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
    -e NEXTCLOUD_URL=http://localhost:8080 \
    -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
    -p 9000:9000 \
    -p 8080:8080 \
    open-webui-exapp:dev
```

### Testing Endpoints

```bash
# Health check
curl http://localhost:9000/heartbeat

# Open WebUI health
curl http://localhost:9000/health
```

## Architecture

```
┌─────────────────────────────────────┐
│         Nextcloud + AppAPI          │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│   Open WebUI ExApp Container        │
│  ┌───────────────────────────────┐  │
│  │  FastAPI Wrapper (port 9000)  │  │
│  │  - /heartbeat                 │  │
│  │  - /init                      │  │
│  │  - /enabled                   │  │
│  │  - /* (proxy to Open WebUI)   │  │
│  └───────────────┬───────────────┘  │
│                  │                  │
│  ┌───────────────▼───────────────┐  │
│  │  Open WebUI (port 8080)       │  │
│  │  ┌─────────────────────────┐  │  │
│  │  │   SQLite Database       │  │  │
│  │  │   /data/webui.db        │  │  │
│  │  └─────────────────────────┘  │  │
│  └───────────────────────────────┘  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│     Ollama ExApp (LLM Backend)      │
└─────────────────────────────────────┘
```

## Integration Stack

For the best experience, install all three ExApps:

1. **Ollama ExApp** - Local LLM inference
2. **Open WebUI ExApp** - Chat interface (this app)
3. **n8n ExApp** - Workflow automation with AI

## License

AGPL-3.0 - See [LICENSE](LICENSE) for details.

## Links

- [Open WebUI Documentation](https://docs.openwebui.com)
- [Open WebUI GitHub](https://github.com/open-webui/open-webui)
- [Nextcloud AppAPI Documentation](https://docs.nextcloud.com/server/stable/developer_manual/exapp_development/Introduction.html)
- [Conduction](https://conduction.nl)
