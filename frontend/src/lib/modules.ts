// Registry of LENS modules. "Structured Hunts" is live; the rest are roadmap
// placeholders. Clients are global and shared across every module.
export type ModuleStatus = "live" | "soon";

export interface ModuleDef {
  id: string;
  name: string;
  path: string;
  status: ModuleStatus;
  tagline: string;
  description: string;
  capabilities: string[];
}

export const MODULES: ModuleDef[] = [
  {
    id: "structured-hunts",
    name: "Structured Hunts",
    path: "/structured-hunts",
    status: "live",
    tagline: "Methodology-driven hunt findings engine",
    description:
      "Run a planned hunt end to end: ingest the methodology and CSV result sets, " +
      "produce evidence-only findings in your approved format, correlate entities " +
      "across datasets, and generate a client-ready DOCX report.",
    capabilities: [
      "Methodology comprehension before analysis",
      "Analyst → Reviewer → QA pipeline (local LLMs)",
      "Evidence-only findings with MITRE mapping",
      "Cross-dataset correlation & IOC tables",
      "Bilingual DOCX reports (EN/ES)",
    ],
  },
  {
    id: "unstructured-hunts",
    name: "Unstructured Hunts",
    path: "/modules/unstructured-hunts",
    status: "soon",
    tagline: "Exploratory, hypothesis-free hunting",
    description:
      "Sweep raw telemetry without a predefined methodology — let the engine surface " +
      "anomalies and candidate leads for an analyst to pursue.",
    capabilities: [
      "Anomaly surfacing across raw datasets",
      "Lead generation & triage queue",
      "Promote leads into a Structured Hunt",
      "Same evidence-only discipline",
    ],
  },
  {
    id: "threat-reviews",
    name: "Threat Reviews",
    path: "/modules/threat-reviews",
    status: "soon",
    tagline: "Posture & detection-coverage reviews",
    description:
      "Periodic security-posture and detection-coverage reviews per client, with " +
      "tracked findings, remediation status, and trend over time.",
    capabilities: [
      "Detection coverage vs. MITRE ATT&CK",
      "Tracked findings with remediation state",
      "Posture trend across review cycles",
      "Executive review report",
    ],
  },
  {
    id: "intel-weekly",
    name: "Intel Weekly Reports",
    path: "/modules/intel-weekly",
    status: "soon",
    tagline: "Curated weekly threat-intel briefings",
    description:
      "Generate curated weekly threat-intelligence briefings tailored to each client's " +
      "sector, footprint, and prior findings.",
    capabilities: [
      "Per-client relevance filtering",
      "Sector & footprint tailoring",
      "Links to prior validated findings",
      "Bilingual briefing export",
    ],
  },
];

export const getModule = (id: string) => MODULES.find((m) => m.id === id);
