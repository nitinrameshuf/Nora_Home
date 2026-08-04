# Nora Home — every routine operation is one word.
#
#     make up        bring the whole house up (first run included)
#     make deploy    pull, rebuild, migrate, restart — the update command
#     make logs      follow everything
#     make backup    full backup now
#     make app       install a new house app
#
# Ops should never take more than one of these.

.DEFAULT_GOAL := help
COMPOSE := docker compose
MANAGE := $(COMPOSE) run --rm web

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ── everyday ─────────────────────────────────────────────────────────────────
.PHONY: up
up: .env nginx/certs/nora-home.crt ## Start the house (builds on first run, migrates automatically)
	$(COMPOSE) up -d --build
	@echo "\nNora Home is coming up. Watch it with: make logs"
	@echo "Then open https://localhost:$${NORA_HOME_HTTPS_PORT:-443}/home/"
	@echo "(self-signed cert — your browser will warn once; see docs/deployment.html)"

.PHONY: down
down: ## Stop everything (data volumes are kept)
	$(COMPOSE) down

.PHONY: deploy
deploy: ## Update to the latest commit and restart cleanly
	git pull --ff-only
	$(COMPOSE) build
	$(COMPOSE) up -d
	@echo "Deployed. Migrations ran automatically."

.PHONY: restart
restart: ## Restart the app without touching the databases
	$(COMPOSE) restart web worker beat

.PHONY: logs
logs: ## Follow logs from the app services
	$(COMPOSE) logs -f web worker beat nginx

.PHONY: ps
ps: ## What is running
	$(COMPOSE) ps

# ── data ─────────────────────────────────────────────────────────────────────
.PHONY: backup
backup: ## Full backup (SQL + Mongo + media + portable fixtures)
	$(MANAGE) nora_backup --compress

.PHONY: restore
restore: ## Restore a backup: make restore FROM=/var/backups/nora/nora-....tar.gz
	@test -n "$(FROM)" || (echo "Set FROM=/path/to/backup"; exit 1)
	$(MANAGE) nora_restore "$(FROM)" --yes

.PHONY: migrate
migrate: ## Apply migrations by hand (normally automatic on start)
	$(MANAGE) migrate

.PHONY: makemigrations
makemigrations: ## Generate migrations for changed models
	$(MANAGE) makemigrations

# ── apps ─────────────────────────────────────────────────────────────────────
.PHONY: app
app: ## Install a house app: make app SRC=https://github.com/you/nora-workout
	@test -n "$(SRC)" || (echo "Set SRC=<git url or local path>"; exit 1)
	$(MANAGE) install_app "$(SRC)"
	$(COMPOSE) up -d --build

.PHONY: apps
apps: ## List installed apps
	$(MANAGE) list_apps

.PHONY: uninstall
uninstall: ## Unregister a house app (code+data kept): make uninstall NAME=workout
	@test -n "$(NAME)" || (echo "Set NAME=<app name>"; exit 1)
	$(MANAGE) uninstall_app "$(NAME)"
	$(COMPOSE) up -d

# ── people ───────────────────────────────────────────────────────────────────
.PHONY: member
member: ## Add a household member: make member NAME=alex [ROLE=member|adult|admin]
	@test -n "$(NAME)" || (echo "Set NAME=<username>"; exit 1)
	$(MANAGE) add_member "$(NAME)" --role "$(or $(ROLE),member)"

.PHONY: token
token: ## Issue a device token: make token NAME="Nora robot"
	@test -n "$(NAME)" || (echo "Set NAME=\"device name\""; exit 1)
	$(MANAGE) issue_device_token "$(NAME)"

# ── development ──────────────────────────────────────────────────────────────
.PHONY: vendor
vendor: ## Download ECharts and Gridstack into static/nora_home/vendor/ (commit them)
	./scripts/vendor.sh

.PHONY: dev
dev: ## Run locally with SQLite and no containers
	python manage.py migrate
	python manage.py bootstrap_home --demo
	python manage.py runserver

.PHONY: shell
shell: ## Django shell inside the container
	$(MANAGE) shell

.PHONY: test
test: ## Run the test suite and print the short report
	./scripts/run-tests.sh

.PHONY: test-pi
test-pi: ## Run the test suite inside the container, as the Pi runs it
	$(COMPOSE) exec -T web ./scripts/run-tests.sh

.PHONY: lint
lint: ## Ruff
	ruff check . && ruff format --check .

.env:
	@cp .env.example .env
	@python -c "import secrets;print('DJANGO_SECRET_KEY='+secrets.token_urlsafe(50))" >> .env
	@echo "Created .env from the example, with a fresh secret key."
	@echo "Fill in Slack and Anthropic keys when you have them, then re-run."

nginx/certs/nora-home.crt:
	./scripts/gen-self-signed-cert.sh
