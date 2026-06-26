import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { AvailableModels } from "../lib/types";
import { useToast } from "./Toast";

/**
 * Per-client base-model selector (W0b) — compliance-gated. Shared by the client
 * Settings tab and the Knowledge Base → Fine-tuned model card.
 */
export default function BaseModelSelect({ tid }: { tid: string }) {
  const toast = useToast();
  const [data, setData] = useState<AvailableModels | null>(null);
  const [saving, setSaving] = useState(false);

  const load = () =>
    api.getAvailableModels(tid).then(setData).catch((e: ApiError) => toast.error(e.message));
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid]);

  const choose = async (value: string) => {
    const model = value === "__default__" ? null : value;
    setSaving(true);
    try {
      const r = await api.setBaseModel(tid, model);
      if (r.warning && !window.confirm(`${r.warning}\n\nChange the model anyway?`)) {
        await api.setBaseModel(tid, data?.current ?? null); // revert
      } else {
        toast.success(model ? `Base model set to ${model}.` : "Using the global default model.");
      }
      load();
    } catch (e) {
      toast.error((e as ApiError).message);
    } finally {
      setSaving(false);
    }
  };

  if (!data) {
    return <p className="text-xs text-slate-500">Loading installed models…</p>;
  }
  const allowed = data.models.filter((m) => m.allowed);
  const blocked = data.models.filter((m) => !m.allowed);

  return (
    <div>
      {!data.reachable && (
        <p className="mb-2 text-[11px] text-amber-300">Ollama unreachable — no installed models to show.</p>
      )}
      <select
        value={data.current ?? "__default__"}
        disabled={saving}
        onChange={(e) => choose(e.target.value)}
        className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
      >
        <option value="__default__">Global default ({data.default_model ?? "—"})</option>
        {allowed.map((m) => (
          <option key={m.name} value={m.name}>{m.name}</option>
        ))}
      </select>
      {blocked.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-[11px] uppercase tracking-wide text-slate-500">
            {blocked.length} model(s) blocked by compliance
          </summary>
          <ul className="mt-1 space-y-0.5 text-[11px] text-slate-500">
            {blocked.map((m) => (
              <li key={m.name}>
                <span className="font-mono text-rose-300">{m.name}</span> — {m.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="mt-1.5 text-[11px] text-slate-500">
        Only Western-origin, local, verified models are selectable. A promoted fine-tuned model
        overrides this base for this client's analysis.
      </p>
    </div>
  );
}
