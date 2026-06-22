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
  if ! command -v docker >/dev/null 2>&1; then
    err "docker not found — install Docker Desktop (or run Postgres yourself on :5432)"
    return 1
  fi
  if ! docker info >/dev/null 2>&1; then
    err "Docker isn't running — open Docker Desktop, wait for it to start, then run 'lense'"
    return 1
  fi
  ensure_env
  local out
  if ! out="$( cd "$ROOT" && docker compose up -d db 2>&1 )"; then
    err "could not start the db container:"
    printf "%s\n" "$out" | sed 's/^/      /'
    return 1
  fi
  # wait for readiness (up to ~30s)
  local i
  for i in $(seq 1 30); do
    if ( cd "$ROOT" && docker compose exec -T db pg_isready -U "${POSTGRES_USER:-lens}" >/dev/null 2>&1 ); then
      ok "database ready on :${POSTGRES_PORT:-5432}"; return 0
    fi
    sleep 1
  done
  warn "database not confirmed ready — continuing anyway"
}

start_backend() {
  say "${bold}Backend${rst}"
  if pid_alive "$BE_PID" || port_up "$BACKEND_PORT/api/health"; then ok "already running on :$BACKEND_PORT"; return 0; fi
  if [ ! -f "$BACKEND/venv/bin/activate" ]; then
    err "no venv at backend/venv — create it once:"
    say "      cd '$BACKEND' && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    return 1
  fi
  ( cd "$BACKEND" && source venv/bin/activate && exec uvicorn app.main:app --reload --port "$BACKEND_PORT" ) \
      >"$BE_LOG" 2>&1 &
  echo $! > "$BE_PID"
  local i
  for i in $(seq 1 30); do
    port_up "$BACKEND_PORT/api/health" && { ok "http://localhost:$BACKEND_PORT  (logs: .run/backend.log)"; return 0; }
    sleep 1
  done
  err "backend did not come up — see .run/backend.log"; return 1
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
  for i in $(seq 1 30); do
    port_up "$FRONTEND_PORT" && { ok "http://localhost:$FRONTEND_PORT  (logs: .run/frontend.log)"; return 0; }
    sleep 1
  done
  err "frontend did not come up — see .run/frontend.log"; return 1
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

cmd_start() {
  say "${bold}Starting LENS${rst} ${dim}($ROOT)${rst}"
  ensure_env
  if ! ensure_db; then
    err "Postgres is not up — skipping migrations/backend (fix the above, then 'lense')"
    return 1
  fi
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
    ( cd "$ROOT" && docker compose stop db >/dev/null 2>&1 ) && ok "database stopped" || true
  else
    say "${dim}(Postgres left running — use 'lense stop --all' to stop it too)${rst}"
  fi
}

cmd_status() {
  say "${bold}LENS status${rst}"
  ( cd "$ROOT" && docker compose ps db --status running 2>/dev/null | grep -q db ) && ok "database: running" || warn "database: stopped"
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

case "${1:-start}" in
  setup|deploy) cmd_setup "${2:-}" ;;
  install)      cmd_install ;;
  start)   cmd_start ;;
  fresh)   rm -rf "$FRONTEND/node_modules/.vite" && ok "cleared Vite cache"; cmd_start ;;
  stop)    cmd_stop "${2:-}" ;;
  restart) cmd_stop "${2:-}"; sleep 1; cmd_start ;;
  status)  cmd_status ;;
  logs)    cmd_logs "${2:-both}" ;;
  pull)    pull_models ;;
  *) say "usage: lense [setup [--pull-models] | install | start | fresh | stop [--all] | restart | status | logs [backend|frontend] | pull]" ;;
esac
