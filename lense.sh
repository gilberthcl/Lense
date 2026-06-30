#!/usr/bin/env bash
#
# LENS — local dev launcher.
#
#   lense              start everything (db + backend + frontend)
#   lense start        same as above
#   lense fresh        clear the Vite cache first, then start (fixes stale theme/CSS)
#   lense stop         stop backend + frontend (leaves Postgres running)
#   lense stop --all   stop backend + frontend AND the Postgres container
#   lense restart      stop then start
#   lense status       show what's up (db, backend, frontend, ollama)
#   lense logs         tail backend + frontend logs
#   lense logs backend|frontend
#
# Ollama is expected to run on the host already (it powers the analysis).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
RUN_DIR="$ROOT/.run"
mkdir -p "$RUN_DIR"
BE_LOG="$RUN_DIR/backend.log"; BE_PID="$RUN_DIR/backend.pid"
FE_LOG="$RUN_DIR/frontend.log"; FE_PID="$RUN_DIR/frontend.pid"

BACKEND_PORT=8000
FRONTEND_PORT=5173
OLLAMA_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"

bold=$'\033[1m'; dim=$'\033[2m'; grn=$'\033[32m'; ylw=$'\033[33m'; red=$'\033[31m'; rst=$'\033[0m'
say()  { printf "%s\n" "$*"; }
ok()   { printf "  ${grn}✓${rst} %s\n" "$*"; }
warn() { printf "  ${ylw}!${rst} %s\n" "$*"; }
err()  { printf "  ${red}✗${rst} %s\n" "$*"; }

pid_alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }
port_up()   { curl -sf -o /dev/null "http://localhost:$1" 2>/dev/null; }

ensure_env() {
  if [ ! -f "$ROOT/.env" ]; then
    cp "$ROOT/.env.example" "$ROOT/.env" && ok "created .env from .env.example"
  fi
}

ensure_db() {
  say "${bold}Postgres${rst}"
  ensure_env
  # Use Docker only if it's actually usable. Many machines can't run Docker
  # Desktop (org/MDM policy), so when it's absent or won't start we fall back to
  # a native Homebrew Postgres + pgvector — no Docker required.
  if command -v docker >/dev/null 2>&1; then
    if ! docker info >/dev/null 2>&1; then
      say "  ${dim}… starting Docker Desktop (up to 90s — accept any first-run prompt)${rst}"
      open -a Docker >/dev/null 2>&1 || true
      local i; for i in $(seq 1 45); do docker info >/dev/null 2>&1 && break; sleep 2; done
    fi
    if docker info >/dev/null 2>&1; then
      local out
      if ! out="$( cd "$ROOT" && docker compose up -d db 2>&1 )"; then
        err "could not start the db container:"
        printf "%s\n" "$out" | sed 's/^/      /'
        return 1
      fi
      local i
      for i in $(seq 1 30); do
        if ( cd "$ROOT" && docker compose exec -T db pg_isready -U "${POSTGRES_USER:-lens}" >/dev/null 2>&1 ); then
          ok "database ready on :${POSTGRES_PORT:-5432} (docker)"; return 0
        fi
        sleep 1
      done
      warn "database not confirmed ready — continuing anyway"; return 0
    fi
    warn "Docker is installed but isn't running — using a native Postgres instead"
  fi
  ensure_db_native
}

# Docker-less fallback: a native Homebrew Postgres with pgvector on :PORT.
# Reliable on machines where Docker Desktop can't be installed/run.
ensure_db_native() {
  local user pass db port
  user="$(env_or POSTGRES_USER lens)"; pass="$(env_or POSTGRES_PASSWORD lens_dev_change_me)"
  db="$(env_or POSTGRES_DB lens)";     port="$(env_or POSTGRES_PORT 5432)"

  if ! command -v brew >/dev/null 2>&1; then
    err "no Docker and no Homebrew — install Homebrew (https://brew.sh), then re-run 'lense'"
    return 1
  fi

  # Reuse an already-installed postgres formula; otherwise install postgresql@16.
  local pgf="" f
  for f in postgresql@16 postgresql@17 postgresql@15 postgresql@14 postgresql; do
    brew list "$f" >/dev/null 2>&1 && { pgf="$f"; break; }
  done
  if [ -z "$pgf" ]; then
    say "  ${dim}… installing postgresql@16 (first run, a few minutes)${rst}"
    brew install postgresql@16 >/dev/null 2>&1 || { err "brew install postgresql@16 failed"; return 1; }
    pgf="postgresql@16"
  fi

  local pgbin; pgbin="$(brew --prefix "$pgf" 2>/dev/null)/bin"
  [ -x "$pgbin/pg_isready" ] || { err "postgres tools not found under $pgbin"; return 1; }

  # Start the service if it isn't already accepting connections on the port.
  if ! "$pgbin/pg_isready" -h localhost -p "$port" >/dev/null 2>&1; then
    say "  ${dim}… starting $pgf service${rst}"
    brew services start "$pgf" >/dev/null 2>&1 || true
    local i; for i in $(seq 1 30); do
      "$pgbin/pg_isready" -h localhost -p "$port" >/dev/null 2>&1 && break; sleep 1
    done
  fi
  if ! "$pgbin/pg_isready" -h localhost -p "$port" >/dev/null 2>&1; then
    err "Postgres didn't come up on :$port — check 'brew services list'"; return 1
  fi

  # Make the pgvector extension AVAILABLE for this exact postgres (the app's
  # knowledge base needs it). Try the bottle first; if the control file still
  # isn't there (version mismatch), build it from source against this pg_config.
  local sharedir ctrl
  sharedir="$("$pgbin/pg_config" --sharedir 2>/dev/null)"
  ctrl="$sharedir/extension/vector.control"
  if [ ! -f "$ctrl" ]; then
    say "  ${dim}… installing pgvector${rst}"
    brew install pgvector >/dev/null 2>&1 || true
  fi
  if [ ! -f "$ctrl" ]; then
    say "  ${dim}… building pgvector from source for $pgf${rst}"
    local tmp; tmp="$(mktemp -d)"
    git clone --depth 1 --branch v0.8.0 https://github.com/pgvector/pgvector.git "$tmp/pgvector" >/dev/null 2>&1 \
      && ( cd "$tmp/pgvector" \
           && make PG_CONFIG="$pgbin/pg_config" >/dev/null 2>&1 \
           && make install PG_CONFIG="$pgbin/pg_config" >/dev/null 2>&1 ) \
      || err "pgvector build failed — install Xcode CLT ('xcode-select --install') and re-run"
    rm -rf "$tmp"
  fi
  if [ ! -f "$ctrl" ]; then
    err "pgvector isn't available for $pgf (looked in $sharedir/extension)"
    err "see https://github.com/pgvector/pgvector#installation, then re-run 'lense'"
    return 1
  fi

  # Provision role + database + extension (idempotent). Connect to the bootstrap
  # 'postgres' db as the OS superuser Homebrew's initdb created.
  "$pgbin/psql" -h localhost -p "$port" -d postgres -v ON_ERROR_STOP=1 -q >/dev/null 2>&1 <<SQL
DO \$do\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='${user}') THEN
    CREATE ROLE "${user}" LOGIN SUPERUSER PASSWORD '${pass}';
  ELSE
    ALTER ROLE "${user}" WITH LOGIN SUPERUSER PASSWORD '${pass}';
  END IF;
END \$do\$;
SQL
  if [ $? -ne 0 ]; then
    err "couldn't provision role '${user}' — try manually: $pgbin/psql -d postgres"
    return 1
  fi
  if ! "$pgbin/psql" -h localhost -p "$port" -d postgres -tAc \
        "SELECT 1 FROM pg_database WHERE datname='${db}'" 2>/dev/null | grep -q 1; then
    "$pgbin/createdb" -h localhost -p "$port" -O "${user}" "${db}" >/dev/null 2>&1 \
      || { err "couldn't create database '${db}'"; return 1; }
  fi
  if ! "$pgbin/psql" -h localhost -p "$port" -d "${db}" -q \
        -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null 2>&1; then
    err "couldn't enable pgvector in database '${db}'"; return 1
  fi
  ok "database ready on :$port (native $pgf + pgvector)"
}

# Create backend/venv and install deps if absent, so migrations/backend can run
# without a separate manual step. Prefers python3.11 (the project target).
ensure_venv() {
  [ -f "$BACKEND/venv/bin/activate" ] && return 0
  say "${bold}Python env${rst}"
  local py="" c
  for c in python3.11 python3; do
    command -v "$c" >/dev/null 2>&1 && { py="$c"; break; }
  done
  [ -n "$py" ] || { err "no python3 found — install Python 3.11"; return 1; }
  case "$py" in python3)
    warn "python3.11 not found; using $($py --version 2>&1) — the project targets 3.11" ;;
  esac
  say "  ${dim}… creating backend/venv and installing deps (first run, a few minutes)${rst}"
  # Install from public PyPI by default. A corporate pip mirror (e.g. an internal
  # Artifactory) configured globally will 401 here and break the install, so we
  # point pip explicitly at pypi.org. Override with LENSE_PIP_INDEX_URL if you
  # have working credentials for an internal index.
  local idx="${LENSE_PIP_INDEX_URL:-https://pypi.org/simple/}"
  local pipargs="--index-url $idx --trusted-host pypi.org --trusted-host files.pythonhosted.org"
  if ( cd "$BACKEND" && "$py" -m venv venv && source venv/bin/activate \
        && pip install --quiet $pipargs --upgrade pip \
        && pip install --quiet $pipargs -r requirements.txt ); then
    ok "backend/venv ready ($py, index: $idx)"
  else
    err "venv setup failed — likely a pip index/credentials issue."
    err "if your shell forces an internal mirror, this installs from public PyPI:"
    say "      cd '$BACKEND' && '$py' -m venv venv && source venv/bin/activate \\"
    say "        && pip install --index-url https://pypi.org/simple/ -r requirements.txt"
    return 1
  fi
}

start_backend() {
  say "${bold}Backend${rst}"
  if pid_alive "$BE_PID" || port_up "$BACKEND_PORT/api/health"; then ok "already running on :$BACKEND_PORT"; return 0; fi
  if [ ! -f "$BACKEND/venv/bin/activate" ]; then
    err "no venv at backend/venv — create it once:"
    say "      cd '$BACKEND' && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    return 1
  fi
  if lsof -i ":$BACKEND_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    err "port $BACKEND_PORT is already in use — stop the other process (lsof -i :$BACKEND_PORT) or 'lense stop'"
    return 1
  fi
  ( cd "$BACKEND" && source venv/bin/activate && exec uvicorn app.main:app --reload --port "$BACKEND_PORT" ) \
      >"$BE_LOG" 2>&1 &
  echo $! > "$BE_PID"
  printf "  ${dim}… waiting for the backend (first start can take ~15s)${rst}\n"
  local i
  for i in $(seq 1 60); do
    port_up "$BACKEND_PORT/api/health" && { ok "http://localhost:$BACKEND_PORT  (logs: .run/backend.log)"; return 0; }
    pid_alive "$BE_PID" || break   # process exited early → show the error
    sleep 1
  done
  err "backend did not come up — last lines of .run/backend.log:"
  tail -n 15 "$BE_LOG" 2>/dev/null | sed 's/^/      /'
  return 1
}

start_frontend() {
  say "${bold}Frontend${rst}"
  if pid_alive "$FE_PID" || port_up "$FRONTEND_PORT"; then ok "already running on :$FRONTEND_PORT"; return 0; fi
  if [ ! -d "$FRONTEND/node_modules" ]; then
    warn "installing frontend deps (first run)…"
    ( cd "$FRONTEND" && npm install ) || { err "npm install failed"; return 1; }
  fi
  ( cd "$FRONTEND" && exec npm run dev ) >"$FE_LOG" 2>&1 &
  echo $! > "$FE_PID"
  local i
  for i in $(seq 1 60); do
    port_up "$FRONTEND_PORT" && { ok "http://localhost:$FRONTEND_PORT  (logs: .run/frontend.log)"; return 0; }
    pid_alive "$FE_PID" || break
    sleep 1
  done
  err "frontend did not come up — last lines of .run/frontend.log:"
  tail -n 15 "$FE_LOG" 2>/dev/null | sed 's/^/      /'
  return 1
}

ensure_migrations() {
  say "${bold}Migrations${rst}"
  if [ ! -f "$BACKEND/venv/bin/activate" ]; then
    warn "no venv — skipping (the backend step will explain how to create it)"; return 0
  fi
  printf "  ${dim}… running 'alembic upgrade head' (15s lock timeout)${rst}\n"
  # lock_timeout makes a blocked ALTER (e.g. a leftover connection holding a lock)
  # fail fast instead of hanging forever; statement_timeout bounds slow DDL.
  if ( cd "$BACKEND" && source venv/bin/activate \
        && PGOPTIONS='-c lock_timeout=15000 -c statement_timeout=300000' alembic upgrade head ) >>"$BE_LOG" 2>&1; then
    ok "schema up to date (alembic upgrade head)"
  else
    warn "alembic upgrade failed or timed out — see .run/backend.log"
    warn "a lock from a previous run can cause this — try:  lense stop --all && lense"
    warn "if it says a table already exists:  (cd backend && source venv/bin/activate && alembic stamp head)"
  fi
}

# Read a value from .env, falling back to a default.
env_or() {
  local v=""
  [ -f "$ROOT/.env" ] && v="$(grep -E "^$1=" "$ROOT/.env" | head -1 | cut -d= -f2- | cut -d'#' -f1 | tr -d ' \r')"
  [ -n "$v" ] && printf "%s" "$v" || printf "%s" "$2"
}

check_models() {
  local tags; tags="$(curl -sf "$OLLAMA_URL/api/tags" 2>/dev/null || true)"
  [ -z "$tags" ] && return 0   # ollama unreachable — already warned by check_ollama
  local seen=" " m miss=0
  for m in \
      "$(env_or OLLAMA_ANALYST_MODEL gemma3:27b)" \
      "$(env_or OLLAMA_REVIEWER_MODEL gpt-oss:20b)" \
      "$(env_or OLLAMA_QA_MODEL gpt-oss:20b)" \
      "$(env_or OLLAMA_EMBED_MODEL nomic-embed-text)"; do
    case "$seen" in *" $m "*) continue ;; esac   # dedupe (reviewer == qa)
    seen="$seen$m "
    if printf "%s" "$tags" | grep -qF "\"$m\""; then
      ok "model present: $m"
    else
      warn "model MISSING: $m   → ollama pull $m"
      miss=1
    fi
  done
  [ "$miss" = 1 ] && warn "analysis will fail until the missing model(s) are pulled"
  return 0
}

check_ollama() {
  say "${bold}Ollama${rst}"
  if curl -sf -o /dev/null "$OLLAMA_URL/api/tags"; then
    ok "reachable at $OLLAMA_URL"
    check_models
  else
    warn "not reachable at $OLLAMA_URL — start it with:  ollama serve"
  fi
}

stop_one() {  # $1=name $2=pidfile $3=port-pattern
  if pid_alive "$2"; then kill "$(cat "$2")" 2>/dev/null || true; fi
  rm -f "$2"
  pkill -f "$3" 2>/dev/null || true
  ok "$1 stopped"
}

check_prereqs() {
  say "${bold}Prerequisites${rst}"
  local all=1 c
  for c in python3 node npm docker; do
    if command -v "$c" >/dev/null 2>&1; then ok "$c"; else err "$c not found"; all=0; fi
  done
  command -v ollama >/dev/null 2>&1 && ok "ollama" || warn "ollama not found — install from https://ollama.com"
  [ "$all" = 1 ] || { err "install the missing tool(s) above and re-run"; return 1; }
}

rc_file() { case "${SHELL:-}" in *bash*) echo "$HOME/.bashrc" ;; *) echo "$HOME/.zshrc" ;; esac; }

add_alias_rc() {
  local rc; rc="$(rc_file)"
  if grep -q "alias lense=" "$rc" 2>/dev/null; then ok "alias already in $rc"; else
    printf 'alias lense="%s/lense.sh"\n' "$ROOT" >> "$rc"; ok "alias added to $rc"
  fi
}

add_path_rc() {
  local dir="$1" rc; rc="$(rc_file)"
  grep -q "$dir" "$rc" 2>/dev/null || { printf 'export PATH="%s:$PATH"\n' "$dir" >> "$rc"; ok "added $dir to PATH in $rc"; }
}

install_cli() {
  say "${bold}CLI${rst}"
  chmod +x "$ROOT/lense.sh" 2>/dev/null || true
  # Prefer a writable directory already on PATH (no sudo needed).
  local d target=""
  for d in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin" "$HOME/bin"; do
    case ":$PATH:" in *":$d:"*) [ -d "$d" ] && [ -w "$d" ] && { target="$d"; break; } ;; esac
  done
  if [ -z "$target" ]; then
    mkdir -p "$HOME/.local/bin"; target="$HOME/.local/bin"; add_path_rc "$target"
  fi
  ln -sf "$ROOT/lense.sh" "$target/lense" && ok "installed: $target/lense" || warn "could not symlink into $target"
  add_alias_rc   # belt-and-suspenders so it works either way
}

cmd_install() {
  say "${bold}Enabling the 'lense' command${rst} ${dim}($ROOT)${rst}"
  install_cli
  pull_models
  say ""
  ok "Done. Open a NEW terminal, or run:  source $(rc_file)"
  ok "Then:  lense status"
}

pull_models() {
  say "${bold}Pulling models${rst}"
  command -v ollama >/dev/null 2>&1 || { warn "ollama not installed — skipping pulls"; return 0; }
  local seen=" " m
  for m in \
      "$(env_or OLLAMA_ANALYST_MODEL gemma3:27b)" \
      "$(env_or OLLAMA_REVIEWER_MODEL gpt-oss:20b)" \
      "$(env_or OLLAMA_QA_MODEL gpt-oss:20b)" \
      "$(env_or OLLAMA_EMBED_MODEL nomic-embed-text)"; do
    case "$seen" in *" $m "*) continue ;; esac
    seen="$seen$m "
    say "  pulling $m …"; ollama pull "$m" || warn "pull failed: $m"
  done
}

cmd_setup() {
  say "${bold}Setting up LENS${rst} ${dim}($ROOT)${rst}"
  check_prereqs || return 1

  say "${bold}Config${rst}"
  if [ ! -f "$ROOT/.env" ]; then
    cp "$ROOT/.env.example" "$ROOT/.env" && ok "created .env from .env.example"
  else ok ".env present"; fi

  say "${bold}Backend deps${rst}"
  if [ ! -f "$BACKEND/venv/bin/activate" ]; then
    ( cd "$BACKEND" && python3 -m venv venv && source venv/bin/activate \
        && pip install --quiet --upgrade pip && pip install -r requirements.txt ) \
      && ok "venv created + requirements installed" || { err "backend setup failed"; return 1; }
  else ok "venv present"; fi

  say "${bold}Frontend deps${rst}"
  if [ ! -d "$FRONTEND/node_modules" ]; then
    ( cd "$FRONTEND" && npm install ) && ok "node_modules installed" || { err "npm install failed"; return 1; }
  else ok "node_modules present"; fi

  install_cli
  [ "${1:-}" = "--pull-models" ] && pull_models

  say ""
  cmd_start
}

cmd_up() {
  # Bulletproof bring-up: clear any stray backend, ensure Docker, then start.
  say "${bold}Bringing up LENS${rst}"
  local stray; stray="$(lsof -ti ":$BACKEND_PORT" 2>/dev/null || true)"
  if [ -n "$stray" ]; then
    echo "$stray" | xargs kill -9 2>/dev/null || true
    ok "cleared stray process on :$BACKEND_PORT"
  fi
  if ! docker info >/dev/null 2>&1; then
    say "  ${dim}starting Docker Desktop…${rst}"
    open -a Docker >/dev/null 2>&1 || true
    local i; for i in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 2; done
  fi
  cmd_start
  say ""
  printf "  build: "; curl -s "http://localhost:$BACKEND_PORT/api/health" 2>/dev/null; echo
}

cmd_start() {
  say "${bold}Starting LENS${rst} ${dim}($ROOT)${rst}"
  ensure_env
  if ! ensure_db; then
    err "Postgres is not up — skipping migrations/backend (fix the above, then 'lense')"
    return 1
  fi
  ensure_venv || true
  ensure_migrations || true
  start_backend || true
  start_frontend || true
  check_ollama
  say ""
  say "${grn}${bold}LENS is up →${rst} ${bold}http://localhost:$FRONTEND_PORT${rst}"
  say "${dim}stop with: lense stop   ·   logs: lense logs${rst}"
}

cmd_stop() {
  say "${bold}Stopping LENS${rst}"
  stop_one "frontend" "$FE_PID" "vite"
  stop_one "backend"  "$BE_PID" "uvicorn app.main"
  if [ "${1:-}" = "--all" ]; then
    if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
      ( cd "$ROOT" && docker compose stop db >/dev/null 2>&1 ) && ok "database stopped" || true
    else
      say "${dim}(native Postgres left running — it's a shared brew service; stop with 'brew services stop postgresql@16')${rst}"
    fi
  else
    say "${dim}(Postgres left running — use 'lense stop --all' to stop it too)${rst}"
  fi
}

cmd_status() {
  say "${bold}LENS status${rst}"
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    ( cd "$ROOT" && docker compose ps db --status running 2>/dev/null | grep -q db ) && ok "database: running (docker)" || warn "database: stopped"
  else
    local port; port="$(env_or POSTGRES_PORT 5432)"
    if command -v pg_isready >/dev/null 2>&1 && pg_isready -h localhost -p "$port" >/dev/null 2>&1; then
      ok "database: running (native :$port)"
    elif nc -z localhost "$port" >/dev/null 2>&1; then
      ok "database: running (native :$port)"
    else
      warn "database: stopped"
    fi
  fi
  port_up "$BACKEND_PORT/api/health" && ok "backend:  http://localhost:$BACKEND_PORT" || warn "backend:  down"
  port_up "$FRONTEND_PORT" && ok "frontend: http://localhost:$FRONTEND_PORT" || warn "frontend: down"
  if curl -sf -o /dev/null "$OLLAMA_URL/api/tags"; then
    ok "ollama:   $OLLAMA_URL"
    check_models
  else
    warn "ollama:   unreachable"
  fi
}

cmd_logs() {
  case "${1:-both}" in
    backend)  tail -f "$BE_LOG" ;;
    frontend) tail -f "$FE_LOG" ;;
    *)        tail -f "$BE_LOG" "$FE_LOG" ;;
  esac
}

cmd_ollama() {
  command -v ollama >/dev/null 2>&1 || { err "ollama not found in PATH"; return 1; }
  case "${1:-status}" in
    status)
      say "${bold}Ollama${rst}"
      if curl -sf -o /dev/null "$OLLAMA_URL/api/tags"; then ok "reachable at $OLLAMA_URL"
      else warn "not reachable at $OLLAMA_URL"; fi
      say "  loaded models in memory (ollama ps):"
      ollama ps 2>/dev/null | sed 's/^/    /'
      ;;
    stop|unload)
      # Unload all loaded models from RAM/VRAM (frees memory; keeps server up).
      say "${bold}Unloading Ollama models${rst}"
      local names; names="$(ollama ps 2>/dev/null | awk 'NR>1{print $1}')"
      if [ -z "$names" ]; then ok "no models currently loaded"; return 0; fi
      local m; for m in $names; do ollama stop "$m" 2>/dev/null && ok "unloaded $m" || warn "could not unload $m"; done
      ;;
    restart|kill)
      # Kill in-flight generations + the server, then bring it back. Use this
      # when stuck requests are pegging the machine.
      say "${bold}Restarting Ollama${rst}"
      if command -v brew >/dev/null 2>&1 && brew services list 2>/dev/null | grep -q '^ollama'; then
        brew services restart ollama && { ok "restarted via brew services"; }
      else
        pkill -f "ollama serve" 2>/dev/null || true
        killall Ollama 2>/dev/null || true
        killall ollama 2>/dev/null || true
        sleep 2
        if [ -d "/Applications/Ollama.app" ]; then
          open -a Ollama && ok "relaunched the Ollama app"
        else
          ( nohup ollama serve >/dev/null 2>&1 & ) && ok "started 'ollama serve'"
        fi
      fi
      local i; for i in $(seq 1 30); do
        curl -sf -o /dev/null "$OLLAMA_URL/api/tags" && { ok "Ollama reachable again"; return 0; }
        sleep 1
      done
      warn "Ollama not reachable yet — give it a few seconds or check the app"
      ;;
    *) say "usage: lense ollama [status|stop|restart]" ;;
  esac
}

cmd_train() {  # offline per-tenant LoRA trainer (W6) — runs on Apple Silicon
  [ -f "$BACKEND/venv/bin/activate" ] || { err "no venv at backend/venv — see 'lense' setup"; return 1; }
  shift  # drop 'train'
  if [ $# -eq 0 ]; then
    say "usage: lense train <tenant_id> --base-model <model> [--iters N] [--dry-run]"
    say "       see docs/training-runbook.md"
    return 0
  fi
  ( cd "$BACKEND" && source venv/bin/activate && exec python -m tools.train_lora "$@" )
}

case "${1:-start}" in
  setup|deploy) cmd_setup "${2:-}" ;;
  install)      cmd_install ;;
  train)   cmd_train "$@" ;;
  start)   cmd_start ;;
  up)      cmd_up ;;
  fresh)   cmd_stop; sleep 1; rm -rf "$FRONTEND/node_modules/.vite" && ok "cleared Vite cache"; cmd_start ;;
  stop)    cmd_stop "${2:-}" ;;
  restart) cmd_stop "${2:-}"; sleep 1; cmd_start ;;
  status)  cmd_status ;;
  logs)    cmd_logs "${2:-both}" ;;
  pull)    pull_models ;;
  ollama)  cmd_ollama "${2:-status}" ;;
  *) say "usage: lense [up | setup [--pull-models] | install | start | fresh | stop [--all] | restart | status | logs [backend|frontend] | pull | ollama [status|stop|restart] | train <tenant_id> --base-model <m>]" ;;
esac
