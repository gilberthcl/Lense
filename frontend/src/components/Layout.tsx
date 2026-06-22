import { type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import Sidebar from "./Sidebar";
import { ThemeBalls } from "./Theme";
import { lockApp } from "./PinGate";
import { IconChevron, IconConfig, IconLock } from "./icons";

function Topbar() {
  return (
    <header className="sticky top-0 z-10 flex items-center justify-end gap-4 border-b border-slate-800/70 bg-slate-950/80 px-8 py-2.5 backdrop-blur">
      <ThemeBalls />
      <span className="h-5 w-px bg-slate-800" />
      <NavLink
        to="/config"
        title="Configuration"
        aria-label="Configuration"
        className={({ isActive }) =>
          `flex h-8 w-8 items-center justify-center rounded-md transition-colors ${
            isActive
              ? "bg-indigo-500/10 text-indigo-300 ring-1 ring-inset ring-indigo-500/30"
              : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
          }`
        }
      >
        <IconConfig width={18} height={18} />
      </NavLink>
      <button
        onClick={lockApp}
        title="Lock"
        aria-label="Lock"
        className="flex h-8 w-8 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-800/60 hover:text-slate-200"
      >
        <IconLock width={17} height={17} />
      </button>
    </header>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full bg-slate-950">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-6xl px-8 py-8">{children}</div>
        </main>
      </div>
    </div>
  );
}

export function Breadcrumbs({
  items,
}: {
  items: { label: string; to?: string }[];
}) {
  return (
    <nav className="mb-6 flex flex-wrap items-center gap-1 text-sm text-slate-500">
      {items.map((it, i) => (
        <span key={i} className="flex items-center gap-1">
          {it.to ? (
            <Link to={it.to} className="hover:text-slate-300">
              {it.label}
            </Link>
          ) : (
            <span className="text-slate-300">{it.label}</span>
          )}
          {i < items.length - 1 && (
            <IconChevron width={14} height={14} className="text-slate-700" />
          )}
        </span>
      ))}
    </nav>
  );
}

/** Standard page header with a title, optional description, and right-aligned actions. */
export function PageHeader({
  title,
  description,
  icon,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="flex items-start gap-3">
        {icon && (
          <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-300 ring-1 ring-inset ring-indigo-500/25">
            {icon}
          </div>
        )}
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-100">
            {title}
          </h1>
          {description && (
            <p className="mt-1 max-w-2xl text-sm text-slate-400">{description}</p>
          )}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

/** A compact metric tile for module dashboards. */
export function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-100">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}
