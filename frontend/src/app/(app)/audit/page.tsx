"use client";

import { Topbar } from "@/components/layout/topbar";
import { fmtDateTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ShieldCheck, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAudit } from "@/lib/hooks";
import { verifyChain } from "@/lib/api";
import { useMutation } from "@tanstack/react-query";

const ACTION_STYLE: Record<string, string> = {
  RUN:        "bg-blue-50 text-blue-700 ring-blue-200/60",
  SIGNOFF:    "bg-emerald-50 text-emerald-700 ring-emerald-200/60",
  DECISION:   "bg-amber-50 text-amber-700 ring-amber-200/60",
  RUN_FAILED: "bg-red-50 text-red-700 ring-red-200/60",
};

export default function AuditPage() {
  const { data: entries = [], isLoading } = useAudit();
  const verify = useMutation({ mutationFn: verifyChain });

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <Topbar
        title="Audit Log"
        subtitle="SHA-256 chained — tamper-evident"
        actions={
          <Button size="sm" variant="outline" className="h-8 text-[12px] gap-1.5"
            onClick={() => verify.mutate()} disabled={verify.isPending}>
            <ShieldCheck className="w-3.5 h-3.5" />
            {verify.isPending ? "Verifying…" : "Verify Chain"}
          </Button>
        }
      />

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto">

          {verify.data && (
            <div className={cn(
              "flex items-center gap-2 mb-5 text-[12px] rounded-lg px-4 py-2.5 border",
              verify.data.intact
                ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                : "bg-red-50 border-red-200 text-red-700"
            )}>
              <CheckCircle2 className="w-4 h-4" />
              <span className="font-medium">{verify.data.message}</span>
            </div>
          )}

          {isLoading && (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12 rounded-xl" />)}
            </div>
          )}

          {!isLoading && (entries as any[]).length === 0 && (
            <div className="bg-muted/40 border border-border rounded-xl p-10 text-center">
              <p className="text-[13px] text-muted-foreground">No audit entries yet.</p>
            </div>
          )}

          {!isLoading && (entries as any[]).length > 0 && (
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              <div className="grid grid-cols-[40px_140px_80px_120px_1fr_100px] gap-4 px-5 py-2.5 border-b border-border text-[11px] font-medium text-muted-foreground uppercase tracking-wide bg-muted/20">
                <span>#</span><span>Timestamp</span><span>Action</span><span>Actor</span><span>Detail</span><span className="text-right">Hash</span>
              </div>

              <div className="divide-y divide-border">
                {(entries as any[]).map((entry: any) => (
                  <div key={entry.seq} className="grid grid-cols-[40px_140px_80px_120px_1fr_100px] gap-4 px-5 py-3 items-start hover:bg-muted/20 transition-colors">
                    <span className="text-[12px] text-muted-foreground tabular-nums">{entry.seq}</span>
                    <span className="text-[12px] text-muted-foreground tabular-nums">{fmtDateTime(entry.ts)}</span>
                    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset self-start",
                      ACTION_STYLE[entry.action] ?? "bg-gray-50 text-gray-600 ring-gray-200/60")}>
                      {entry.action}
                    </span>
                    <span className="text-[12px] font-medium">{entry.actor}</span>
                    <div className="text-[12px] text-muted-foreground space-y-0.5">
                      {entry.payload && typeof entry.payload === "object" && !Array.isArray(entry.payload) && Object.entries(entry.payload).map(([k, v]) => (
                        <div key={k} className="flex gap-2">
                          <span className="font-mono text-[10px] text-muted-foreground/60 shrink-0">{k}:</span>
                          <span className="text-[11px] truncate">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                    <div className="text-right">
                      <span className="font-mono text-[10px] text-muted-foreground">{String(entry.hash).slice(0, 8)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
