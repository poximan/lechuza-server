#!/bin/sh
set -eu

install -d -o appuser -g appgroup /app/data
if ! chown -R appuser:appgroup /app/data; then
    echo "ERROR FATAL: no se pudieron asignar permisos a /app/data para appuser." >&2
    exit 1
fi
if ! gosu appuser test -w /app/data; then
    echo "ERROR FATAL: /app/data no es escribible por appuser (UID 1000)." >&2
    exit 1
fi

exec gosu appuser "$@"
