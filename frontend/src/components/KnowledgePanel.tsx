import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { CreateKnowledgeInput, DocType, KnowledgeDoc } from "../lib/types";
import { useToast } from "./Toast";
import {
  Badge,
  Button,
  Card,
  DOC_TYPES,
  docTypeLabel,
  EmptyState,
  fmtDate,
  Input,
  Label,
  PanelHeader,
  Select,
  Spinner,
  Textarea,
} from "./ui";

const CONSTITUTION: DocType[] = [
  "methodology",
  "finding_categories",
  "finding_format",
];

export default function KnowledgePanel({ tid }: { tid: string }) {
  const toast = useToast();
  const [docs, setDocs] = useState<KnowledgeDoc[] | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState<CreateKnowledgeInput>({
    doc_type: "methodology",
    title: "",
    content: "",
  });

  const load = () =>
    api
      .listKnowledge(tid)
      .then(setDocs)
      .catch((e: ApiError) => {
        toast.error(e.message);
        setDocs([]);
      });

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid]);

  const grouped = useMemo(() => {
    const map = new Map<DocType, KnowledgeDoc[]>();
    for (const d of docs ?? []) {
      const arr = map.get(d.doc_type) ?? [];
      arr.push(d);
      map.set(d.doc_type, arr);
    }
    return map;
  }, [docs]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) return toast.error("Title is required.");
    if (!form.content.trim()) return toast.error("Content is required.");
    setSubmitting(true);
    try {
      await api.createKnowledge(tid, {
        doc_type: form.doc_type,
        title: form.title.trim(),
        content: form.content,
      });
      toast.success("Document added.");
      setForm({ doc_type: form.doc_type, title: "", content: "" });
      setShowForm(false);
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to add document.");
    } finally {
      setSubmitting(false);
    }
  };

  const onDelete = async (doc: KnowledgeDoc) => {
    if (!confirm(`Delete "${doc.title}"?`)) return;
    try {
      await api.deleteKnowledge(tid, doc.id);
      toast.success("Document deleted.");
      setDocs((prev) => (prev ? prev.filter((d) => d.id !== doc.id) : prev));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to delete.");
    }
  };

  return (
    <Card>
      <PanelHeader
        title="Knowledge Base"
        subtitle="The methodology, finding categories & finding format docs form the hunt constitution"
        right={
          <Button onClick={() => setShowForm((s) => !s)}>
            {showForm ? "Close" : "+ Add Doc"}
          </Button>
        }
      />

      {showForm && (
        <form
          onSubmit={onSubmit}
          className="space-y-3 border-b border-slate-800 bg-slate-950/40 p-4"
        >
          <div>
            <Label>Doc Type</Label>
            <Select
              value={form.doc_type}
              onChange={(e) =>
                setForm((f) => ({ ...f, doc_type: e.target.value as DocType }))
              }
            >
              {DOC_TYPES.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                  {d.constitution ? "  ★ constitution" : ""}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label>Title</Label>
            <Input
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder="e.g. Standard hunt methodology"
            />
          </div>
          <div>
            <Label>Content</Label>
            <Textarea
              rows={6}
              value={form.content}
              onChange={(e) =>
                setForm((f) => ({ ...f, content: e.target.value }))
              }
              placeholder="Markdown / plain text…"
              className="font-mono text-xs"
            />
          </div>
          <Button type="submit" variant="primary" disabled={submitting}>
            {submitting ? <Spinner /> : "Save Document"}
          </Button>
        </form>
      )}

      <div className="p-4">
        {docs === null ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> Loading…
          </div>
        ) : docs.length === 0 ? (
          <EmptyState>
            No knowledge documents yet. Add methodology, finding categories, and
            finding format to define this tenant's hunt constitution.
          </EmptyState>
        ) : (
          <div className="space-y-5">
            {DOC_TYPES.map((dt) => {
              const list = grouped.get(dt.value);
              if (!list || list.length === 0) return null;
              return (
                <div key={dt.value}>
                  <div className="mb-2 flex items-center gap-2">
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                      {docTypeLabel(dt.value)}
                    </h4>
                    {CONSTITUTION.includes(dt.value) && (
                      <Badge className="border border-indigo-800 bg-indigo-950 text-indigo-300">
                        constitution
                      </Badge>
                    )}
                  </div>
                  <ul className="space-y-1.5">
                    {list.map((doc) => (
                      <li
                        key={doc.id}
                        className="flex items-center justify-between gap-3 rounded border border-slate-800 bg-slate-950/40 px-3 py-2"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm text-slate-200">
                            {doc.title}
                          </p>
                          <p className="text-xs text-slate-600">
                            {fmtDate(doc.created_at)}
                          </p>
                        </div>
                        <Button
                          variant="danger"
                          className="shrink-0 px-2 py-1 text-xs"
                          onClick={() => onDelete(doc)}
                        >
                          Delete
                        </Button>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </Card>
  );
}
