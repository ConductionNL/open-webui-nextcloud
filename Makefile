# Open WebUI Nextcloud ExApp - Build System

REGISTRY ?= ghcr.io/conductionnl
IMAGE_NAME ?= open-webui-nextcloud
VERSION ?= 1.0.0

.PHONY: build push run test clean help

help:
	@echo "Open WebUI Nextcloud ExApp"
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
		-e NEXTCLOUD_URL=http://host.docker.internal:8080 \
		-e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
		-p 9000:9000 \
		-p 8081:8080 \
		$(REGISTRY)/$(IMAGE_NAME):latest

test:
	@echo "Testing heartbeat endpoint..."
	@curl -s http://localhost:9000/heartbeat || echo "Container not running"
	@echo ""
	@echo "Testing Open WebUI health..."
	@curl -s http://localhost:9000/health || echo "Open WebUI not running"

clean:
	-docker rmi $(REGISTRY)/$(IMAGE_NAME):$(VERSION)
	-docker rmi $(REGISTRY)/$(IMAGE_NAME):latest
