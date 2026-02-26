# Docker Compose: docker/dev.docker-compose.yml
COMPOSE_FILE = docker/dev.docker-compose.yml
ENV_FILE = ./.docker.env
LOCAL_ENV_FILE =  ./.env

.PHONY: ollama-up ollama-down ollama-pull ollama-logs up down logs

.PHONY: create_env
create_env: ## Just touching env files
	touch $(ENV_FILE)
	touch $(LOCAL_ENV_FILE)

up:
	docker compose -f $(COMPOSE_FILE) up -d

down:
	docker compose -f $(COMPOSE_FILE) down

.PHONY: restart
restart: create_env down up ## restart services

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
