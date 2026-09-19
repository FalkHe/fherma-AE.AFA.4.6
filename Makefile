# Development shortcuts. Everything runs inside Docker — no host Node/Python
# toolchain is required. Test/lint targets use the one-off CLI services
# (app-cli, node-cli in compose.yaml), so they work even when the stack is
# down. Run `make build` after dependency changes so the images stay fresh.

COMPOSE := docker compose
# The CLI services sit behind the `cli` profile so `up` never starts them,
# but `build` must include them explicitly.
COMPOSE_ALL := $(COMPOSE) --profile cli
RUN_BACKEND := $(COMPOSE) run --rm --no-deps app-cli
RUN_NODE := $(COMPOSE) run --rm --no-deps node-cli

.DEFAULT_GOAL := help

help: ## List available targets
	@grep -E '^[a-z][a-zA-Z-]*:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-20s %s\n", $$1, $$2}'
.PHONY: help

up: ## Start the full dev environment (detached)
	$(COMPOSE) up -d
.PHONY: up

down: ## Stop and remove all services
	$(COMPOSE) down
.PHONY: down

build: ## Build all Docker images, including the CLI services
	$(COMPOSE_ALL) build
.PHONY: build

rebuild: build ## Build images, then recreate the stack (renews the frontend node_modules volume — needed after dependency changes)
	$(COMPOSE) up -d --force-recreate --renew-anon-volumes
.PHONY: rebuild

logs: ## Follow logs of all services
	$(COMPOSE) logs -f
.PHONY: logs

ps: ## Show service status
	$(COMPOSE) ps
.PHONY: ps

# The Langfuse stack lives in compose.langfuse.yaml and is enabled by adding
# that file to COMPOSE_FILE in .env (see .env.dist); these targets error with
# "no such service" when it is not enabled.
langfuse-up: ## Start the optional Langfuse tracing stack (needs compose.langfuse.yaml in COMPOSE_FILE)
	$(COMPOSE) up -d langfuse-web langfuse-worker
.PHONY: langfuse-up

langfuse-down: ## Stop the optional Langfuse tracing stack (leaves the app stack running)
	# Never `down` here -- it is not service-scoped: it tears down the whole
	# project, and with -v it deletes postgres-data (the entire dev database).
	# `stop` with explicit names touches only the Langfuse services.
	$(COMPOSE) stop langfuse-web langfuse-worker clickhouse valkey minio langfuse-postgres
.PHONY: langfuse-down

test: backend-test frontend-test ## Run both test suites
.PHONY: test

backend-test: ## Run backend pytest suite, engine-free (app-cli service)
	# `-m "not database"` deselects rather than relying on the database tests
	# skipping: they skip only when no Postgres *answers*, so with the dev
	# stack up they would run here, against no scratch database.
	$(RUN_BACKEND) pytest -m "not database"
.PHONY: backend-test

backend-test-db: ## Run the database-backed backend pytest suite (starts postgres, app-cli joins its network)
	$(COMPOSE) up -d postgres
	$(COMPOSE) run --rm app-cli pytest -m database
.PHONY: backend-test-db

frontend-test: ## Run frontend Vitest suite (node-cli service)
	$(RUN_NODE) pnpm test
.PHONY: frontend-test

lint: backend-lint frontend-lint frontend-typecheck ## Run all lint and type checks
.PHONY: lint

backend-lint: ## Ruff lint + format check (app-cli service)
	$(RUN_BACKEND) ruff check .
	$(RUN_BACKEND) ruff format --check .
.PHONY: backend-lint

frontend-lint: ## ESLint (node-cli service)
	$(RUN_NODE) pnpm lint
.PHONY: frontend-lint

frontend-typecheck: ## TypeScript check (node-cli service)
	$(RUN_NODE) pnpm typecheck
.PHONY: frontend-typecheck

backend-cli: ## Open a bash shell in a one-off backend CLI container
	$(COMPOSE) run --rm app-cli bash
.PHONY: backend-cli

frontend-cli: ## Open a bash shell in a one-off node CLI container
	$(COMPOSE) run --rm node-cli bash
.PHONY: frontend-cli

generate-api: ## Regenerate the frontend's typed API client (stack must be up)
	$(COMPOSE) exec -T app-web app openapi export > frontend/openapi.json
	$(RUN_NODE) pnpm exec openapi-typescript openapi.json -o src/api/schema.d.ts
.PHONY: generate-api
