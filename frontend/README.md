# LENS — Threat Hunt Findings Engine (Frontend)

Local, single-user React UI for the Threat Hunt Findings Engine. Dark,
security-tooling aesthetic. No auth.

Stack: Vite + React 18 + TypeScript + Tailwind CSS + react-router-dom.

## Prerequisites

- Node.js 20+
- The backend API running (default `http://localhost:8000`)

## Run (local)

```bash
npm install
npm run dev
```

The dev server starts on `http://localhost:5173`.

## Configuration

The API base URL is read from `VITE_API_BASE` (build/dev-time env var).

```bash
cp .env.example .env
# edit VITE_API_BASE if your backend is not on http://localhost:8000
```

Default fallback when unset: `http://localhost:8000`.

## Build

```bash
npm run build      # type-checks then builds to dist/
npm run preview    # serve the production build locally
```

## Docker

```bash
docker build -t lens-frontend .
docker run --rm -p 5173:5173 \
  -e VITE_API_BASE=http://localhost:8000 \
  lens-frontend
```

The container runs the Vite dev server (fine for a local tool).

## App structure

- `src/lib/types.ts` — centralized API types
- `src/lib/api.ts` — typed fetch client + `pollJob` helper
- `src/components/` — shared UI (`ui.tsx`), toasts, layout, panels
- `src/pages/` — `TenantsPage`, `TenantDashboard`, `HuntView`

## Flows

1. `/` — Tenants list + create. Each tenant is a fully isolated workspace.
2. `/tenants/:tid` — Knowledge base (the methodology / finding categories /
   finding format docs are the hunt "constitution") and hunts.
3. `/tenants/:tid/hunts/:hid` — Upload CSV datasets (20MB max), analyze them
   (with live progress polling, sequential "Analyze all"), and review findings
   with a per-row expandable detail drawer. Validate / reject findings.
   "Generate Report" is a disabled Phase 2 placeholder.
