BASE_DOCKER_COMPOSE = -f docker/dev.docker-compose.yml -f docker/docker-compose.override.yml
CPU_DOCKER_COMPOSE = -f docker/dev.docker-compose.yml -f docker/docker-compose.override.yml -f docker/dev.docker-compose.cpu.yml
ENV_FILE = ./.docker.env
LOCAL_ENV_FILE =  ./.env

.PHONY: create_env
create_env: ## Just touching env files
	touch $(ENV_FILE)
	touch $(LOCAL_ENV_FILE)

.PHONY: up
up: create_env ## up services
	@docker compose $(if $(profile),--profile $(profile)) --env-file $(ENV_FILE) $(BASE_DOCKER_COMPOSE) up $(service) -d

.PHONY: logs
logs: create_env ## tail logs services
	@docker compose --env-file $(ENV_FILE) $(BASE_DOCKER_COMPOSE) logs $(service) -f

.PHONY: down
down: create_env ## down services
	@docker compose --env-file $(ENV_FILE) $(BASE_DOCKER_COMPOSE) down $(service)

.PHONY: build
build: create_env ## build services
	@docker compose --env-file $(ENV_FILE) $(BASE_DOCKER_COMPOSE) build --no-cache $(service)

.PHONY: stats
stats: create_env ## stats services
	@docker compose --env-file $(ENV_FILE) $(BASE_DOCKER_COMPOSE) stats $(service)

.PHONY: restart
restart: create_env down up ## restart services

.PHONY: up-cpu
up-cpu: create_env ## up services (CPU, без GPU)
	@docker compose $(if $(profile),--profile $(profile)) --env-file $(ENV_FILE) $(CPU_DOCKER_COMPOSE) up $(service) -d

.PHONY: down-cpu
down-cpu: create_env ## down services (CPU)
	@docker compose --env-file $(ENV_FILE) $(CPU_DOCKER_COMPOSE) down $(service)

.PHONY: logs-cpu
logs-cpu: create_env ## tail logs (CPU)
	@docker compose --env-file $(ENV_FILE) $(CPU_DOCKER_COMPOSE) logs $(service) -f

.PHONY: build-cpu
build-cpu: create_env ## build services (CPU)
	@docker compose --env-file $(ENV_FILE) $(CPU_DOCKER_COMPOSE) build --no-cache $(service)

.PHONY: restart-cpu
restart-cpu: create_env down-cpu up-cpu ## restart services (CPU)

.PHONY: uninstall
uninstall: ## uninstall all services
	@docker compose --env-file $(ENV_FILE) $(BASE_DOCKER_COMPOSE) down --remove-orphans --volumes $(service)

.PHONY: config
config: create_env ## show config services
	@docker compose --env-file $(ENV_FILE) $(BASE_DOCKER_COMPOSE) config $(service)

.PHONY: help
help: ## Help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
