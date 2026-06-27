import { useEffect, useState, type ComponentType, type SVGProps } from "react";
import { NavLink } from "react-router-dom";
import { api, API_BASE } from "../lib/api";
import { MODULES } from "../lib/modules";
import { BrandLogo } from "./BrandLogo";
import {
  IconClients,
  IconIntel,
  IconReviews,
  IconStructured,
  IconUnstructured,
} from "./icons";

type IconC = ComponentType<SVGProps<SVGSVGElement>>;

function IconTools(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}
      strokeLinecap="round" strokeLinejoin="round" width={18} height={18} {...props}>
      <path d="M14.7 6.3a4 4 0 0 0-5.4 5.3L3 18v3h3l6.4-6.3a4 4 0 0 0 5.3-5.4l-2.5 2.5-2.1-.6-.6-2.1z" />
    </svg>
  );
}

const MODULE_ICONS: Record<string, IconC> = {
  "structured-hunts": IconStructured,
  "unstructured-hunts": IconUnstructured,
  "threat-reviews": IconReviews,
  "intel-weekly": IconIntel,
};

function navClass(active: boolean): string {
  return [
    "group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
    active
      ? "bg-indigo-500/10 text-indigo-200 ring-1 ring-inset ring-indigo-500/30"
      : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200",
  ].join(" ");
}

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
  const color = ok === null ? "bg-slate-500" : ok ? "bg-emerald-500" : "bg-red-500";
  const label = ok === null ? "checking…" : ok ? "Backend online" : "Backend offline";
  return (
    <div className="flex items-center gap-2 px-3 py-2 text-xs text-slate-500" title={API_BASE}>
      <span className={`h-2 w-2 rounded-full ${color} ${ok ? "shadow-[0_0_8px] shadow-emerald-500/50" : ""}`} />
      <span className="truncate">{label}</span>
    </div>
  );
}

export default function Sidebar() {
  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-slate-800/80 bg-slate-900/40">
      {/* Brand — clickable, takes the user to the global home page */}
      <NavLink
        to="/"
        title="LENS home"
        className="flex items-center gap-3 px-5 py-5 transition-opacity hover:opacity-80"
      >
        <BrandLogo className="h-12 w-12 rounded-lg" iconSize={28} />
        <div className="leading-tight">
          <div className="font-mono text-base font-bold tracking-[0.25em] text-slate-100">
            LENS
          </div>
          <div className="text-[10px] uppercase tracking-wide text-slate-500">
            Threat Hunt Platform
          </div>
        </div>
      </NavLink>

      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-2">
        {/* Global entities */}
        <div className="space-y-1">
          <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-600">
            Global
          </p>
          <NavLink to="/clients" className={({ isActive }) => navClass(isActive)}>
            <IconClients className="shrink-0 text-current opacity-80" />
            <span>Clients</span>
          </NavLink>
          <NavLink to="/tools" className={({ isActive }) => navClass(isActive)}>
            <IconTools className="shrink-0 text-current opacity-80" />
            <span>Toolbox</span>
          </NavLink>
        </div>

        {/* Modules */}
        <div className="space-y-1">
          <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-600">
            Modules
          </p>
          {MODULES.map((m) => {
            const Icon = MODULE_ICONS[m.id];
            return (
              <NavLink key={m.id} to={m.path} className={({ isActive }) => navClass(isActive)}>
                {Icon && <Icon className="shrink-0 text-current opacity-80" />}
                <span className="flex-1 truncate">{m.name}</span>
                {m.status === "soon" && (
                  <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-slate-500">
                    Soon
                  </span>
                )}
              </NavLink>
            );
          })}
        </div>
      </nav>

      {/* Footer */}
      <div className="border-t border-slate-800/80 p-3">
        <HealthDot />
      </div>
    </aside>
  );
}
