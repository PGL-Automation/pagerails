import { cn } from "@/lib/utils";
import type { RunStatus, AlertSeverity, MatchStatus } from "@/lib/types";

const RUN_STATUS: Record<RunStatus, { label: string; className: string }> = {
  "RECONCILED":                 { label: "Reconciled",      className: "bg-emerald-50 text-emerald-700 ring-emerald-200/60" },
  "RECONCILED-WITH-EXCEPTIONS": { label: "Exceptions",      className: "bg-amber-50 text-amber-700 ring-amber-200/60" },
  "UNRECONCILED":               { label: "Unreconciled",    className: "bg-red-50 text-red-700 ring-red-200/60" },
  "RUNNING":                    { label: "Running…",        className: "bg-blue-50 text-blue-700 ring-blue-200/60" },
  "QUEUED":                     { label: "Queued",          className: "bg-gray-50 text-gray-600 ring-gray-200/60" },
  "FAILED":                     { label: "Failed",          className: "bg-red-50 text-red-700 ring-red-200/60" },
};

const ALERT_SEVERITY: Record<AlertSeverity, { label: string; className: string }> = {
  HIGH:   { label: "High",   className: "bg-red-50 text-red-700 ring-red-200/60" },
  MEDIUM: { label: "Medium", className: "bg-amber-50 text-amber-700 ring-amber-200/60" },
  LOW:    { label: "Low",    className: "bg-gray-50 text-gray-600 ring-gray-200/60" },
};

const MATCH_STATUS: Record<MatchStatus, { label: string; className: string }> = {
  AUTO:     { label: "Auto-matched", className: "bg-emerald-50 text-emerald-700 ring-emerald-200/60" },
  PROPOSED: { label: "Proposed",     className: "bg-amber-50 text-amber-700 ring-amber-200/60" },
  APPROVED: { label: "Approved",     className: "bg-blue-50 text-blue-700 ring-blue-200/60" },
  REJECTED: { label: "Rejected",     className: "bg-red-50 text-red-700 ring-red-200/60" },
};

const BASE = "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset tabular-nums";
const FALLBACK = { label: "Unknown", className: "bg-gray-50 text-gray-600 ring-gray-200/60" };

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const cfg = RUN_STATUS[status] ?? { ...FALLBACK, label: status ?? "Unknown" };
  return <span className={cn(BASE, cfg.className)}>{cfg.label}</span>;
}

export function AlertBadge({ severity }: { severity: AlertSeverity }) {
  const cfg = ALERT_SEVERITY[severity] ?? FALLBACK;
  return <span className={cn(BASE, cfg.className)}>{cfg.label}</span>;
}

export function MatchStatusBadge({ status }: { status: MatchStatus }) {
  const cfg = MATCH_STATUS[status] ?? { ...FALLBACK, label: status ?? "Unknown" };
  return <span className={cn(BASE, cfg.className)}>{cfg.label}</span>;
}

export function RuleBadge({ rule }: { rule: string }) {
  const short = rule.replace("_", " ").replace("P0 ", "P0·").replace("P1 ", "P1·")
    .replace("P2 ", "P2·").replace("P3 ", "P3·").replace("P4 ", "P4·").replace("P5 ", "P5·");
  return (
    <span className={cn(BASE, "bg-slate-50 text-slate-600 ring-slate-200/60 font-mono text-[10px]")}>
      {short}
    </span>
  );
}

export function PurposeBadge({ purpose, clientMoney }: { purpose: string; clientMoney: boolean }) {
  return (
    <span className={cn(
      BASE,
      clientMoney
        ? "bg-violet-50 text-violet-700 ring-violet-200/60"
        : "bg-gray-50 text-gray-600 ring-gray-200/60"
    )}>
      {purpose.replace("_", " ")}
    </span>
  );
}
