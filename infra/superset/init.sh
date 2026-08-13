#!/usr/bin/env bash
set -e
pip install psycopg2-binary --quiet
# Ensure the superset database exists (postgres volume may pre-exist without it)
python3 -c "
import psycopg2, psycopg2.extensions
conn = psycopg2.connect('postgresql://assessment:assessment@postgres:5432/assessment')
conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()
cur.execute(\"SELECT 1 FROM pg_database WHERE datname='superset'\")
if not cur.fetchone():
    cur.execute('CREATE DATABASE superset OWNER assessment')
cur.close(); conn.close()
"
superset fab create-admin --username ${SUPERSET_ADMIN_USER:-admin} --firstname Admin --lastname User --email admin@example.com --password ${SUPERSET_ADMIN_PASSWORD:-admin} || true
superset db upgrade
superset init
superset run -h 0.0.0.0 -p 8088
