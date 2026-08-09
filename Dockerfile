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

# ── build the front end ───────────────────────────────────────────────────────
# node exists here and nowhere else. The final image has no node, no npm and no
# node_modules, and the Pi's host has never had any of them installed. Vite's
# output is also committed to the repo, so this stage is a rebuild of something
# that already works rather than the only way to get a working house.
FROM node:22-bookworm-slim AS assets

WORKDIR /build
COPY package.json package-lock.json ./
# npm ci needs the lockfile to agree with package.json, which is what makes this
# reproducible; `npm install` here would silently drift between architectures.
RUN npm ci --no-audit --no-fund

COPY vite.config.js ./
COPY assets/ assets/
# Tailwind scans these for class names. Copied after node_modules so editing a
# template does not re-run the install layer.
COPY templates/ templates/
COPY nora_home/ nora_home/
RUN npm run build

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

# Overwrite the committed dist/ with this build's own. They should be identical;
# when they are not, the image is right and the commit is stale.
COPY --from=assets --chown=nora:nora /build/static/nora_home/dist static/nora_home/dist

RUN mkdir -p /srv/nora/staticfiles /srv/nora/media /srv/nora/logs /var/backups/nora \
    && chown -R nora:nora /srv/nora /var/backups/nora \
    && chmod +x /srv/nora/docker/entrypoint.sh /srv/nora/scripts/run-tests.sh

USER nora
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -fsS http://localhost:8000/home/health/ || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/srv/nora/docker/entrypoint.sh"]
CMD ["web"]
