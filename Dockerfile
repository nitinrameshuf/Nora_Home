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
RUN pip wheel --wheel-dir=/wheels -r requirements/prod.txt -r requirements/test.txt

# ── build the stylesheet ──────────────────────────────────────────────────────
# Node lives in this stage and nowhere else. The runtime image copies out one
# compiled CSS file and never sees npm, so nothing here reaches the Pi at run
# time — only at build time, which the Pi already does (`./nora up` and
# `./nora upgrade` both run `docker compose up -d --build`).
#
# Tailwind generates CSS by scanning the sources copied below, so a house app
# installed *after* this stage ran has not been scanned and its raw utility
# classes would compile to nothing. That is why house apps are expected to use
# the .nh-* component layer, which is already compiled and always works. An app
# that does want utilities needs `./nora upgrade` to rebuild.
FROM node:22-slim AS css

WORKDIR /build
COPY package.json ./
RUN npm install --no-audit --no-fund

COPY static/nora_home/css/src/ static/nora_home/css/src/
COPY templates/ templates/
COPY nora_home/ nora_home/
COPY houseapps/ houseapps/
RUN mkdir -p /out && npx tailwindcss \
        -i static/nora_home/css/src/nora.css \
        -o /out/nh.css --minify

# ── final ─────────────────────────────────────────────────────────────────────
FROM base

RUN useradd --create-home --shell /bin/bash nora
WORKDIR /srv/nora

COPY --from=builder /wheels /wheels
COPY requirements/ requirements/
RUN pip install --no-index --find-links=/wheels -r requirements/prod.txt \
                    -r requirements/test.txt \
    && rm -rf /wheels

COPY --chown=nora:nora . .

# After the source copy, so the compiled sheet wins over anything checked in.
COPY --from=css --chown=nora:nora /out/nh.css static/nora_home/css/nh.css

RUN mkdir -p /srv/nora/staticfiles /srv/nora/media /srv/nora/logs /var/backups/nora \
    && chown -R nora:nora /srv/nora /var/backups/nora \
    && chmod +x /srv/nora/docker/entrypoint.sh /srv/nora/scripts/run-tests.sh

USER nora
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -fsS http://localhost:8000/home/health/ || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/srv/nora/docker/entrypoint.sh"]
CMD ["web"]
