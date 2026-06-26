import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { AiEngineConfig, DbHealth, GlobalConfig, PlatformConfig } from "../../lib/types";
import { useToast } from "../Toast";
import { BrandLogo } from "../BrandLogo";
import { Badge, Button, Card, fmtBytes, Input, Label, PanelHeader, Select, Spinner } from "../ui";

const PIN_LEN = 6;

const AI_FIELDS: { key: keyof AiEngineConfig; label: string; hint?: string }[] = [
  { key: "base_url", label: "Ollama Base URL", hint: "Local endpoint — never a cloud host" },
  { key: "analyst_model", label: "Analyst Model", hint: "Primary findings analyst" },
  { key: "reviewer_model", label: "Reviewer Model", hint: "False-positive reduction" },
  { key: "qa_model", label: "QA Model", hint: "Format / consistency check" },
  { key: "embed_model", label: "Embeddings Model", hint: "RAG — must stay 768-dim" },
];

export default function GlobalConfig() {
  const toast = useToast();
  const [cfg, setCfg] = useState<GlobalConfig | null>(null);
  const [ai, setAi] = useState<AiEngineConfig | null>(null);
  const [platform, setPlatform] = useState<PlatformConfig | null>(null);
  const [savingAi, setSavingAi] = useState(false);
  const [savingPlatform, setSavingPlatform] = useState(false);
  const [logoVer, setLogoVer] = useState(0);
  const [models, setModels] = useState<string[]>([]);
  const logoRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.ollamaModels().then((r) => setModels(r.models)).catch(() => undefined);
  }, []);

  // Change-PIN state
  const [curPin, setCurPin] = useState("");
  const [newPin, setNewPin] = useState("");
  const [changingPin, setChangingPin] = useState(false);

  // Maintenance state
  const [health, setHealth] = useState<DbHealth | null>(null);
  const [scanning, setScanning] = useState(false);
  const [cleaning, setCleaning] = useState(false);

  const scan = async () => {
    setScanning(true);
    try {
      setHealth(await api.dbHealthScan());
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Scan failed.");
    } finally {
      setScanning(false);
    }
  };

  const clean = async () => {
    if (!window.confirm("Delete orphaned files and clear stuck jobs? This removes upload files no longer referenced by the database."))
      return;
    setCleaning(true);
    try {
      const r = await api.dbHealthClean();
      toast.success(`Removed ${r.removed_files} files (${fmtBytes(r.freed_bytes)}), cleared ${r.cleared_jobs} jobs.`);
      await scan();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Cleanup failed.");
    } finally {
      setCleaning(false);
    }
  };

  useEffect(() => {
    api
      .getGlobalConfig()
      .then((c) => {
        setCfg(c);
        setAi(c.ai_engine);
        setPlatform(c.platform);
      })
      .catch((e: ApiError) => toast.error(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveAi = async () => {
    if (!ai) return;
    setSavingAi(true);
    try {
      const saved = await api.updateAiEngine(ai);
      setAi(saved);
      toast.success("AI engine settings saved.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Save failed.");
    } finally {
      setSavingAi(false);
    }
  };

  const savePlatform = async () => {
    if (!platform) return;
    setSavingPlatform(true);
    try {
      const saved = await api.updatePlatform(platform);
      setPlatform(saved);
      toast.success("Platform settings saved.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Save failed.");
    } finally {
      setSavingPlatform(false);
    }
  };

  const uploadLogo = async (file?: File) => {
    if (!file) return;
    try {
      await api.uploadPlatformLogo(file);
      setLogoVer((v) => v + 1);
      toast.success("Platform logo updated. It appears across the platform.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Logo upload failed.");
    }
  };

  const changePin = async () => {
    if (curPin.length !== PIN_LEN || newPin.length !== PIN_LEN)
      return toast.error(`PINs must be exactly ${PIN_LEN} characters.`);
    setChangingPin(true);
    try {
      await api.authChange(curPin, newPin);
      setCurPin("");
      setNewPin("");
      toast.success("Access PIN changed.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not change PIN.");
    } finally {
      setChangingPin(false);
    }
  };

  const resetAi = () => cfg && setAi(cfg.ai_defaults);

  if (!ai || !platform)
    return (
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Spinner /> Loading…
      </div>
    );

  return (
    <div className="space-y-4">
      {/* Platform */}
      <Card>
        <PanelHeader title="Platform" subtitle="Cross-module defaults" />
        <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Label>Platform Logo</Label>
            <div className="flex items-center gap-3">
              <BrandLogo className="h-12 w-12 rounded-lg ring-1 ring-slate-700" version={logoVer} />
              <input
                ref={logoRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => uploadLogo(e.target.files?.[0])}
              />
              <Button variant="ghost" onClick={() => logoRef.current?.click()}>
                Upload Logo
              </Button>
              <p className="text-xs text-slate-600">Shown in the sidebar and on the lock screen.</p>
            </div>
          </div>
          <div>
            <Label>Platform Name</Label>
            <Input
              value={platform.platform_name}
              onChange={(e) => setPlatform({ ...platform, platform_name: e.target.value })}
            />
          </div>
          <div>
            <Label>Default Report Language</Label>
            <Select
              value={platform.default_report_language}
              onChange={(e) =>
                setPlatform({ ...platform, default_report_language: e.target.value })
              }
            >
              <option value="English">English</option>
              <option value="Spanish">Spanish</option>
            </Select>
          </div>
          <div className="sm:col-span-2">
            <Button variant="primary" onClick={savePlatform} disabled={savingPlatform}>
              {savingPlatform ? <Spinner /> : "Save Platform Settings"}
            </Button>
          </div>
        </div>
      </Card>

      {/* AI Engine */}
      <Card>
        <PanelHeader
          title="AI Engine (Ollama)"
          subtitle="Local LLM endpoint and per-role models — changes apply on the next run"
          right={
            <Button variant="ghost" onClick={resetAi}>
              Reset to defaults
            </Button>
          }
        />
        <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2">
          {AI_FIELDS.map((f) => {
            const val = String(ai[f.key] ?? "");
            const isModel = f.key.endsWith("_model");
            const isEmbedRole = f.key === "embed_model";
            // Generation roles can't use embedding models; the embeddings role wants them.
            const pool = isEmbedRole ? models : models.filter((m) => !m.toLowerCase().includes("embed"));
            const opts = isModel ? Array.from(new Set([val, ...pool].filter(Boolean))) : [];
            return (
              <div key={f.key}>
                <Label>{f.label}</Label>
                {isModel && models.length > 0 ? (
                  <Select
                    value={val}
                    onChange={(e) => setAi({ ...ai, [f.key]: e.target.value })}
                    className="font-mono"
                  >
                    {opts.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </Select>
                ) : (
                  <Input
                    value={val}
                    onChange={(e) => setAi({ ...ai, [f.key]: e.target.value })}
                    className="font-mono"
                  />
                )}
                {f.hint && <p className="mt-1 text-xs text-slate-600">{f.hint}</p>}
              </div>
            );
          })}
          <div>
            <Label>Temperature</Label>
            <Input
              type="number"
              step="0.05"
              min="0"
              max="1"
              value={ai.temperature}
              onChange={(e) => setAi({ ...ai, temperature: Number(e.target.value) })}
              className="font-mono"
            />
            <p className="mt-1 text-xs text-slate-600">Low (~0.2) for analytical work</p>
          </div>
          <div>
            <Label>Request Timeout (s)</Label>
            <Input
              type="number"
              min="30"
              value={ai.timeout}
              onChange={(e) => setAi({ ...ai, timeout: Number(e.target.value) })}
              className="font-mono"
            />
          </div>
          <div>
            <Label>Max output tokens (num_predict)</Label>
            <Input
              type="number"
              min="256"
              max="16384"
              value={ai.num_predict ?? 4096}
              onChange={(e) => setAi({ ...ai, num_predict: Number(e.target.value) })}
              className="font-mono"
            />
            <p className="mt-1 text-xs text-slate-600">Caps generation so JSON can't truncate</p>
          </div>
          <div>
            <Label>Keep model warm (keep_alive)</Label>
            <Input
              value={ai.keep_alive ?? "30m"}
              onChange={(e) => setAi({ ...ai, keep_alive: e.target.value })}
              className="font-mono"
            />
            <p className="mt-1 text-xs text-slate-600">e.g. 30m — avoids reloading between datasets</p>
          </div>
          <div className="sm:col-span-2">
            <label className="flex items-start gap-2 rounded border border-indigo-500/20 bg-indigo-500/[0.04] px-3 py-2 text-sm text-slate-300">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={ai.single_model_pipeline ?? true}
                onChange={(e) => setAi({ ...ai, single_model_pipeline: e.target.checked })}
              />
              <span>
                <span className="font-medium">Single-model pipeline</span> — run Reviewer &amp; QA on
                the Analyst model.{" "}
                <span className="text-slate-500">
                  Strongly recommended on ≤32 GB: avoids Ollama reloading a second large model on every
                  dataset (the main cause of slow/failed runs). Uncheck only if you have RAM for two
                  models at once.
                </span>
              </span>
            </label>
          </div>
          <div className="sm:col-span-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <label className="flex items-center gap-2 rounded border border-slate-800 bg-slate-950/40 px-3 py-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={ai.enable_reviewer ?? true}
                onChange={(e) => setAi({ ...ai, enable_reviewer: e.target.checked })}
              />
              <span>Reviewer stage <span className="text-slate-500">(false-positive reduction)</span></span>
            </label>
            <label className="flex items-center gap-2 rounded border border-slate-800 bg-slate-950/40 px-3 py-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={ai.enable_qa ?? true}
                onChange={(e) => setAi({ ...ai, enable_qa: e.target.checked })}
              />
              <span>QA stage <span className="text-slate-500">(format normalization)</span></span>
            </label>
            <p className="sm:col-span-2 text-xs text-slate-600">
              Each stage is a separate generation. Turning both off runs a single analyst pass — about
              3× faster on a slow box, at some quality cost. Use the per-dataset timing in the log to
              decide.
            </p>
            <label className="sm:col-span-2 flex items-start gap-2 rounded border border-slate-800 bg-slate-950/40 px-3 py-2 text-sm text-slate-300">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={ai.anonymize_training ?? false}
                onChange={(e) => setAi({ ...ai, anonymize_training: e.target.checked })}
              />
              <span>
                Anonymise training data <span className="text-slate-500">(W5)</span>
                <span className="block text-xs text-slate-500">
                  On export, replace concrete entities (hosts, users, IPs) with placeholders so the
                  per-client model learns patterns, not specific names. Optional — per-client
                  isolation already covers data safety.
                </span>
              </span>
            </label>
          </div>
          <div className="sm:col-span-2">
            <div className="mb-3 rounded border border-amber-500/20 bg-amber-500/[0.04] px-3 py-2 text-xs text-amber-300/90">
              Local-only compliance: <code>*-cloud</code> models are rejected, and
              unverified community fine-tunes should be avoided for client data.
            </div>
            <Button variant="primary" onClick={saveAi} disabled={savingAi}>
              {savingAi ? <Spinner /> : "Save AI Engine Settings"}
            </Button>
          </div>
        </div>
      </Card>

      {/* Security */}
      <Card>
        <PanelHeader title="Access PIN" subtitle="Local single-operator access — enforced by the API" />
        <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-3">
          <div>
            <Label>Current PIN</Label>
            <Input
              type="password"
              maxLength={PIN_LEN}
              value={curPin}
              onChange={(e) => setCurPin(e.target.value)}
              className="font-mono tracking-widest"
            />
          </div>
          <div>
            <Label>New PIN</Label>
            <Input
              type="password"
              maxLength={PIN_LEN}
              value={newPin}
              onChange={(e) => setNewPin(e.target.value)}
              className="font-mono tracking-widest"
            />
          </div>
          <div className="flex items-end">
            <Button variant="primary" onClick={changePin} disabled={changingPin}>
              {changingPin ? <Spinner /> : "Change PIN"}
            </Button>
          </div>
        </div>
      </Card>

      {/* Database / storage maintenance */}
      <Card>
        <PanelHeader
          title="Database & Storage Maintenance"
          subtitle="Find and remove leftovers from deleted hunts/datasets (orphaned files, stuck jobs)"
          right={
            <div className="flex gap-2">
              <Button variant="ghost" onClick={scan} disabled={scanning}>
                {scanning ? <Spinner /> : "Scan"}
              </Button>
              <Button
                variant="danger"
                onClick={clean}
                disabled={cleaning || !health || health.healthy}
              >
                {cleaning ? <Spinner /> : "Clean now"}
              </Button>
            </div>
          }
        />
        <div className="p-4">
          {!health ? (
            <p className="text-sm text-slate-500">Run a scan to check storage and jobs.</p>
          ) : (
            <div className="space-y-3 text-sm">
              <div className="flex flex-wrap gap-2 text-xs text-slate-400">
                <span>{health.counts.clients} clients</span>·
                <span>{health.counts.hunts} hunts</span>·
                <span>{health.counts.datasets} datasets</span>·
                <span>{health.counts.findings} findings</span>·
                <span>{health.counts.jobs} jobs</span>
              </div>

              {health.healthy ? (
                <Badge className="border border-emerald-800 bg-emerald-950 text-emerald-300">
                  ✓ Clean — nothing to remove
                </Badge>
              ) : (
                <ul className="space-y-2">
                  <li className="flex items-center justify-between rounded border border-slate-800 bg-slate-950/40 px-3 py-2">
                    <span className="text-slate-300">Orphaned upload files</span>
                    <span className="font-mono text-xs text-amber-300">
                      {health.orphan_files.count} · {fmtBytes(health.orphan_files.bytes)}
                    </span>
                  </li>
                  <li className="flex items-center justify-between rounded border border-slate-800 bg-slate-950/40 px-3 py-2">
                    <span className="text-slate-300">Datasets with missing files</span>
                    <span className="font-mono text-xs text-amber-300">
                      {health.missing_dataset_files.length}
                    </span>
                  </li>
                  <li className="flex items-center justify-between rounded border border-slate-800 bg-slate-950/40 px-3 py-2">
                    <span className="text-slate-300">Stuck / active jobs</span>
                    <span className="font-mono text-xs text-amber-300">
                      {health.stuck_jobs.length}
                    </span>
                  </li>
                </ul>
              )}

              {health.orphan_files.sample.length > 0 && (
                <details className="text-xs text-slate-500">
                  <summary className="cursor-pointer hover:text-slate-300">
                    Sample orphaned files
                  </summary>
                  <ul className="mt-1 max-h-40 overflow-auto font-mono">
                    {health.orphan_files.sample.map((f, i) => (
                      <li key={i} className="truncate">{f}</li>
                    ))}
                  </ul>
                </details>
              )}
              <p className="text-xs text-slate-600">
                “Clean now” deletes orphaned files, clears stuck jobs, and prunes empty folders.
                Missing-file datasets are reported only — delete those hunts manually if unwanted.
              </p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
