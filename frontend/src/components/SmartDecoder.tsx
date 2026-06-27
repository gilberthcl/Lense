import { useMemo, useState } from "react";
import { useToast } from "./Toast";
import { Button, Card, PanelHeader, Textarea } from "./ui";

/**
 * Smart Decoder — a CyberChef-style recipe tool. Build an ordered list of
 * operations and they're applied in sequence to the input, live. Pure,
 * client-side, deterministic — no model, no network.
 */

type Op = { key: string; name: string; group: string; fn: (s: string) => string };

// ── UTF-8-safe base64 ────────────────────────────────────────────────────────
const b64encode = (s: string) =>
  btoa(unescape(encodeURIComponent(s)));
const b64decode = (s: string) =>
  decodeURIComponent(escape(atob(s.trim().replace(/\s+/g, ""))));

const toHex = (s: string) =>
  Array.from(new TextEncoder().encode(s)).map((b) => b.toString(16).padStart(2, "0")).join(" ");
const fromHex = (s: string) => {
  const bytes = s.trim().split(/[\s,]+/).filter(Boolean).map((h) => parseInt(h, 16));
  if (bytes.some((b) => Number.isNaN(b))) throw new Error("invalid hex");
  return new TextDecoder().decode(new Uint8Array(bytes));
};

const fromCharcode = (s: string) =>
  String.fromCharCode(...s.trim().split(/[\s,]+/).filter(Boolean).map((n) => parseInt(n, 10)));
const toCharcode = (s: string) =>
  Array.from(s).map((c) => c.charCodeAt(0)).join(" ");
const fromBinary = (s: string) =>
  String.fromCharCode(...s.trim().split(/\s+/).filter(Boolean).map((b) => parseInt(b, 2)));
const fromDecimal = (s: string) =>
  String.fromCharCode(...s.trim().split(/[\s,]+/).filter(Boolean).map((n) => parseInt(n, 10)));

const rot13 = (s: string) =>
  s.replace(/[a-z]/gi, (c) => {
    const base = c <= "Z" ? 65 : 97;
    return String.fromCharCode(((c.charCodeAt(0) - base + 13) % 26) + base);
  });

const htmlEntityDecode = (s: string) => {
  const map: Record<string, string> = {
    "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&nbsp;": " ",
  };
  return s
    .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(parseInt(d, 10)))
    .replace(/&[a-z]+;/gi, (m) => map[m] ?? m);
};

const OPS: Op[] = [
  { key: "b64d", name: "From Base64", group: "Base", fn: b64decode },
  { key: "b64e", name: "To Base64", group: "Base", fn: b64encode },
  { key: "hexd", name: "From Hex", group: "Base", fn: fromHex },
  { key: "hexe", name: "To Hex", group: "Base", fn: toHex },
  { key: "urld", name: "URL Decode", group: "Web", fn: (s) => decodeURIComponent(s) },
  { key: "urle", name: "URL Encode", group: "Web", fn: (s) => encodeURIComponent(s) },
  { key: "htmld", name: "HTML Entity Decode", group: "Web", fn: htmlEntityDecode },
  { key: "ccd", name: "From Charcode", group: "Numeric", fn: fromCharcode },
  { key: "cce", name: "To Charcode", group: "Numeric", fn: toCharcode },
  { key: "bind", name: "From Binary", group: "Numeric", fn: fromBinary },
  { key: "decd", name: "From Decimal", group: "Numeric", fn: fromDecimal },
  { key: "rot13", name: "ROT13", group: "Cipher", fn: rot13 },
  { key: "rev", name: "Reverse", group: "Text", fn: (s) => Array.from(s).reverse().join("") },
  { key: "upper", name: "To Uppercase", group: "Text", fn: (s) => s.toUpperCase() },
  { key: "lower", name: "To Lowercase", group: "Text", fn: (s) => s.toLowerCase() },
  { key: "nows", name: "Remove Whitespace", group: "Text", fn: (s) => s.replace(/\s+/g, "") },
  { key: "jsonp", name: "JSON Pretty-print", group: "Text", fn: (s) => JSON.stringify(JSON.parse(s), null, 2) },
];
const OP = Object.fromEntries(OPS.map((o) => [o.key, o]));

interface StepResult { ok: boolean; out: string; error?: string }

export default function SmartDecoder() {
  const toast = useToast();
  const [input, setInput] = useState("");
  const [recipe, setRecipe] = useState<string[]>([]);

  // Apply the recipe in sequence; a failing step stops the chain but shows where.
  const steps: StepResult[] = useMemo(() => {
    const out: StepResult[] = [];
    let cur = input;
    for (const key of recipe) {
      const op = OP[key];
      if (!op) { out.push({ ok: false, out: cur, error: "unknown op" }); break; }
      try {
        cur = op.fn(cur);
        out.push({ ok: true, out: cur });
      } catch (e) {
        out.push({ ok: false, out: cur, error: e instanceof Error ? e.message : "failed" });
        break;
      }
    }
    return out;
  }, [input, recipe]);

  const output = steps.length ? steps[steps.length - 1].out : input;
  const failedAt = steps.findIndex((s) => !s.ok);

  const add = (key: string) => setRecipe((r) => [...r, key]);
  const removeAt = (i: number) => setRecipe((r) => r.filter((_, j) => j !== i));
  const move = (i: number, d: -1 | 1) =>
    setRecipe((r) => {
      const j = i + d;
      if (j < 0 || j >= r.length) return r;
      const n = [...r];
      [n[i], n[j]] = [n[j], n[i]];
      return n;
    });

  const groups = Array.from(new Set(OPS.map((o) => o.group)));

  return (
    <Card>
      <PanelHeader
        title="Smart Decoder"
        subtitle="CyberChef-style recipe — stack operations and they apply in order, live. Runs entirely in your browser (no model, no network)."
        right={
          <Button variant="ghost" disabled={!recipe.length} onClick={() => setRecipe([])}>
            Clear recipe
          </Button>
        }
      />
      <div className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-[1fr_220px]">
        <div className="space-y-4">
          <div>
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Input</p>
            <Textarea rows={5} value={input} onChange={(e) => setInput(e.target.value)}
              placeholder="Paste an encoded string, beacon, command, blob…" className="font-mono text-xs" />
          </div>

          {/* Recipe */}
          <div>
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Recipe ({recipe.length})
            </p>
            {recipe.length === 0 ? (
              <p className="rounded border border-dashed border-slate-800 px-3 py-4 text-center text-xs text-slate-600">
                Add operations from the right →
              </p>
            ) : (
              <ul className="space-y-1">
                {recipe.map((key, i) => (
                  <li key={i} className={`flex items-center gap-2 rounded border px-2 py-1.5 text-sm ${
                    failedAt === i ? "border-rose-800 bg-rose-950/30" : "border-slate-800 bg-slate-950/40"
                  }`}>
                    <span className="font-mono text-[10px] text-slate-600">{i + 1}</span>
                    <span className="flex-1 text-slate-200">{OP[key]?.name ?? key}</span>
                    {steps[i] && !steps[i].ok && (
                      <span className="text-[10px] text-rose-400">{steps[i].error}</span>
                    )}
                    <button onClick={() => move(i, -1)} className="px-1 text-slate-500 hover:text-slate-200" title="Up">▲</button>
                    <button onClick={() => move(i, 1)} className="px-1 text-slate-500 hover:text-slate-200" title="Down">▼</button>
                    <button onClick={() => removeAt(i)} className="px-1 text-rose-400 hover:text-rose-300" title="Remove">✕</button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Output */}
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Output</p>
              <Button variant="ghost" className="px-2 py-1 text-xs" disabled={!output}
                onClick={() => { navigator.clipboard.writeText(output); toast.success("Copied."); }}>
                Copy
              </Button>
            </div>
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded border border-slate-800 bg-slate-950 p-3 font-mono text-xs text-slate-200">
              {output || <span className="text-slate-600">— output appears here —</span>}
            </pre>
            {failedAt >= 0 && (
              <p className="mt-1 text-[11px] text-rose-400">
                Step {failedAt + 1} ({OP[recipe[failedAt]]?.name}) failed — output is from before it.
              </p>
            )}
          </div>
        </div>

        {/* Operation palette */}
        <div className="lg:border-l lg:border-slate-800 lg:pl-4">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Operations</p>
          <div className="space-y-3">
            {groups.map((g) => (
              <div key={g}>
                <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-600">{g}</p>
                <div className="flex flex-wrap gap-1">
                  {OPS.filter((o) => o.group === g).map((o) => (
                    <button key={o.key} onClick={() => add(o.key)}
                      className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-300 hover:border-indigo-600 hover:text-indigo-300">
                      {o.name}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}
