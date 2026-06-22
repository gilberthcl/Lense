import { type ComponentType, type SVGProps } from "react";
import { Link } from "react-router-dom";
import { getModule } from "../lib/modules";
import { PageHeader } from "../components/Layout";
import { Button, Card } from "../components/ui";
import { IconIntel, IconReviews, IconUnstructured } from "../components/icons";

const ICONS: Record<string, ComponentType<SVGProps<SVGSVGElement>>> = {
  "unstructured-hunts": IconUnstructured,
  "threat-reviews": IconReviews,
  "intel-weekly": IconIntel,
};

export default function ModulePlaceholder({ moduleId }: { moduleId: string }) {
  const mod = getModule(moduleId);
  if (!mod) return <div className="text-slate-500">Unknown module.</div>;
  const Icon = ICONS[mod.id];

  return (
    <div>
      <PageHeader
        icon={Icon ? <Icon width={22} height={22} /> : undefined}
        title={
          <span className="flex items-center gap-3">
            {mod.name}
            <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-0.5 text-xs font-medium text-amber-300">
              Coming soon
            </span>
          </span>
        }
        description={mod.description}
      />

      <Card className="mb-6 p-6">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Planned capabilities
        </p>
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {mod.capabilities.map((c, i) => (
            <li key={i} className="flex items-center gap-2 text-sm text-slate-300">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400/70" />
              {c}
            </li>
          ))}
        </ul>
      </Card>

      <Card className="flex flex-wrap items-center justify-between gap-4 p-5">
        <div>
          <p className="text-sm font-medium text-slate-200">
            This module is on the roadmap.
          </p>
          <p className="mt-0.5 text-sm text-slate-500">
            Clients you create are global — they'll be available here automatically
            when {mod.name} ships.
          </p>
        </div>
        <Link to="/structured-hunts">
          <Button variant="primary">Go to Structured Hunts</Button>
        </Link>
      </Card>
    </div>
  );
}
