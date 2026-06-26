import { useState } from "react";
import { api, ApiError } from "../lib/api";
import type { SanitizeResult } from "../lib/types";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, PanelHeader, Spinner, Textarea } from "../components/ui";

/**
 * Tools — an analyst toolbox. Tool 1: Data Sanitizer & Anonymizer.
 * (More tools, e.g. a smart AI decoder, can be added as sibling cards.)
 */
export default function ToolsPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Tools</h1>
        <p className="text-sm text-slate-500">Handy analyst utilities.</p>
      </div>
      <DataSanitizer />
    </div>
  );
}

function DataSanitizer() {
  const toast = useToast();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SanitizeResult | null>(null);

  const run = async () => {
    if (!input.trim()) {
      toast.error("Paste something to sanitize.");
      return;
    }
    setBusy(true);
    setResult(null);
    try {
      setResult(await api.sanitizeText(input));
    } catch (e) {
      toast.error((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const copy = () => {
    if (result) {
      navigator.clipboard.writeText(result.sanitized);
      toast.success("Sanitized text copied.");
    }
  };

  return (
    <Card>
      <PanelHeader
        title="Data Sanitizer & Anonymizer"
        subtitle="Anonymize internal/proprietary entities and redact secrets in any text, command line, script, or JSON — public IPs and external domains are preserved"
        right={
          <Button onClick={run} disabled={busy}>
            {busy ? <Spinner /> : "Sanitize"}
          </Button>
        }
      />
      <div className="space-y-4 p-4">
        <Textarea
          rows={8}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Paste a command line, script, log line, JSON, finding text… anything. The AI finds internal usernames, hostnames, domains, emails, private IPs, paths — and redacts passwords/keys/tokens."
          className="font-mono text-xs"
        />

        {result && (
          <>
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Sanitized output</p>
                <Button variant="ghost" className="px-2 py-1 text-xs" onClick={copy}>Copy</Button>
              </div>
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded border border-slate-800 bg-slate-950 p-3 font-mono text-xs text-slate-200">
                {result.sanitized}
              </pre>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Replaced ({result.replacements.length})
                </p>
                {result.replacements.length === 0 ? (
                  <p className="text-sm text-slate-600">Nothing sensitive detected.</p>
                ) : (
                  <ul className="space-y-1 text-[11px]">
                    {result.replacements.map((r, i) => (
                      <li key={i} className="flex flex-wrap items-center gap-1.5">
                        <span className="font-mono text-rose-300 line-through">{r.value}</span>
                        <span className="text-slate-600">→</span>
                        <span className="font-mono text-emerald-300">{r.placeholder}</span>
                        <Badge className="border border-slate-700 bg-slate-800 text-slate-400">{r.type}</Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Kept as-is ({result.kept.length})
                </p>
                {result.kept.length === 0 ? (
                  <p className="text-sm text-slate-600">—</p>
                ) : (
                  <ul className="space-y-1 text-[11px] text-slate-400">
                    {result.kept.map((k, i) => (
                      <li key={i}>
                        <span className="font-mono text-slate-300">{k.value}</span> — {k.reason}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
            <p className="text-[11px] text-slate-600">
              AI-assisted detection with a hard rule: public IPs and known external domains are never
              altered. Review before sharing — confirm nothing internal slipped through.
            </p>
          </>
        )}
      </div>
    </Card>
  );
}
