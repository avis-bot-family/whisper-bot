# Docker Compose: docker/dev.docker-compose.yml
COMPOSE_FILE = docker/dev.docker-compose.yml

.PHONY: ollama-up ollama-down ollama-pull ollama-logs up down logs

up:
	docker compose -f $(COMPOSE_FILE) up -d

down:
	docker compose -f $(COMPOSE_FILE) down

logs:
	docker compose -f $(COMPOSE_FILE) logs -f

ollama-up:
	docker compose -f $(COMPOSE_FILE) up -d ollama

ollama-down:
	docker compose -f $(COMPOSE_FILE) stop ollama

ollama-pull:
	docker compose -f $(COMPOSE_FILE) exec ollama ollama pull llama3.2

ollama-logs:
	docker compose -f $(COMPOSE_FILE) logs -f ollama
