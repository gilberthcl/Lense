import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type { Tenant } from "../lib/types";
import { Card, EmptyState, fmtDate, Spinner } from "./ui";
import { IconClients } from "./icons";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

/** Client cards (a client = a globally shared workspace). Used by Clients + module dashboards. */
export default function ClientGrid({
  clients,
  emptyHint = "No clients yet.",
  basePath = "/clients",
}: {
  clients: Tenant[] | null;
  emptyHint?: string;
  /** Where a card links to. Module dashboards pass their own base, e.g. /structured-hunts/clients */
  basePath?: string;
}) {
  if (clients === null)
    return (
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Spinner /> Loading clients…
      </div>
    );
  if (clients.length === 0)
    return (
      <Card>
        <EmptyState>{emptyHint}</EmptyState>
      </Card>
    );
  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      {clients.map((c) => {
        const tech = [c.edr_platform, c.siem_platform, c.xdr_platform].filter(Boolean) as string[];
        const location = [c.city, c.country].filter(Boolean).join(", ");
        return (
          <Link key={c.id} to={`${basePath}/${c.id}`} className="group">
            <Card className="h-full p-6 transition-colors group-hover:border-indigo-600/70 group-hover:bg-slate-900">
              <div className="flex items-start gap-4">
                {c.logo_path ? (
                  <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-white p-1.5 ring-1 ring-slate-700">
                    <img
                      src={api.logoUrl(String(c.id))}
                      alt=""
                      className="max-h-full max-w-full object-contain"
                    />
                  </div>
                ) : (
                  <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-xl bg-indigo-500/15 text-xl font-semibold text-indigo-200 ring-1 ring-inset ring-indigo-500/30">
                    {initials(c.name) || <IconClients width={24} height={24} />}
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="truncate text-lg font-semibold text-slate-100 group-hover:text-indigo-300">
                      {c.name}
                    </h3>
                    <span className="shrink-0 rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-400">
                      {c.slug}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-sm text-slate-400">
                    {[c.sector, location].filter(Boolean).join(" · ") || "No profile yet"}
                  </p>
                  {tech.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {tech.map((t) => (
                        <span key={t} className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <p className="mt-4 border-t border-slate-800/60 pt-3 text-xs text-slate-600">
                Added {fmtDate(c.created_at)}
              </p>
            </Card>
          </Link>
        );
      })}
    </div>
  );
}
