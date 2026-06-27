import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { DecodeMode, SanitizeResult } from "../lib/types";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, PanelHeader, Spinner, Textarea } from "../components/ui";
import SmartDecoder from "../components/SmartDecoder";

/**
 * Tools — an analyst toolbox.
 *   Tool 1: Data Sanitizer & Anonymizer (AI).
 *   Tool 2: Smart Decoder (CyberChef-style recipe, client-side).
 */
export default function ToolsPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Tools</h1>
        <p className="text-sm text-slate-500">Handy analyst utilities.</p>
      </div>
      <DataSanitizer />
      <SmartDecoder />
    </div>
  );
}

const DECODE_OPTIONS: { value: DecodeMode; label: string }[] = [
  { value: "", label: "No decode" },
  { value: "auto", label: "Auto-detect" },
  { value: "base64", label: "Base64" },
  { value: "hex", label: "Hex" },
  { value: "url", label: "URL-encoded" },
];

function DataSanitizer() {
  const toast = useToast();
  const [input, setInput] = useState("");
  const [decode, setDecode] = useState<DecodeMode>("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [result, setResult] = useState<SanitizeResult | null>(null);

  // The output is editable so the analyst can hand-fix anything the AI missed.
  const [edited, setEdited] = useState("");
  const [find, setFind] = useState("");
  const [replace, setReplace] = useState("");
  const outRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (result) setEdited(result.sanitized);
  }, [result]);

  const run = async () => {
    if (!input.trim()) {
      toast.error("Paste something to sanitize.");
      return;
    }
    setBusy(true);
    setResult(null);
    // Honest, lightweight progress — the call is a single model pass.
    setStage(decode ? "Decoding…" : "Detecting sensitive values with the model…");
    try {
      const r = await api.sanitizeText(input, decode || undefined);
      setStage("Applying placeholders…");
      setResult(r);
      if (r.decoded?.changed) toast.success(`Decoded ${r.decoded.codec} payload, then sanitized.`);
      else if (decode) toast.info("Input wasn't encoded — sanitized as-is.");
    } catch (e) {
      toast.error((e as ApiError).message);
    } finally {
      setBusy(false);
      setStage("");
    }
  };

  const copy = () => {
    navigator.clipboard.writeText(edited);
    toast.success("Sanitized text copied.");
  };

  const countOccurrences = (hay: string, needle: string) =>
    needle ? hay.split(needle).length - 1 : 0;

  const replaceAll = () => {
    if (!find) return;
    const n = countOccurrences(edited, find);
    if (n === 0) {
      toast.error(`"${find}" not found.`);
      return;
    }
    setEdited(edited.split(find).join(replace));
    toast.success(`Replaced ${n} occurrence(s).`);
  };

  // Select-to-replace: take the current selection in the output box and replace
  // every occurrence of it with a value the analyst types.
  const replaceSelection = () => {
    const ta = outRef.current;
    if (!ta) return;
    const sel = edited.slice(ta.selectionStart, ta.selectionEnd).trim();
    if (!sel) {
      toast.error("Select some text in the output first.");
      return;
    }
    const to = window.prompt(`Replace all "${sel}" with:`, "");
    if (to === null) return;
    const n = countOccurrences(edited, sel);
    setEdited(edited.split(sel).join(to));
    toast.success(`Replaced ${n} occurrence(s) of "${sel}".`);
  };

  const summary = result?.summary;
  const uncertain = result?.uncertain ?? [];

  return (
    <Card>
      <PanelHeader
        title="Data Sanitizer & Anonymizer"
        subtitle="Anonymize internal/proprietary entities and redact secrets in any text, command line, script, or JSON — public IPs and external domains are preserved, and only the sensitive substring inside a path is changed"
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

        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
          <label className="flex items-center gap-1.5">
            Decode first:
            <select
              value={decode}
              onChange={(e) => setDecode(e.target.value as DecodeMode)}
              className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-100"
            >
              {DECODE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>
          <span className="text-slate-600">
            Encoded payload? Decode it, then sanitize the decoded text.
          </span>
        </div>

        {busy && stage && (
          <div className="flex items-center gap-2 rounded border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs text-slate-400">
            <Spinner /> {stage}
          </div>
        )}

        {result && (
          <>
            {summary && (
              <div className="flex flex-wrap gap-2 text-[11px]">
                <SummaryTile label="Anonymized" value={summary.anonymized} tone="emerald" />
                <SummaryTile label="Redacted" value={summary.redacted} tone="rose" />
                <SummaryTile label="Kept as-is" value={summary.kept} tone="slate" />
                <SummaryTile label="Needs review" value={summary.uncertain} tone="amber" />
                {result.decoded?.changed && (
                  <SummaryTile label={`Decoded (${result.decoded.codec})`} value="✓" tone="indigo" />
                )}
              </div>
            )}

            <div>
              <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Sanitized output <span className="font-normal normal-case text-slate-600">(editable)</span>
                </p>
                <div className="flex gap-1.5">
                  <Button variant="ghost" className="px-2 py-1 text-xs" onClick={replaceSelection}>
                    Replace selection…
                  </Button>
                  <Button variant="ghost" className="px-2 py-1 text-xs" onClick={copy}>Copy</Button>
                </div>
              </div>
              <Textarea
                ref={outRef}
                rows={10}
                value={edited}
                onChange={(e) => setEdited(e.target.value)}
                className="max-h-72 font-mono text-xs text-slate-200"
              />
              {/* Find & replace across the output */}
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <input
                  value={find}
                  onChange={(e) => setFind(e.target.value)}
                  placeholder="Find"
                  className="w-32 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-xs text-slate-100"
                />
                <input
                  value={replace}
                  onChange={(e) => setReplace(e.target.value)}
                  placeholder="Replace with"
                  className="w-32 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-xs text-slate-100"
                />
                <Button variant="ghost" className="px-2 py-1 text-xs" onClick={replaceAll}>
                  Replace all
                </Button>
                {find && (
                  <span className="text-[11px] text-slate-600">
                    {countOccurrences(edited, find)} match(es)
                  </span>
                )}
              </div>
            </div>

            {uncertain.length > 0 && (
              <div className="rounded border border-amber-900/50 bg-amber-950/20 p-3">
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-amber-300">
                  I'm not sure about these ({uncertain.length})
                </p>
                <p className="mb-2 text-[11px] text-amber-200/70">
                  The model wasn't confident, or it's a path/combined string where only part is
                  sensitive. These were <b>not</b> changed — use “Replace selection…” above to fix any
                  that are genuinely internal.
                </p>
                <ul className="space-y-1 text-[11px]">
                  {uncertain.map((u, i) => (
                    <li key={i} className="flex flex-wrap items-center gap-1.5">
                      <span className="font-mono text-amber-200">{u.value}</span>
                      <Badge className="border border-amber-800 bg-amber-950 text-amber-300">{u.type}</Badge>
                      <span className="text-slate-500">— {u.reason}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

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
              AI-assisted detection with hard rules: public IPs and known external domains are never
              altered, and a whole path is never swapped wholesale — only the sensitive substring
              inside it. Every occurrence of a value maps to the same placeholder. Review before
              sharing — confirm nothing internal slipped through.
            </p>
          </>
        )}
      </div>
    </Card>
  );
}

function SummaryTile({
  label, value, tone,
}: {
  label: string;
  value: number | string;
  tone: "emerald" | "rose" | "slate" | "amber" | "indigo";
}) {
  const tones: Record<string, string> = {
    emerald: "border-emerald-800 bg-emerald-950/40 text-emerald-300",
    rose: "border-rose-800 bg-rose-950/40 text-rose-300",
    slate: "border-slate-700 bg-slate-900 text-slate-300",
    amber: "border-amber-800 bg-amber-950/40 text-amber-300",
    indigo: "border-indigo-800 bg-indigo-950/40 text-indigo-300",
  };
  return (
    <span className={`rounded border px-2.5 py-1 ${tones[tone]}`}>
      <b className="font-mono">{value}</b> {label}
    </span>
  );
}
