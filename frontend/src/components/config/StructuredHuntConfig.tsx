import { useEffect, useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { CategoryDef, ModuleConfig } from "../../lib/types";
import { useToast } from "../Toast";
import { Button, Card, CategoryBadge, PanelHeader, Spinner, Textarea } from "../ui";

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
      item.content = updated.content;
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
            <Button variant="ghost" onClick={() => setContent(item.content)} disabled={!dirty}>
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

function CategoriesReference({ categories }: { categories: CategoryDef[] }) {
  return (
    <Card>
      <PanelHeader
        title="Finding Categories (canonical)"
        subtitle="The machine-usable category contract — every finding is assigned one of these."
      />
      <div className="grid grid-cols-1 gap-2 p-4 sm:grid-cols-2">
        {categories.map((c) => (
          <div key={c.key} className="rounded border border-slate-800 bg-slate-950/40 p-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <CategoryBadge category={c.key} />
              <span className="text-xs text-slate-500">{c.label_es}</span>
            </div>
            <p className="mt-1 text-xs text-slate-400">{c.definition}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}

export default function StructuredHuntConfig() {
  const toast = useToast();
  const [items, setItems] = useState<ModuleConfig[] | null>(null);
  const [categories, setCategories] = useState<CategoryDef[]>([]);

  useEffect(() => {
    api
      .listConfig()
      .then(setItems)
      .catch((e: ApiError) => {
        toast.error(e.message);
        setItems([]);
      });
    api
      .listCategories()
      .then((r) => setCategories(r.categories))
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (items === null)
    return (
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Spinner /> Loading…
      </div>
    );

  return (
    <div className="space-y-4">
      <p className="max-w-3xl text-sm text-slate-400">
        Guides that drive the Structured Hunts analysis engine. Shared across all
        clients; per-hunt methodology is provided when you start a hunt. Edits take
        effect on the next analysis run.
      </p>
      {items.map((it) => (
        <ConfigEditor key={it.key} item={it} />
      ))}
      {categories.length > 0 && <CategoriesReference categories={categories} />}
    </div>
  );
}
