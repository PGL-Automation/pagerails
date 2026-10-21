"use client";

import Link from "next/link";
import { Topbar } from "@/components/layout/topbar";
import { StatCard } from "@/components/domain/stat-card";
import { RunStatusBadge } from "@/components/domain/status-badge";
import { TriggerRunModal } from "@/components/domain/trigger-run-modal";
import { fmtAmount, fmtDateTime } from "@/lib/format";
import { useStats, useRuns } from "@/lib/hooks";
import { Skeleton } from "@/components/ui/skeleton";
import {
  CheckCircle2, AlertCircle, Clock, FileStack,
  ArrowRight, AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading } = useStats();
  const { data: runs = [],  isLoading: runsLoading }  = useRuns();

  const loading = statsLoading || runsLoading;

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <Topbar
        title="Dashboard"
        subtitle={loading ? "Loading…" : `${runs.length} run${runs.length !== 1 ? "s" : ""} in database`}
        actions={<TriggerRunModal />}
      />

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-6xl mx-auto space-y-6">

          {/* KPI strip */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {loading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-28 rounded-xl" />
              ))
            ) : (
              <>
                <StatCard label="Reconciled" value={`${stats?.reconciled_count ?? 0}/${stats?.total_accounts ?? 0}`}
                  sub="latest run per account" icon={CheckCircle2}
                  accent={(stats?.reconciled_count ?? 0) > 0 ? "success" : "default"} />
                <StatCard label="Unreconciled" value={stats?.unreconciled_count ?? 0}
                  sub={(stats?.unreconciled_count ?? 0) > 0 ? "require attention" : "All clear"}
                  icon={AlertCircle} accent={(stats?.unreconciled_count ?? 0) > 0 ? "danger" : "success"} />
                <StatCard label="Pending Sign-off" value={stats?.pending_signoff ?? 0}
                  sub="awaiting checker" icon={Clock}
                  accent={(stats?.pending_signoff ?? 0) > 0 ? "warning" : "default"} />
                <StatCard label="Open Items" value={(stats?.open_items_count ?? 0).toLocaleString()}
                  sub="unmatched transactions" icon={FileStack}
                  accent={(stats?.open_items_count ?? 0) > 0 ? "warning" : "default"} />
              </>
            )}
          </div>

          {/* Runs table */}
          {!loading && runs.length > 0 && (
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              <div className="px-5 py-4 border-b border-border flex items-center justify-between">
                <div>
                  <h2 className="text-[13px] font-semibold">Recent Runs</h2>
                  <p className="text-[11px] text-muted-foreground mt-0.5">Live from database</p>
                </div>
                <Link href="/runs">
                  <Button variant="ghost" size="sm" className="h-7 text-[11px] gap-1 text-muted-foreground">
                    All runs <ArrowRight className="w-3 h-3" />
                  </Button>
                </Link>
              </div>

              <div className="grid grid-cols-[1fr_140px_120px_100px_80px] gap-4 px-5 py-2.5 border-b border-border text-[11px] font-medium text-muted-foreground uppercase tracking-wide bg-muted/20">
                <span>Account</span><span>Period</span><span>Bank Close</span><span>Difference</span><span>Status</span>
              </div>

              <div className="divide-y divide-border">
                {runs.slice(0, 8).map((run: any) => (
                  <Link key={run.run_id} href={`/runs/${run.run_id}`}
                    className="grid grid-cols-[1fr_140px_120px_100px_80px] gap-4 px-5 py-3.5 items-center hover:bg-muted/30 transition-colors">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-[13px] font-mono font-medium">{run.account_id}</span>
                        <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full font-medium",
                          run.entity === "PAM" ? "bg-blue-50 text-blue-600" : "bg-purple-50 text-purple-600")}>
                          {run.entity}
                        </span>
                      </div>
                      <p className="text-[11px] text-muted-foreground mt-0.5">{run.maker}</p>
                    </div>
                    <span className="text-[12px] text-muted-foreground tabular-nums">
                      {run.period_end}
                    </span>
                    <span className="text-[13px] font-medium tabular-nums">
                      {fmtAmount(run.bank_close, { compact: true })}
                    </span>
                    <span className={cn("text-[13px] font-medium tabular-nums",
                      run.difference !== 0 ? "text-red-600" : "text-emerald-600")}>
                      {fmtAmount(run.difference)}
                    </span>
                    <RunStatusBadge status={run.status} />
                  </Link>
                ))}
              </div>
            </div>
          )}

          {!loading && runs.length === 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-4 flex items-start gap-3">
              <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
              <div>
                <p className="text-[13px] font-medium text-amber-800">No reconciliation runs yet</p>
                <p className="text-[12px] text-amber-700 mt-0.5">
                  Upload files and trigger a run using the <strong>New Run</strong> button above.
                </p>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
