import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, API_BASE } from "../lib/api";

function HealthDot() {
  const [ok, setOk] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    const check = () =>
      api
        .health()
        .then(() => alive && setOk(true))
        .catch(() => alive && setOk(false));
    check();
    const t = window.setInterval(check, 15000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, []);

  const color =
    ok === null ? "bg-slate-500" : ok ? "bg-emerald-500" : "bg-red-500";
  const label = ok === null ? "checking" : ok ? "backend online" : "backend offline";

  return (
    <div
      className="flex items-center gap-2 text-xs text-slate-500"
      title={`${label} — ${API_BASE}`}
    >
      <span className={`h-2 w-2 rounded-full ${color}`} />
      <span className="font-mono">{API_BASE}</span>
    </div>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-40 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <Link to="/" className="flex items-center gap-2">
            <span className="font-mono text-lg font-bold tracking-widest text-indigo-400">
              LENS
            </span>
            <span className="text-xs uppercase tracking-wide text-slate-500">
              Threat Hunt Findings Engine
            </span>
          </Link>
          <HealthDot />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
    </div>
  );
}

export function Breadcrumbs({
  items,
}: {
  items: { label: string; to?: string }[];
}) {
  return (
    <nav className="mb-6 flex flex-wrap items-center gap-1.5 text-sm text-slate-500">
      {items.map((it, i) => (
        <span key={i} className="flex items-center gap-1.5">
          {it.to ? (
            <Link to={it.to} className="hover:text-slate-300">
              {it.label}
            </Link>
          ) : (
            <span className="text-slate-300">{it.label}</span>
          )}
          {i < items.length - 1 && <span className="text-slate-700">/</span>}
        </span>
      ))}
    </nav>
  );
}
