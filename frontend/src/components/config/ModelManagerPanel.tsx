import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { CatalogModel, InstalledModel, PullStatus } from "../../lib/types";
import { useToast } from "../Toast";
import { Badge, Button, Card, EmptyState, fmtBytes, PanelHeader, Spinner } from "../ui";

/** Sable assistant identity: name, model, and icon. */
function SableConfig({ installed }: { installed: InstalledModel[] | null }) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [model, setModel] = useState("");
  const [savedName, setSavedName] = useState("");
  const [iconV, setIconV] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.sableIdentity().then((r) => { setName(r.name); setSavedName(r.name); setModel(r.model); });
  }, []);

  const saveName = async () => {
    try {
      await api.updatePlatform({ assistant_name: name.trim() || "Sable" });
      setSavedName(name.trim() || "Sable");
      toast.success("Assistant name saved.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Save failed.");
    }
  };
  const saveModel = async (m: string) => {
    setModel(m);
    try {
      await api.updateAiEngine({ assistant_model: m });
      toast.success("Sable's model updated.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Save failed.");
    }
  };
  const uploadIcon = async (f?: File) => {
    if (!f) return;
    try {
      await api.uploadSableIcon(f);
      setIconV((v) => v + 1);
      toast.success("Icon updated.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Upload failed.");
    }
  };

  const options = (installed ?? []).filter((m) => m.allowed || m.name === model);

  return (
    <Card className="mb-4">
      <PanelHeader
        title="Sable assistant"
        subtitle="Name, icon, and model for the in-app cybersecurity assistant (isolated from client data)"
      />
      <div className="flex flex-wrap items-end gap-4 p-4">
        <div className="flex items-center gap-3">
          <img
            src={api.sableIconUrl(iconV)}
            alt="icon"
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.visibility = "hidden"; }}
            className="h-12 w-12 rounded-full border border-slate-700 bg-slate-800 object-cover"
          />
          <input ref={fileRef} type="file" accept="image/*" className="hidden"
            onChange={(e) => uploadIcon(e.target.files?.[0])} />
          <Button variant="ghost" className="text-xs" onClick={() => fileRef.current?.click()}>
            Upload icon
          </Button>
        </div>
        <div>
          <label className="block text-[11px] uppercase tracking-wide text-slate-500">Name</label>
          <div className="mt-1 flex gap-2">
            <input value={name} onChange={(e) => setName(e.target.value)}
              className="w-40 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
            <Button variant="ghost" disabled={name.trim() === savedName} onClick={saveName}>Save</Button>
          </div>
          <p className="mt-1 text-[11px] text-slate-600">Launcher reads “Ask {savedName || "Sable"}”.</p>
        </div>
        <div>
          <label className="block text-[11px] uppercase tracking-wide text-slate-500">Model</label>
          <select value={model} onChange={(e) => saveModel(e.target.value)}
            className="mt-1 w-72 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100">
            {!options.some((o) => o.name === model) && model && <option value={model}>{model}</option>}
            {options.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
          </select>
          <p className="mt-1 text-[11px] text-slate-600">Any installed model — Sable sees no client data.</p>
        </div>
      </div>
    </Card>
  );
}

const KIND_BADGE: Record<string, string> = {
  cyber: "border border-indigo-800 bg-indigo-950 text-indigo-300",
  generalist: "border border-slate-700 bg-slate-800 text-slate-300",
  embed: "border border-emerald-800 bg-emerald-950 text-emerald-300",
};

/**
 * In-app model manager. Install vetted cybersecurity models, see what's
 * installed (size, compliance, which client uses it), and remove safely.
 * GGUF-only via Ollama — no executable model code, no CLI.
 */
export default function ModelManagerPanel() {
  const toast = useToast();
  const [catalog, setCatalog] = useState<CatalogModel[]>([]);
  const [installed, setInstalled] = useState<InstalledModel[] | null>(null);
  const [pulls, setPulls] = useState<Record<string, PullStatus>>({});
  const [custom, setCustom] = useState("");
  const timer = useRef<number | null>(null);

  const loadInstalled = () =>
    api.installedModels().then((r) => setInstalled(r.models)).catch(() => setInstalled([]));

  useEffect(() => {
    api.modelCatalog().then((r) => setCatalog(r.models)).catch(() => setCatalog([]));
    loadInstalled();
    // Poll pull progress + installed list while anything is downloading.
    timer.current = window.setInterval(async () => {
      try {
        const r = await api.pullStatus();
        setPulls(r.pulls);
        if (Object.values(r.pulls).some((p) => p.done)) loadInstalled();
      } catch {
        /* ignore */
      }
    }, 2000);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, []);

  const installedNames = new Set((installed ?? []).map((m) => m.name));

  const pull = async (ref: string) => {
    try {
      await api.pullModel(ref);
      toast.success(`Installing ${ref}…`);
      setPulls((p) => ({ ...p, [ref]: { status: "queued", pct: 0, done: false, error: null } }));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Install failed.");
    }
  };

  const remove = async (m: InstalledModel) => {
    if (!window.confirm(`Remove ${m.name}? This frees disk; shared weights are kept if another model uses them.`)) return;
    try {
      await api.removeModel(m.name);
      toast.success(`Removed ${m.name}.`);
      loadInstalled();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Remove failed.");
    }
  };

  const pullRow = (ref: string) => {
    const p = pulls[ref];
    if (!p || p.done) return null;
    return (
      <div className="mt-1 flex items-center gap-2">
        <div className="h-1.5 w-24 overflow-hidden rounded bg-slate-800">
          <div className="h-full bg-indigo-500" style={{ width: `${Math.max(3, p.pct ?? 0)}%` }} />
        </div>
        <span className="font-mono text-[10px] text-slate-500">{p.status} {p.pct != null ? `${p.pct}%` : ""}</span>
      </div>
    );
  };

  return (
    <>
      <SableConfig installed={installed} />

      {/* Catalog — vetted, one-click install */}
      <Card className="mb-4">
        <PanelHeader
          title="Add a model"
          subtitle="Vetted, provenance-checked cybersecurity & generalist models — GGUF, runs fully local, no CLI"
        />
        <div className="grid grid-cols-1 gap-2 p-4 sm:grid-cols-2">
          {catalog.map((m) => {
            const isInstalled = installedNames.has(m.ref) || installedNames.has(m.name);
            const busy = pulls[m.ref] && !pulls[m.ref].done;
            return (
              <div key={m.key} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-sm font-medium text-slate-200">{m.name}</span>
                      <Badge className={KIND_BADGE[m.kind] ?? KIND_BADGE.generalist}>{m.kind}</Badge>
                      {m.recommended && (
                        <Badge className="border border-amber-800 bg-amber-950 text-amber-300">recommended</Badge>
                      )}
                    </div>
                    <p className="mt-0.5 text-[11px] text-slate-500">{m.params} · ~{m.approx_gb} GB · {m.origin}</p>
                    <p className="mt-1 text-xs text-slate-400">{m.focus}</p>
                    {m.note && <p className="mt-1 text-[11px] text-slate-600">{m.note}</p>}
                    {pullRow(m.ref)}
                  </div>
                  {isInstalled ? (
                    <Badge className="shrink-0 border border-emerald-800 bg-emerald-950 text-emerald-300">installed</Badge>
                  ) : (
                    <Button variant="ghost" className="shrink-0 px-2 py-1 text-xs" disabled={!!busy} onClick={() => pull(m.ref)}>
                      {busy ? <Spinner /> : "Install"}
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        {/* Custom (power-user) install — still compliance-gated server-side */}
        <div className="border-t border-slate-800 p-4">
          <p className="mb-1.5 text-[11px] uppercase tracking-wide text-slate-500">Custom install (advanced)</p>
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              placeholder="ollama name or hf.co/<org>/<repo>-GGUF"
              className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100"
            />
            <Button variant="ghost" disabled={!custom.trim()} onClick={() => { pull(custom.trim()); setCustom(""); }}>
              Install
            </Button>
          </div>
          <p className="mt-1 text-[11px] text-slate-600">
            GGUF only (no executable model code). Compliance-checked server-side; unverified provenance is refused.
          </p>
        </div>
      </Card>

      {/* Installed */}
      <Card>
        <PanelHeader
          title="Installed models"
          subtitle="On this machine — remove unused ones to free disk"
          right={<Button variant="ghost" onClick={loadInstalled}>Refresh</Button>}
        />
        <div className="p-4">
          {installed === null ? (
            <div className="flex items-center gap-2 text-sm text-slate-500"><Spinner /> Loading…</div>
          ) : installed.length === 0 ? (
            <EmptyState>No models installed, or Ollama is unreachable.</EmptyState>
          ) : (
            <ul className="space-y-1.5">
              {installed.map((m) => (
                <li key={m.name} className="flex flex-wrap items-center gap-2 rounded border border-slate-800 bg-slate-950/40 px-3 py-2">
                  <span className="font-mono text-xs text-slate-200">{m.name}</span>
                  <span className="text-[11px] text-slate-500">{fmtBytes(m.size)}</span>
                  {m.kind && <Badge className={KIND_BADGE[m.kind] ?? KIND_BADGE.generalist}>{m.kind}</Badge>}
                  {!m.allowed && (
                    <span title={m.reason}>
                      <Badge className="border border-rose-800 bg-rose-950 text-rose-300">non-compliant</Badge>
                    </span>
                  )}
                  {m.is_default && <Badge className="border border-slate-700 bg-slate-800 text-slate-400">default</Badge>}
                  {m.assigned_to && <span className="text-[11px] text-indigo-300">client: {m.assigned_to}</span>}
                  <div className="ml-auto">
                    {m.protected || m.is_default || m.assigned_to ? (
                      <span className="text-[11px] text-slate-600" title={
                        m.protected ? "Required (embeddings)" : m.is_default ? "Global default" : `In use by ${m.assigned_to}`
                      }>locked</span>
                    ) : (
                      <Button variant="danger" className="px-2 py-1 text-xs" onClick={() => remove(m)}>Remove</Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>
    </>
  );
}
