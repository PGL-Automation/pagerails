"use client";

import { useState } from "react";
import { useFetchStatement, useFetchLedger } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Download, RefreshCw, Loader2, CheckCircle2, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

interface ConnectorActionsProps {
  accountId: string;
  canFetchStatement?: boolean;
  canFetchLedger?: boolean;
}

function useTodayPeriod() {
  const today = new Date().toISOString().slice(0, 10);
  return { periodStart: today, periodEnd: today };
}

export function ConnectorActions({ accountId, canFetchStatement = true, canFetchLedger = true }: ConnectorActionsProps) {
  const { periodStart, periodEnd } = useTodayPeriod();
  const [stmtOpen, setStmtOpen] = useState(false);
  const [glOpen,   setGlOpen]   = useState(false);
  const [start, setStart] = useState(periodStart);
  const [end,   setEnd]   = useState(periodEnd);

  const fetchStmt = useFetchStatement();
  const fetchGl   = useFetchLedger();

  function ResultBadge({ mutation }: { mutation: typeof fetchStmt }) {
    if (mutation.isPending) return <span className="text-[11px] text-blue-600 flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" />Fetching…</span>;
    if (mutation.isSuccess)  return <span className="text-[11px] text-emerald-600 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" />Done</span>;
    if (mutation.isError)    return <span className="text-[11px] text-red-600 flex items-center gap-1"><AlertTriangle className="w-3 h-3" />{(mutation.error as any)?.message?.slice(0,60)}</span>;
    return null;
  }

  return (
    <>
      <div className="flex items-center gap-2 flex-wrap">
        {canFetchStatement && (
          <Button size="sm" variant="outline" className="h-7 text-[11px] gap-1.5"
            onClick={() => setStmtOpen(true)}>
            <Download className="w-3 h-3" />
            Fetch Statement
          </Button>
        )}
        {canFetchLedger && (
          <Button size="sm" variant="outline" className="h-7 text-[11px] gap-1.5"
            onClick={() => setGlOpen(true)}>
            <RefreshCw className="w-3 h-3" />
            Fetch GL
          </Button>
        )}
        <ResultBadge mutation={fetchStmt} />
        <ResultBadge mutation={fetchGl} />
      </div>

      {/* Statement fetch dialog */}
      <Dialog open={stmtOpen} onOpenChange={setStmtOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-[14px]">Fetch bank statement</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <p className="text-[12px] text-muted-foreground">
              Pulls the bank statement via the configured API or email connector for <strong>{accountId}</strong>.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-[12px]">From</Label>
                <Input type="date" value={start} onChange={e => setStart(e.target.value)} className="h-8 text-[12px]" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-[12px]">To</Label>
                <Input type="date" value={end} onChange={e => setEnd(e.target.value)} className="h-8 text-[12px]" />
              </div>
            </div>
            {fetchStmt.isError && (
              <p className="text-[12px] text-red-600 bg-red-50 rounded-lg px-3 py-2">
                {(fetchStmt.error as any)?.message}
              </p>
            )}
            {fetchStmt.isSuccess && (
              <p className="text-[12px] text-emerald-600 bg-emerald-50 rounded-lg px-3 py-2">
                {(fetchStmt.data as any)?.message}
              </p>
            )}
            <Button className="w-full h-9 text-[13px] gap-2"
              disabled={fetchStmt.isPending}
              onClick={() => fetchStmt.mutate({ account_id: accountId, period_start: start, period_end: end })}>
              {fetchStmt.isPending
                ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />Fetching…</>
                : <><Download className="w-3.5 h-3.5" />Fetch statement</>}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* GL fetch dialog */}
      <Dialog open={glOpen} onOpenChange={setGlOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-[14px]">Fetch GL from Symplus</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <p className="text-[12px] text-muted-foreground">
              Pulls ledger entries for <strong>{accountId}</strong> from Symplus for the selected period.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-[12px]">From</Label>
                <Input type="date" value={start} onChange={e => setStart(e.target.value)} className="h-8 text-[12px]" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-[12px]">To</Label>
                <Input type="date" value={end} onChange={e => setEnd(e.target.value)} className="h-8 text-[12px]" />
              </div>
            </div>
            {fetchGl.isError && (
              <p className="text-[12px] text-red-600 bg-red-50 rounded-lg px-3 py-2">
                {(fetchGl.error as any)?.message}
              </p>
            )}
            {fetchGl.isSuccess && (
              <p className="text-[12px] text-emerald-600 bg-emerald-50 rounded-lg px-3 py-2">
                {(fetchGl.data as any)?.message}
              </p>
            )}
            <Button className="w-full h-9 text-[13px] gap-2"
              disabled={fetchGl.isPending}
              onClick={() => fetchGl.mutate({ account_id: accountId, period_start: start, period_end: end })}>
              {fetchGl.isPending
                ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />Fetching…</>
                : <><RefreshCw className="w-3.5 h-3.5" />Fetch GL</>}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
