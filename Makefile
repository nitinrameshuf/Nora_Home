# Nora Home.
#
# The real command is ./nora — run `./nora help` for the full list.
#
# These targets are thin aliases kept because muscle memory and older docs still
# reach for `make`. Every one of them delegates, so there is a single
# implementation and the two cannot drift apart.

.DEFAULT_GOAL := help
NORA := ./nora

.PHONY: help
help: ## Show the runner's help
	@$(NORA) help

# ── everyday ─────────────────────────────────────────────────────────────────
.PHONY: up
up: ## Start the house
	@$(NORA) up

.PHONY: down
down: ## Stop everything (data volumes are kept)
	@$(NORA) down

.PHONY: deploy
deploy: ## Backup, pull, rebuild, migrate, restart
	@$(NORA) upgrade

.PHONY: upgrade
upgrade: ## Same as deploy
	@$(NORA) upgrade

.PHONY: restart
restart: ## Restart the app without touching the databases
	@$(NORA) restart

.PHONY: recreate
recreate: ## Replace containers so an edited .env takes effect
	@$(NORA) recreate

.PHONY: logs
logs: ## Follow logs
	@$(NORA) logs

.PHONY: ps
ps: ## What is running, plus health
	@$(NORA) status

.PHONY: status
status: ## What is running, plus health
	@$(NORA) status

.PHONY: screens
screens: ## Hard-reload the wall and kiosk browsers
	@$(NORA) screens

# ── data ─────────────────────────────────────────────────────────────────────
.PHONY: backup
backup: ## Full backup now
	@$(NORA) backup

.PHONY: restore
restore: ## Restore a backup: make restore FROM=/var/backups/nora/nora-....tar.gz
	@test -n "$(FROM)" || (echo "Set FROM=/path/to/backup"; exit 1)
	@$(NORA) restore "$(FROM)"

.PHONY: migrate
migrate: ## Apply migrations by hand (normally automatic on start)
	@$(NORA) manage migrate

.PHONY: makemigrations
makemigrations: ## Generate migrations for changed models
	@$(NORA) manage makemigrations

# ── apps ─────────────────────────────────────────────────────────────────────
.PHONY: app
app: ## Install a house app: make app SRC=https://github.com/you/nora-workout
	@test -n "$(SRC)" || (echo "Set SRC=<git url or local path>"; exit 1)
	@$(NORA) app install "$(SRC)"

.PHONY: apps
apps: ## List installed apps
	@$(NORA) app list

.PHONY: uninstall
uninstall: ## Unregister a house app (code+data kept): make uninstall NAME=workout
	@test -n "$(NAME)" || (echo "Set NAME=<app name>"; exit 1)
	@$(NORA) app uninstall "$(NAME)"

# ── people ───────────────────────────────────────────────────────────────────
.PHONY: member
member: ## Add a household member: make member NAME=alex [ROLE=member|adult|admin]
	@test -n "$(NAME)" || (echo "Set NAME=<username>"; exit 1)
	@$(NORA) member "$(NAME)" "$(or $(ROLE),member)"

.PHONY: token
token: ## Issue a device token: make token NAME="Nora robot"
	@test -n "$(NAME)" || (echo "Set NAME=\"device name\""; exit 1)
	@$(NORA) token "$(NAME)"

# ── development ──────────────────────────────────────────────────────────────
.PHONY: vendor
vendor: ## Download ECharts and Gridstack into static/nora_home/vendor/
	./scripts/vendor.sh

.PHONY: dev
dev: ## Run locally with SQLite and no containers
	python manage.py migrate
	python manage.py bootstrap_home --demo
	python manage.py runserver

.PHONY: shell
shell: ## Django shell inside the container
	@$(NORA) shell

.PHONY: test
test: ## Run the test suite and print the short report
	./scripts/run-tests.sh

.PHONY: test-pi
test-pi: ## Run the test suite inside the container, as the Pi runs it
	@$(NORA) test

.PHONY: lint
lint: ## Ruff
	ruff check . && ruff format --check .
