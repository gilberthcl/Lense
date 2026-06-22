import { useEffect, useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { AiEngineConfig, GlobalConfig, PlatformConfig } from "../../lib/types";
import { useToast } from "../Toast";
import { Button, Card, Input, Label, PanelHeader, Select, Spinner } from "../ui";

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
          {AI_FIELDS.map((f) => (
            <div key={f.key}>
              <Label>{f.label}</Label>
              <Input
                value={String(ai[f.key])}
                onChange={(e) => setAi({ ...ai, [f.key]: e.target.value })}
                className="font-mono"
              />
              {f.hint && <p className="mt-1 text-xs text-slate-600">{f.hint}</p>}
            </div>
          ))}
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
    </div>
  );
}
