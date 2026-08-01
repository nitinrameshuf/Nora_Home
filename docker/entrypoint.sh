#!/usr/bin/env bash
#
# One entrypoint, three roles. Migrations run here — not by hand — so that
# deploying is `git pull && docker compose up -d` and nothing else.
#
#   web     migrate, collect static, serve ASGI (HTTP + websockets)
#   worker  celery worker across every queue
#   beat    celery beat, the house's clock
#
set -euo pipefail

ROLE="${1:-web}"

log() { printf '[nora:%s] %s\n' "$ROLE" "$*"; }

wait_for() {
    local host="$1" port="$2" label="$3" attempts="${4:-60}"
    log "waiting for $label at $host:$port"
    for _ in $(seq 1 "$attempts"); do
        if (echo > "/dev/tcp/$host/$port") >/dev/null 2>&1; then
            log "$label is up"
            return 0
        fi
        sleep 2
    done
    log "ERROR: $label never came up at $host:$port"
    return 1
}

wait_for "${NORA_HOME_DB_HOST:-mysql}" "${NORA_HOME_DB_PORT:-3306}" "MySQL"
wait_for "$(python -c 'import os,urllib.parse as u;print(u.urlparse(os.environ.get("NORA_HOME_REDIS_URL","redis://redis:6379/0")).hostname)')" 6379 "Redis"

case "$ROLE" in
  web)
    # Only the web role migrates. Workers starting concurrently must not race
    # each other applying the same migrations.
    log "applying migrations"
    python manage.py migrate --noinput

    log "collecting static files"
    python manage.py collectstatic --noinput --clear

    log "bootstrapping baseline records"
    python manage.py bootstrap_home || log "bootstrap reported a problem; continuing"

    log "starting daphne on 0.0.0.0:8000"
    exec daphne -b 0.0.0.0 -p 8000 --proxy-headers config.asgi:application
    ;;

  worker)
    # Wait for the web container to finish migrating before touching the ORM.
    wait_for "${NORA_HOME_WEB_HOST:-web}" 8000 "the web service" 120
    log "starting celery worker"
    exec celery -A config worker \
        --loglevel="${NORA_HOME_LOG_LEVEL:-INFO}" \
        --concurrency="${NORA_HOME_CELERY_CONCURRENCY:-3}" \
        --queues=platform,alerts,apps,ai,integrations \
        --max-tasks-per-child=200
    ;;

  beat)
    wait_for "${NORA_HOME_WEB_HOST:-web}" 8000 "the web service" 120
    log "starting celery beat"
    exec celery -A config beat \
        --loglevel="${NORA_HOME_LOG_LEVEL:-INFO}" \
        --scheduler django_celery_beat.schedulers:DatabaseScheduler
    ;;

  shell)
    exec python manage.py shell
    ;;

  *)
    # Anything else is treated as a management command: `docker compose run web
    # nora_backup --compress` just works.
    log "running: manage.py $*"
    exec python manage.py "$@"
    ;;
esac
