#!/usr/bin/env bash
set -e
superset fab create-admin --username ${SUPERSET_ADMIN_USER:-admin} --firstname Admin --lastname User --email admin@example.com --password ${SUPERSET_ADMIN_PASSWORD:-admin} || true
superset db upgrade
superset init
superset run -h 0.0.0.0 -p 8088
