"use client";

import Link from "next/link";
import { Topbar } from "@/components/layout/topbar";
import { RunStatusBadge } from "@/components/domain/status-badge";
import { fmtAmount, fmtDateTime } from "@/lib/format";
import { CheckCircle2, ChevronRight, Database } from "lucide-react";
import { TriggerRunModal } from "@/components/domain/trigger-run-modal";
import { DownloadButton } from "./download-button";
import { Skeleton } from "@/components/ui/skeleton";
import { useRuns } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const ENTITY: Record<string, "PAM" | "PCL"> = {
  "PAM-PRV-CLIENTS": "PAM", "PAM-OPS-01": "PAM", "PAM-CLIENT-01": "PAM", "PAM-MMF-CUST": "PAM",
  "PCL-OPS-01": "PCL", "PCL-COLL-01": "PCL",
};

export default function RunsPage() {
  const { data: runs = [], isLoading } = useRuns();

  const grouped = Array.isArray(runs) ? (runs as any[]).reduce((acc: any, r: any) => {
    const key = r?.period_end?.slice(0, 7);
    if (!key) return acc;
    if (!acc[key]) acc[key] = [];
    acc[key].push(r);
    return acc;
  }, {}) : {};

  const periods = Object.keys(grouped).sort().reverse();

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <Topbar
        title="Reconciliation Runs"
        subtitle={isLoading ? "Loading…" : `${runs.length} run${runs.length !== 1 ? "s" : ""} — live from database`}
        actions={<TriggerRunModal />}
      />

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-5xl mx-auto space-y-8">

          {isLoading && (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-14 rounded-xl" />
              ))}
            </div>
          )}

          {!isLoading && runs.length === 0 && (
            <div className="bg-muted/40 border border-border rounded-xl p-10 flex flex-col items-center gap-3 text-center">
              <Database className="w-8 h-8 text-muted-foreground" />
              <p className="text-[14px] font-medium">No runs in the database yet</p>
              <p className="text-[12px] text-muted-foreground max-w-sm">
                Upload files and trigger a run using the <strong>New Run</strong> button above.
              </p>
            </div>
          )}

          {periods.map(period => (
            <section key={period}>
              <div className="flex items-center gap-3 mb-3">
                <h2 className="text-[13px] font-semibold text-foreground">
                  {new Date(period + "-01").toLocaleDateString("en-GB", { month: "long", year: "numeric" })}
                </h2>
                <div className="flex-1 h-px bg-border" />
                <span className="text-[11px] text-muted-foreground">
                  {(grouped[period] ?? []).filter((r: any) => r.status === "RECONCILED").length}/{(grouped[period] ?? []).length} reconciled
                </span>
              </div>

              <div className="bg-card border border-border rounded-xl overflow-hidden">
                <div className="grid grid-cols-[1fr_130px_110px_100px_90px_32px] gap-4 px-5 py-2.5 border-b border-border text-[11px] font-medium text-muted-foreground uppercase tracking-wide bg-muted/20">
                  <span>Account</span><span>Bank Close</span><span>Difference</span><span>Status</span><span>Sign-off</span><span />
                </div>

                <div className="divide-y divide-border">
                  {grouped[period].map((run: any) => {
                    const entity = ENTITY[run.account_id] ?? "PAM";
                    return (
                      <Link key={run.run_id} href={`/runs/${encodeURIComponent(run.run_id)}`}
                        className="grid grid-cols-[1fr_130px_110px_100px_90px_32px] gap-4 px-5 py-3.5 items-center hover:bg-muted/30 transition-colors group">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-[13px] font-mono font-medium">{run.account_id}</span>
                            <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full font-medium",
                              entity === "PAM" ? "bg-blue-50 text-blue-600" : "bg-purple-50 text-purple-600")}>
                              {entity}
                            </span>
                          </div>
                          <p className="text-[11px] text-muted-foreground mt-0.5">{fmtDateTime(run.created_at)} · {run.maker}</p>
                        </div>
                        <span className="text-[13px] font-medium tabular-nums">{fmtAmount(run.bank_close, { compact: true })}</span>
                        <span className={cn("text-[13px] font-medium tabular-nums", run.difference !== 0 ? "text-red-600" : "text-emerald-600")}>
                          {fmtAmount(run.difference)}
                        </span>
                        <RunStatusBadge status={run.status} />
                        <div>
                          {run.signed_at
                            ? <div className="flex items-center gap-1 text-emerald-600"><CheckCircle2 className="w-3.5 h-3.5" /><span className="text-[11px]">{run.checker}</span></div>
                            : <span className="text-[11px] text-muted-foreground italic">Pending</span>}
                        </div>
                        <div className="flex items-center justify-end gap-1">
                          {run.report_path && <DownloadButton href={run.report_path} />}
                          <ChevronRight className="w-3.5 h-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                      </Link>
                    );
                  })}
                </div>
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
