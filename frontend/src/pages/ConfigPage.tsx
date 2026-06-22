import { useState } from "react";
import { PageHeader } from "../components/Layout";
import { IconConfig } from "../components/icons";
import { Card, Tabs } from "../components/ui";
import { MODULES } from "../lib/modules";
import GlobalConfig from "../components/config/GlobalConfig";
import StructuredHuntConfig from "../components/config/StructuredHuntConfig";
import JobsPanel from "../components/config/JobsPanel";

const TABS = [
  { id: "global", label: "Global" },
  { id: "jobs", label: "Jobs" },
  ...MODULES.map((m) => ({
    id: m.id,
    label: m.name,
    badge:
      m.status === "soon" ? (
        <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-slate-500">
          Soon
        </span>
      ) : undefined,
  })),
];

function ModuleConfigPlaceholder({ moduleId }: { moduleId: string }) {
  const mod = MODULES.find((m) => m.id === moduleId);
  return (
    <Card className="p-8 text-center">
      <p className="text-sm font-medium text-slate-300">
        No configuration yet for {mod?.name}.
      </p>
      <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
        This module is on the roadmap. Its configuration — prompts, models, and
        output standards — will appear here when it ships.
      </p>
    </Card>
  );
}

export default function ConfigPage() {
  const [tab, setTab] = useState("global");

  return (
    <div>
      <PageHeader
        icon={<IconConfig width={22} height={22} />}
        title="Configuration"
        description="Global platform settings and per-module standards. Clients are global; these settings apply across the platform."
      />

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "global" && <GlobalConfig />}
      {tab === "jobs" && <JobsPanel />}
      {tab === "structured-hunts" && <StructuredHuntConfig />}
      {tab !== "global" && tab !== "jobs" && tab !== "structured-hunts" && (
        <ModuleConfigPlaceholder moduleId={tab} />
      )}
    </div>
  );
}
