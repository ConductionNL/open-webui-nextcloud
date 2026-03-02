# Open WebUI + Ollama Nextcloud ExApp - Build System

REGISTRY ?= ghcr.io/conductionnl
IMAGE_NAME ?= open-webui-nextcloud
VERSION ?= 1.0.0

.PHONY: build push run test clean help

help:
	@echo "Open WebUI + Ollama Nextcloud ExApp"
	@echo ""
	@echo "Usage:"
	@echo "  make build    - Build Docker image"
	@echo "  make push     - Push to registry"
	@echo "  make run      - Run locally for testing"
	@echo "  make test     - Test endpoints"
	@echo "  make clean    - Remove local images"
	@echo ""
	@echo "Variables:"
	@echo "  REGISTRY=$(REGISTRY)"
	@echo "  VERSION=$(VERSION)"

build:
	docker build -t $(REGISTRY)/$(IMAGE_NAME):$(VERSION) -t $(REGISTRY)/$(IMAGE_NAME):latest .

push: build
	docker push $(REGISTRY)/$(IMAGE_NAME):$(VERSION)
	docker push $(REGISTRY)/$(IMAGE_NAME):latest

run:
	docker run -it --rm \
		-e APP_ID=open_webui \
		-e APP_SECRET=dev-secret \
		-e APP_HOST=0.0.0.0 \
		-e APP_PORT=23000 \
		-e APP_PERSISTENT_STORAGE=/data \
		-e NEXTCLOUD_URL=http://host.docker.internal:8080 \
		-e OLLAMA_DEFAULT_MODEL=llama3.2:1b \
		-p 23000:23000 \
		$(REGISTRY)/$(IMAGE_NAME):latest

test:
	@echo "Testing heartbeat endpoint..."
	@curl -s http://localhost:23000/heartbeat || echo "Container not running"
	@echo ""
	@echo "Testing Ollama API..."
	@curl -s http://localhost:23000/ollama/api/tags || echo "Ollama not running"

clean:
	-docker rmi $(REGISTRY)/$(IMAGE_NAME):$(VERSION)
	-docker rmi $(REGISTRY)/$(IMAGE_NAME):latest
