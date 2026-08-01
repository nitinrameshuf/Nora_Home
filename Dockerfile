# Nora Home. One image, three roles (web, worker, beat) chosen by the command.
# Builds natively on the Pi 5 (arm64) and on an x86 laptop.

FROM python:3.13-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.pi

# Runtime libraries only. Build tools live in the builder stage so the final
# image stays small enough to pull comfortably over a home connection.
#
# mongodb-database-tools is deliberately not installed here: it isn't a Debian
# package (only MongoDB's own apt repo carries it), so it fails on stock
# Debian/Raspberry Pi OS. nora_backup/nora_restore already treat a missing
# mongodump/mongorestore as a soft skip, not a failure, so the house just runs
# without Mongo backup/restore until that repo is added separately.
RUN apt-get update && apt-get install -y --no-install-recommends \
        default-mysql-client \
        libmariadb3 \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*

# ── build wheels ──────────────────────────────────────────────────────────────
FROM base AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential pkg-config libmariadb-dev default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels
COPY requirements/ requirements/
RUN pip wheel --wheel-dir=/wheels -r requirements/prod.txt

# ── final ─────────────────────────────────────────────────────────────────────
FROM base

RUN useradd --create-home --shell /bin/bash nora
WORKDIR /srv/nora

COPY --from=builder /wheels /wheels
COPY requirements/ requirements/
RUN pip install --no-index --find-links=/wheels -r requirements/prod.txt \
    && rm -rf /wheels

COPY --chown=nora:nora . .

RUN mkdir -p /srv/nora/staticfiles /srv/nora/media /srv/nora/logs /var/backups/nora \
    && chown -R nora:nora /srv/nora /var/backups/nora \
    && chmod +x /srv/nora/docker/entrypoint.sh

USER nora
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -fsS http://localhost:8000/home/health/ || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/srv/nora/docker/entrypoint.sh"]
CMD ["web"]
