#!/bin/bash
#
# BoxTech IoT Platform entrypoint.
#
# Runs the one-time schema install on a fresh database, then starts the server.
# The install marker lives on the /data volume so a container restart does not
# try to install over an existing schema.

set -euo pipefail

JAR="${BOXTECH_HOME}/bin/boxtech.jar"
MARKER="${BOXTECH_DATA}/.installed"
LAUNCHER="org.springframework.boot.loader.launch.PropertiesLauncher"

log() { echo "[boxtech] $*"; }

# Wait for Postgres. Compose also gates on a healthcheck, but this keeps the
# image usable on its own (docker run against an external database).
wait_for_db() {
  local host port
  host="$(sed -E 's|.*//([^:/]+).*|\1|' <<< "${SPRING_DATASOURCE_URL:-}")"
  port="$(sed -E 's|.*//[^:/]+:([0-9]+).*|\1|' <<< "${SPRING_DATASOURCE_URL:-}")"
  [[ -n "$host" && "$host" != "${SPRING_DATASOURCE_URL:-}" ]] || return 0
  [[ "$port" =~ ^[0-9]+$ ]] || port=5432

  log "waiting for database at ${host}:${port}"
  for _ in $(seq 1 120); do
    if (exec 3<>"/dev/tcp/${host}/${port}") 2>/dev/null; then
      exec 3>&- 2>/dev/null || true
      log "database is accepting connections"
      return 0
    fi
    sleep 2
  done
  log "ERROR: database at ${host}:${port} did not become reachable"
  return 1
}

wait_for_db

if [[ ! -f "$MARKER" ]]; then
  log "fresh database detected, running schema install (load_demo=${LOAD_DEMO:-false})"
  java -cp "$JAR" ${JAVA_OPTS} \
    -Dloader.main=org.thingsboard.server.ThingsboardInstallApplication \
    -Dinstall.data_dir="${BOXTECH_HOME}/data" \
    -Dinstall.load_demo="${LOAD_DEMO:-false}" \
    -Dinstall.upgrade=false \
    "$LAUNCHER"
  touch "$MARKER"
  log "schema install complete"
else
  log "existing installation detected, skipping schema install"
fi

log "starting BoxTech IoT Platform"
exec java -cp "$JAR" ${JAVA_OPTS} \
  -Dloader.main=org.thingsboard.server.ThingsboardServerApplication \
  -Dinstall.data_dir="${BOXTECH_HOME}/data" \
  "$LAUNCHER"
