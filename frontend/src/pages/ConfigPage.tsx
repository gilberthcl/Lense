import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { ModuleConfig } from "../lib/types";
import { useToast } from "../components/Toast";
import { Breadcrumbs } from "../components/Layout";
import { Button, Card, PanelHeader, Spinner, Textarea } from "../components/ui";

const DESCRIPTIONS: Record<string, string> = {
  analysis_instructions:
    "The investigation protocol the engine follows when analyzing every dataset.",
  finding_format:
    "The approved structure, style, and terminology every finding must conform to.",
  finding_categories:
    "The categories a finding may be assigned — and the areas the hunt looks for.",
};

function ConfigEditor({ item }: { item: ModuleConfig }) {
  const toast = useToast();
  const [content, setContent] = useState(item.content);
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);
  const dirty = content !== item.content;

  const save = async () => {
    setSaving(true);
    try {
      const updated = await api.updateConfig(item.key, content);
      item.content = updated.content; // keep baseline in sync
      toast.success(`${item.title} saved.`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <PanelHeader
        title={item.title}
        subtitle={DESCRIPTIONS[item.key]}
        right={
          <div className="flex items-center gap-2">
            {dirty && <span className="text-xs text-amber-400">unsaved</span>}
            <Button variant="ghost" onClick={() => setOpen((o) => !o)}>
              {open ? "Collapse" : "Edit"}
            </Button>
          </div>
        }
      />
      {open && (
        <div className="space-y-3 p-4">
          <Textarea
            rows={20}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="font-mono text-xs leading-relaxed"
          />
          <div className="flex items-center gap-2">
            <Button variant="primary" onClick={save} disabled={saving || !dirty}>
              {saving ? <Spinner /> : "Save"}
            </Button>
            <Button
              variant="ghost"
              onClick={() => setContent(item.content)}
              disabled={!dirty}
            >
              Revert
            </Button>
            <span className="ml-auto text-xs text-slate-600">
              {content.length.toLocaleString()} chars
            </span>
          </div>
        </div>
      )}
    </Card>
  );
}

export default function ConfigPage() {
  const toast = useToast();
  const [items, setItems] = useState<ModuleConfig[] | null>(null);

  useEffect(() => {
    api
      .listConfig()
      .then(setItems)
      .catch((e: ApiError) => {
        toast.error(e.message);
        setItems([]);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Tenants", to: "/" }, { label: "Configuration" }]} />
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100">
          Structured Threat Hunt — Configuration
        </h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-400">
          Global guides and standards that drive the analysis engine. These are
          shared across all clients; per-hunt methodology is provided when you
          start a hunt. Edits take effect on the next analysis run.
        </p>
      </div>

      {items === null ? (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Spinner /> Loading…
        </div>
      ) : items.length === 0 ? (
        <p className="text-sm text-slate-500">No configuration available.</p>
      ) : (
        <div className="space-y-4">
          {items.map((it) => (
            <ConfigEditor key={it.key} item={it} />
          ))}
        </div>
      )}
    </div>
  );
}
