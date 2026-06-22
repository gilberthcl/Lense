import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { DocType, FindingCategory } from "../lib/types";

// --- Generic surfaces ---

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-lg border border-slate-800 bg-slate-900/60 ${className}`}
    >
      {children}
    </div>
  );
}

export function PanelHeader({
  title,
  subtitle,
  right,
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-800 px-4 py-3">
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-200">
          {title}
        </h2>
        {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

// --- Buttons ---

type Variant = "primary" | "ghost" | "danger" | "success";

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-indigo-600 hover:bg-indigo-500 text-white border-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 disabled:border-slate-700",
  ghost:
    "bg-transparent hover:bg-slate-800 text-slate-300 border-slate-700 disabled:text-slate-600",
  danger:
    "bg-red-900/40 hover:bg-red-800/60 text-red-200 border-red-800 disabled:opacity-50",
  success:
    "bg-emerald-900/40 hover:bg-emerald-800/60 text-emerald-200 border-emerald-800 disabled:opacity-50",
};

export function Button({
  variant = "ghost",
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed ${variantClasses[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

// --- Form controls ---

export function Input(
  props: React.InputHTMLAttributes<HTMLInputElement>,
) {
  return (
    <input
      {...props}
      className={`w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-indigo-500 focus:outline-none ${props.className ?? ""}`}
    />
  );
}

export function Textarea(
  props: React.TextareaHTMLAttributes<HTMLTextAreaElement>,
) {
  return (
    <textarea
      {...props}
      className={`w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-indigo-500 focus:outline-none ${props.className ?? ""}`}
    />
  );
}

export function Select(
  props: React.SelectHTMLAttributes<HTMLSelectElement>,
) {
  return (
    <select
      {...props}
      className={`w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none ${props.className ?? ""}`}
    />
  );
}

export function Label({ children }: { children: ReactNode }) {
  return (
    <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">
      {children}
    </label>
  );
}

// --- Badges ---

export function Badge({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${className}`}
    >
      {children}
    </span>
  );
}

const categoryClasses: Record<string, string> = {
  malicious: "bg-red-950 text-red-300 border border-red-800",
  suspicious: "bg-amber-950 text-amber-300 border border-amber-800",
  risky: "bg-orange-950 text-orange-300 border border-orange-800",
  policy_violation: "bg-blue-950 text-blue-300 border border-blue-800",
  unconfirmed: "bg-slate-800 text-slate-300 border border-slate-700",
};

export function CategoryBadge({ category }: { category: FindingCategory }) {
  const cls =
    categoryClasses[category] ?? "bg-slate-800 text-slate-300 border border-slate-700";
  return <Badge className={cls}>{String(category).replace(/_/g, " ")}</Badge>;
}

const statusClasses: Record<string, string> = {
  uploaded: "bg-slate-800 text-slate-300 border border-slate-700",
  analyzing: "bg-indigo-950 text-indigo-300 border border-indigo-800",
  analyzed: "bg-emerald-950 text-emerald-300 border border-emerald-800",
  error: "bg-red-950 text-red-300 border border-red-800",
};

export function DatasetStatusBadge({ status }: { status: string }) {
  const cls =
    statusClasses[status] ?? "bg-slate-800 text-slate-300 border border-slate-700";
  return <Badge className={cls}>{status}</Badge>;
}

const findingStatusClasses: Record<string, string> = {
  draft: "bg-slate-800 text-slate-300 border border-slate-700",
  validated: "bg-emerald-950 text-emerald-300 border border-emerald-800",
  rejected: "bg-red-950 text-red-400 border border-red-800",
};

export function FindingStatusBadge({ status }: { status: string }) {
  const cls =
    findingStatusClasses[status] ?? "bg-slate-800 text-slate-300 border border-slate-700";
  return <Badge className={cls}>{status}</Badge>;
}

// --- Misc ---

export const DOC_TYPES: { value: DocType; label: string; constitution?: boolean }[] = [
  { value: "methodology", label: "Methodology", constitution: true },
  { value: "finding_categories", label: "Finding Categories", constitution: true },
  { value: "finding_format", label: "Finding Format", constitution: true },
  { value: "approved_software", label: "Approved Software" },
  { value: "report_standard", label: "Report Standard" },
  { value: "previous_report", label: "Previous Report" },
  { value: "validated_finding", label: "Validated Finding" },
];

export function docTypeLabel(t: DocType): string {
  return DOC_TYPES.find((d) => d.value === t)?.label ?? t;
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-indigo-400 ${className}`}
    />
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="px-4 py-10 text-center text-sm text-slate-500">{children}</div>
  );
}

export function fmtBytes(bytes: number): string {
  if (!bytes && bytes !== 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function fmtDate(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}
