.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help dev down logs test lint fmt types types-check health clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

dev: ## Build and start the full stack
	$(COMPOSE) up --build

down: ## Stop the stack and remove volumes
	$(COMPOSE) down -v

logs: ## Tail logs for all services
	$(COMPOSE) logs -f

test: ## Run api, cpm and web test suites
	$(COMPOSE) run --rm --no-deps api pytest -q tests ../shared/tests
	$(COMPOSE) run --rm --no-deps web npm run test -- --run

types: ## Regenerate the CPM JSON Schema and the TypeScript types from it
	$(COMPOSE) run --rm --no-deps api python -m cpm.export_schema ../schemas/cpm.schema.json
	$(COMPOSE) run --rm --no-deps web npm run gen:types

types-check: ## Fail if the schema or the generated TS is stale
	$(COMPOSE) run --rm --no-deps api python -m cpm.export_schema ../schemas/cpm.schema.json --check
	$(COMPOSE) run --rm --no-deps web npm run gen:types:check

# Paths are relative to the container WORKDIR (/srv/api) on purpose: Git Bash on
# Windows rewrites a leading /srv/... into C:/Program Files/Git/srv/... before
# docker ever sees it.
lint: types-check ## Lint api, worker and web, and verify generated files are current
	$(COMPOSE) run --rm --no-deps api ruff check . ../shared
	$(COMPOSE) run --rm --no-deps api ruff format --check . ../shared
	$(COMPOSE) run --rm --no-deps worker ruff check .
	$(COMPOSE) run --rm --no-deps worker ruff format --check .
	$(COMPOSE) run --rm --no-deps web npm run lint

fmt: ## Auto-format Python sources
	$(COMPOSE) run --rm --no-deps api ruff format . ../shared
	$(COMPOSE) run --rm --no-deps api ruff check --fix . ../shared
	$(COMPOSE) run --rm --no-deps worker ruff format .
	$(COMPOSE) run --rm --no-deps worker ruff check --fix .

health: ## Print the API dependency health report
	@curl -s http://localhost:8000/health | python -m json.tool

clean: ## Remove build artefacts and caches
	$(COMPOSE) down -v --remove-orphans
	docker image prune -f
