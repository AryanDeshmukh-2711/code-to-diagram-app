.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help dev down logs test at1 chat1 lint fmt golden types types-check health clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

dev: ## Build and start the full stack
	$(COMPOSE) up --build

down: ## Stop the stack and remove volumes
	$(COMPOSE) down -v

logs: ## Tail logs for all services
	$(COMPOSE) logs -f

# Two invocations, not one: pytest picks rootdir from the common ancestor of
# its arguments, so a combined run lands on /srv and reads neither package's
# config — including asyncio_mode.
test: ## Run api, shared and web test suites
	$(COMPOSE) run --rm --no-deps api pytest -q tests
	$(COMPOSE) run --rm --no-deps api pytest -q ../shared/tests
	$(COMPOSE) run --rm --no-deps web npm run test -- --run

# AT-1 is the acceptance test, not a unit test: it needs the database, the
# queue, the worker and the diagram engines, so it runs against a live stack.
at1: ## Run acceptance test AT-1 end to end (SRS 10.1)
	$(COMPOSE) up -d postgres redis plantuml api worker
	@# Relative path on purpose: an absolute one gets mangled into a Windows
	@# path by MSYS before docker ever sees it.
	$(COMPOSE) exec -T api python ../repo/acceptance/at1.py

# CHAT-1 is AT-1's sibling for the chat-driven frontend (P-M6-12): the real
# HTTP surface, so it also needs the api container answering requests, not
# just able to run a script against the database directly.
chat1: ## Run acceptance test CHAT-1 end to end (P-M6)
	$(COMPOSE) up -d postgres redis plantuml api worker
	$(COMPOSE) exec -T api python ../repo/acceptance/chat1.py

golden: ## Regenerate the golden diagram sources, then review the diff
	$(COMPOSE) run --rm --no-deps api python ../shared/tests/regenerate_golden.py
	@git --no-pager diff --stat -- shared/tests/golden || true

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
