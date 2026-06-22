import { Link } from "react-router-dom";
import type { Tenant } from "../lib/types";
import { Card, EmptyState, fmtDate, Spinner } from "./ui";

/** Client cards (a client = a globally shared workspace). Used by Clients + module dashboards. */
export default function ClientGrid({
  clients,
  emptyHint = "No clients yet.",
}: {
  clients: Tenant[] | null;
  emptyHint?: string;
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
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {clients.map((c) => (
        <Link key={c.id} to={`/clients/${c.id}`} className="group">
          <Card className="h-full p-4 transition-colors group-hover:border-indigo-600/70 group-hover:bg-slate-900">
            <div className="flex items-center justify-between gap-2">
              <h3 className="truncate font-semibold text-slate-100 group-hover:text-indigo-300">
                {c.name}
              </h3>
              <span className="shrink-0 rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-400">
                {c.slug}
              </span>
            </div>
            {c.context_notes ? (
              <p className="mt-2 line-clamp-2 text-xs text-slate-500">{c.context_notes}</p>
            ) : (
              <p className="mt-2 text-xs text-slate-600 italic">No context notes</p>
            )}
            <p className="mt-3 text-xs text-slate-600">Added {fmtDate(c.created_at)}</p>
          </Card>
        </Link>
      ))}
    </div>
  );
}
