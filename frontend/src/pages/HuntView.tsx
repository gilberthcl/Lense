import { useEffect, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import type { Hunt, ReportLang, Tenant } from "../lib/types";
import { useToast } from "../components/Toast";
import { Breadcrumbs } from "../components/Layout";
import { getModule, moduleClientBase } from "../lib/modules";
import { Badge, Button, Select, Spinner } from "../components/ui";
import DatasetsPanel from "../components/DatasetsPanel";
import FindingsPanel from "../components/FindingsPanel";
import CorrelationsPanel from "../components/CorrelationsPanel";
import MethodologyPanel from "../components/MethodologyPanel";

export default function HuntView() {
  const { tid, hid } = useParams<{ tid: string; hid: string }>();
  const { pathname } = useLocation();
  const toast = useToast();
  // If we arrived under a module (e.g. /structured-hunts/clients/...), keep that context.
  const mod = pathname.startsWith("/structured-hunts/")
    ? getModule("structured-hunts")
    : undefined;
  const clientBase = mod ? moduleClientBase(mod) : "/clients";
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [hunt, setHunt] = useState<Hunt | null>(null);
  // Bumping this key tells the Findings/Correlations panels to reload.
  const [findingsKey, setFindingsKey] = useState(0);
  const [reportLang, setReportLang] = useState<ReportLang>("en");
  const [downloading, setDownloading] = useState(false);

  const onGenerateReport = async () => {
    if (!tid || !hid) return;
    setDownloading(true);
    try {
      await api.downloadReport(tid, hid, reportLang);
      toast.success("Report generated.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Report generation failed.");
    } finally {
      setDownloading(false);
    }
  };

  const loadHunt = () => {
    if (!tid || !hid) return;
    api
      .getHunt(tid, hid)
      .then(setHunt)
      .catch((e: ApiError) => toast.error(e.message));
  };

  useEffect(() => {
    if (!tid || !hid) return;
    api.getTenant(tid).then(setTenant).catch(() => undefined);
    loadHunt();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid, hid]);

  if (!tid || !hid) return null;

  return (
    <div>
      <Breadcrumbs
        items={
          mod
            ? [
                { label: mod.name, to: mod.path },
                { label: tenant?.name ?? "…", to: `${clientBase}/${tid}` },
                { label: hunt?.name ?? "…" },
              ]
            : [
                { label: "Clients", to: "/clients" },
                { label: tenant?.name ?? "…", to: `/clients/${tid}` },
                { label: hunt?.name ?? "…" },
              ]
        }
      />

      <div className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold text-slate-100">
            {hunt?.name ?? <Spinner />}
          </h1>
          {hunt && (
            <Badge className="border border-slate-700 bg-slate-800 text-slate-300">
              {hunt.status}
            </Badge>
          )}
          <div className="ml-auto flex items-center gap-2">
            <Select
              aria-label="Report language"
              value={reportLang}
              onChange={(e) => setReportLang(e.target.value as ReportLang)}
              className="w-auto"
            >
              <option value="en">English</option>
              <option value="es">Español</option>
            </Select>
            <Button
              variant="primary"
              onClick={onGenerateReport}
              disabled={downloading || !hunt}
            >
              {downloading ? <Spinner /> : "Generate Report (.docx)"}
            </Button>
          </div>
        </div>
        {hunt?.objective && (
          <p className="mt-2 max-w-3xl text-sm text-slate-400">{hunt.objective}</p>
        )}
      </div>

      <div className="grid grid-cols-1 gap-6">
        <MethodologyPanel tid={tid} hid={hid} hunt={hunt} onRefresh={loadHunt} />
        <DatasetsPanel
          tid={tid}
          hid={hid}
          onAnalysisComplete={() => setFindingsKey((k) => k + 1)}
        />
        <FindingsPanel tid={tid} hid={hid} reloadKey={findingsKey} />
        <CorrelationsPanel tid={tid} hid={hid} reloadKey={findingsKey} />
      </div>
    </div>
  );
}
