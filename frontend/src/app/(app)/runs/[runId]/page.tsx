"use client";

import { useState, use, useCallback } from "react";
import Link from "next/link";
import { Topbar } from "@/components/layout/topbar";
import { RunStatusBadge, RuleBadge } from "@/components/domain/status-badge";
import { SignoffButton } from "@/components/domain/signoff-button";
import { fmtAmount, fmtDate, fmtDateTime } from "@/lib/format";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ArrowLeft, Download, FileSpreadsheet, CheckCircle2,
  AlertTriangle, Loader2, RefreshCw, ArrowUpRight, ArrowDownLeft,
  FileText, ChevronDown, ChevronRight, Shield,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useRun, useProposedMatches } from "@/lib/hooks";
import { BASE, apiFetch } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

type Txn = {
  uid: string; side: "BANK" | "BOOK"; amount: number;
  txn_date: string; description: string; reference: string;
};

type FilterType = "all" | "matched" | "unmatched_bank" | "unmatched_book" | "proposed";

const ACCOUNT_META: Record<string, { bank: string; masked: string; entity: string }> = {
  "PAM-PRV-CLIENTS": { bank: "Providus Bank", masked: "****2286", entity: "PAM" },
  "PAM-OPS-01":      { bank: "Bank A",         masked: "****1101", entity: "PAM" },
  "PAM-CLIENT-01":   { bank: "Bank B",         masked: "****2202", entity: "PAM" },
  "PAM-MMF-CUST":    { bank: "Custodian",      masked: "****3303", entity: "PAM" },
  "PCL-OPS-01":      { bank: "Bank D",         masked: "****4404", entity: "PCL" },
  "PCL-COLL-01":     { bank: "Bank E",         masked: "****5505", entity: "PCL" },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function amtStr(n: number) {
  const abs = Math.abs(n) / 100;
  const sign = n < 0 ? "−" : "+";
  return sign + new Intl.NumberFormat("en-NG", { minimumFractionDigits: 2 }).format(abs);
}

function downloadFile(url: string) {
  const a = document.createElement("a");
  a.href = url; a.download = "";
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
}

// ── Transaction cell ──────────────────────────────────────────────────────────

function TxnCell({ txn, side }: { txn: Txn | null; side: "BANK" | "GL" }) {
  if (!txn) return (
    <div className="flex-1 px-4 py-3 text-[12px] text-muted-foreground italic flex items-center min-w-0">
      No matching {side} entry
    </div>
  );
  const isCredit = txn.amount > 0;
  return (
    <div className="flex-1 flex items-start gap-2 px-4 py-3 min-w-0">
      <div className={cn(
        "mt-0.5 shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs",
        isCredit ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-500"
      )}>
        {isCredit ? <ArrowDownLeft className="w-3 h-3" /> : <ArrowUpRight className="w-3 h-3" />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-muted-foreground shrink-0">{fmtDate(txn.txn_date)}</span>
          <span className={cn("text-[13px] font-semibold tabular-nums shrink-0",
            isCredit ? "text-emerald-700" : "text-red-600")}>
            {amtStr(txn.amount)}
          </span>
        </div>
        <p className="text-[13px] font-medium text-foreground truncate mt-0.5">{txn.description}</p>
        {txn.reference && (
          <p className="text-[10px] text-muted-foreground font-mono truncate mt-0.5">{txn.reference}</p>
        )}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function RunDetailPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params);
  const { data, isLoading, refetch } = useRun(runId);
  const { data: proposed = [] } = useProposedMatches(runId);

  const [filter, setFilter]       = useState<FilterType>("all");
  const [exporting, setExporting] = useState(false);
  const [payoutCheck, setPayoutCheck] = useState<any>(null);
  const [checking, setChecking]   = useState(false);
  const [showBalRec, setShowBalRec] = useState(false);

  const run: any      = data ?? {};
  const openBank: Txn[] = run?.open_bank ?? [];
  const openBook: Txn[] = run?.open_book ?? [];
  const allMatches: any[] = run?.matches ?? [];

  const matchedCount  = allMatches.filter((m: any) => m.status === "AUTO" || m.status === "APPROVED").length;
  const proposedCount = (proposed as any[]).length;
  const difference    = run.difference ?? 0;

  const apiBase = BASE ?? "http://localhost:8000";
  const meta = ACCOUNT_META[run?.account_id] ?? { bank: "", masked: "", entity: "" };

  // Build all display rows based on filter
  const rows = (() => {
    const matched = allMatches
      .filter((m: any) => m.status === "AUTO" || m.status === "APPROVED")
      .map((m: any) => ({ type: "matched", m, bankTxn: null as Txn | null, bookTxn: null as Txn | null }));
    const prop = (proposed as any[]).map(m => ({ type: "proposed", m,
      bankTxn: m.bank?.[0] as Txn | null ?? null,
      bookTxn: m.book?.[0] as Txn | null ?? null }));
    const uBank = openBank.map(t => ({ type: "unmatched_bank", m: null, bankTxn: t, bookTxn: null as Txn | null }));
    const uBook = openBook.map(t => ({ type: "unmatched_book", m: null, bankTxn: null as Txn | null, bookTxn: t }));

    switch (filter) {
      case "matched":       return matched;
      case "proposed":      return prop;
      case "unmatched_bank":return uBank;
      case "unmatched_book":return uBook;
      default:              return [...matched, ...prop, ...uBank, ...uBook];
    }
  })();

  const totalRows = allMatches.length + proposedCount + openBank.length + openBook.length;

  // Payout cross-check
  const runPayoutCheck = useCallback(async () => {
    setChecking(true);
    try {
      const res = await apiFetch(
        `/reconciliation/${encodeURIComponent(runId)}/payout-check`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }
      );
      setPayoutCheck(res);
    } catch (e) { console.error(e); }
    finally { setChecking(false); }
  }, [runId]);

  if (isLoading) return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <Topbar title="Loading…" />
      <div className="flex-1 p-6 space-y-3">
        {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14 rounded-xl" />)}
      </div>
    </div>
  );

  if (!run?.run_id) return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <Topbar title="Run not found" />
      <div className="flex-1 flex items-center justify-center text-muted-foreground text-[13px]">Run not found.</div>
    </div>
  );

  return (
    <div className="flex flex-col flex-1 overflow-hidden">

      {/* Header */}
      <Topbar
        title={run.account_id}
        subtitle={`${fmtDate(run.period_start)} – ${fmtDate(run.period_end)} · ${meta.bank} ${meta.masked}`}
        actions={
          <div className="flex items-center gap-2">
            <Link href="/runs">
              <button className="h-8 px-3 rounded-lg text-[12px] border border-border bg-card hover:bg-muted transition-colors flex items-center gap-1.5">
                <ArrowLeft className="w-3.5 h-3.5" /> All Runs
              </button>
            </Link>
            {run.report_path && (
              <button
                onClick={() => downloadFile(`${apiBase}/api/files/pack?path=${encodeURIComponent(run.report_path)}`)}
                className="h-8 px-3 rounded-lg text-[12px] border border-border bg-card hover:bg-muted transition-colors flex items-center gap-1.5"
              >
                <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-600" /> Download Excel
              </button>
            )}
            <button
              disabled={exporting}
              onClick={async () => {
                setExporting(true);
                try {
                  const res = await fetch(
                    `${apiBase}/api/runs/${encodeURIComponent(runId)}/export`,
                    { headers: { Authorization: `Bearer ${localStorage.getItem("token") ?? ""}` } }
                  );
                  if (res.ok) { const blob = await res.blob(); downloadFile(URL.createObjectURL(blob)); }
                } finally { setExporting(false); }
              }}
              className="h-8 px-3 rounded-lg text-[12px] border border-border bg-card hover:bg-muted transition-colors flex items-center gap-1.5 disabled:opacity-50"
            >
              {exporting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
              Export CSV
            </button>
            <button
              disabled={checking}
              onClick={runPayoutCheck}
              className="h-8 px-3 rounded-lg text-[12px] border border-border bg-card hover:bg-muted transition-colors flex items-center gap-1.5 disabled:opacity-50"
            >
              {checking ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Shield className="w-3.5 h-3.5 text-blue-600" />}
              3-Way Check
            </button>
          </div>
        }
      />

      <div className="flex-1 overflow-auto">

        {/* Summary strip */}
        <div className="px-6 py-3 border-b border-border bg-card flex flex-wrap items-center gap-5">
          <RunStatusBadge status={run.status} />
          {[
            { label: "Bank Close",  value: fmtAmount(run.bank_close) },
            { label: "GL Close",    value: fmtAmount(run.book_close) },
            { label: "Difference",  value: fmtAmount(difference), warn: difference !== 0 },
            { label: "Matched",     value: String(matchedCount) },
            { label: "Open Bank",   value: String(openBank.length), warn: openBank.length > 0 },
            { label: "Open GL",     value: String(openBook.length), warn: openBook.length > 0 },
            { label: "Proposed",    value: String(proposedCount), warn: proposedCount > 0 },
          ].map(s => (
            <div key={s.label}>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wide">{s.label}</p>
              <p className={cn("text-[14px] font-semibold tabular-nums mt-0.5",
                (s as any).warn ? "text-amber-600" : "text-foreground")}>
                {s.value}
              </p>
            </div>
          ))}
          <div className="flex-1" />
          {run.signed_at ? (
            <div className="flex items-center gap-1.5 text-emerald-600 text-[12px]">
              <CheckCircle2 className="w-3.5 h-3.5" /> Signed: {run.checker}
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
              <span className="text-[12px] text-amber-600">Awaiting sign-off</span>
              {run.status === "RECONCILED" && <SignoffButton runId={run.run_id} />}
            </div>
          )}
        </div>

        <div className="p-6 space-y-4">

          {/* Payout 3-way check results */}
          {payoutCheck && payoutCheck.total > 0 && (
            <div className="rounded-xl border border-border overflow-hidden bg-card">
              <div className="flex items-center justify-between px-5 py-3 border-b border-border">
                <div className="flex items-center gap-2">
                  <Shield className="w-4 h-4 text-blue-600" />
                  <span className="text-[13px] font-semibold">Payout Instruction Cross-Check</span>
                </div>
                <div className="flex gap-2 text-[11px]">
                  {payoutCheck.matched_3way > 0 && <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">{payoutCheck.matched_3way} matched</span>}
                  {payoutCheck.amount_mismatch > 0 && <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">{payoutCheck.amount_mismatch} amount mismatch</span>}
                  {payoutCheck.no_approval > 0 && <span className="px-2 py-0.5 rounded-full bg-red-100 text-red-700">{payoutCheck.no_approval} ⚠ no approval</span>}
                </div>
              </div>
              {payoutCheck.results?.map((r: any) => (
                <div key={r.bank_line_id} className="px-5 py-3 flex items-start gap-3 border-b border-border last:border-b-0">
                  <div className={cn("mt-0.5 shrink-0",
                    r.status === "matched_3way" ? "text-emerald-500" :
                    r.status === "no_approval" ? "text-red-500" : "text-amber-500")}>
                    {r.status === "matched_3way" ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[12px] font-semibold">{r.instruction_id} — ₦{((r.bank_amount_kobo ?? 0) / 100).toLocaleString("en-NG", { minimumFractionDigits: 2 })}</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">{r.narration?.slice(0, 80)}</p>
                    <p className={cn("text-[11px] mt-1",
                      r.status === "matched_3way" ? "text-emerald-600" :
                      r.status === "no_approval" ? "text-red-600" : "text-amber-600")}>
                      {r.notes}
                    </p>
                  </div>
                  {r.payout_request_id && (
                    <Link href={`/payouts/${r.payout_request_id}`} className="text-[11px] text-blue-600 hover:underline shrink-0">
                      View approval ↗
                    </Link>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Balance Rec (collapsible) */}
          <div>
            <button onClick={() => setShowBalRec(v => !v)}
              className="flex items-center gap-2 text-[12px] font-medium text-muted-foreground hover:text-foreground transition-colors mb-2">
              {showBalRec ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              Balance Reconciliation Statement
            </button>
            {showBalRec && (
              <div className="rounded-xl border border-border overflow-hidden bg-card max-w-xl">
                {[
                  { label: "Bank closing balance", value: run.bank_close, bold: true, accent: false },
                  openBank.filter(t => t.amount > 0).length > 0 && {
                    label: `Credits in bank, not in GL (${openBank.filter(t => t.amount > 0).length})`,
                    value: openBank.filter(t => t.amount > 0).reduce((s, t) => s + t.amount, 0),
                    bold: false, accent: false, indent: true,
                  },
                  openBank.filter(t => t.amount < 0).length > 0 && {
                    label: `Debits in bank, not in GL (${openBank.filter(t => t.amount < 0).length})`,
                    value: openBank.filter(t => t.amount < 0).reduce((s, t) => s + t.amount, 0),
                    bold: false, accent: false, indent: true,
                  },
                  { label: "GL closing balance", value: run.book_close, bold: true, accent: false },
                  { label: "Difference", value: difference, bold: true, accent: true },
                ].filter(Boolean).map((row: any, i) => (
                  <div key={i} className={cn(
                    "flex items-center justify-between border-b border-border last:border-b-0",
                    row.indent ? "px-10 py-2.5" : "px-6 py-3.5",
                    row.accent && difference !== 0 ? "bg-amber-50" : row.accent ? "bg-emerald-50" : ""
                  )}>
                    <span className={cn("text-[13px]", row.bold ? "font-semibold" : "text-muted-foreground")}>{row.label}</span>
                    <span className={cn("text-[14px] tabular-nums", row.bold ? "font-bold" : "font-medium",
                      row.accent && difference !== 0 ? "text-amber-700" : row.accent ? "text-emerald-700" : "")}>
                      {fmtAmount(row.value)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Filter bar */}
          <div className="flex items-center gap-1 p-1 bg-muted/40 rounded-xl w-fit border border-border">
            {([
              { key: "all",            label: "All",       count: totalRows },
              { key: "matched",        label: "Matched",   count: matchedCount },
              { key: "proposed",       label: "Proposed",  count: proposedCount },
              { key: "unmatched_bank", label: "Open Bank", count: openBank.length },
              { key: "unmatched_book", label: "Open GL",   count: openBook.length },
            ] as { key: FilterType; label: string; count: number }[]).map(f => (
              <button key={f.key} onClick={() => setFilter(f.key)}
                className={cn(
                  "flex items-center gap-1.5 h-7 px-3 rounded-lg text-[11px] font-medium transition-all",
                  filter === f.key ? "bg-white shadow text-foreground border border-border" : "text-muted-foreground hover:text-foreground"
                )}>
                {f.label}
                <span className={cn(
                  "text-[9px] font-bold px-1 py-0.5 rounded-full",
                  filter === f.key ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground",
                  (f.key === "unmatched_bank" || f.key === "unmatched_book") && f.count > 0 ? "bg-amber-100 text-amber-700" : "",
                  f.key === "proposed" && f.count > 0 ? "bg-blue-100 text-blue-700" : "",
                )}>
                  {f.count}
                </span>
              </button>
            ))}
            <button onClick={() => refetch()} className="ml-2 h-7 w-7 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Match table */}
          <div className="rounded-xl border border-border overflow-hidden bg-card">
            {/* Column headers */}
            <div className="grid border-b border-border bg-muted/20" style={{ gridTemplateColumns: "1fr 72px 1fr" }}>
              <div className="px-4 py-2.5 text-[11px] font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                <ArrowDownLeft className="w-3.5 h-3.5" /> Bank Statement
              </div>
              <div className="border-x border-border flex items-center justify-center">
                <span className="text-[9px] font-medium text-muted-foreground uppercase tracking-wide">Rule</span>
              </div>
              <div className="px-4 py-2.5 text-[11px] font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5" /> General Ledger
              </div>
            </div>

            {rows.length === 0 ? (
              <div className="px-6 py-12 text-center text-[13px] text-muted-foreground">
                No {filter === "all" ? "transactions" : filter.replace("_", " ")} in this run.
              </div>
            ) : (
              <div>
                {rows.slice(0, 200).map((row, i) => (
                  <div key={i} className={cn(
                    "grid border-b border-border last:border-b-0 hover:bg-muted/20 transition-colors",
                    row.type === "unmatched_bank" || row.type === "unmatched_book" ? "bg-amber-50/30" : "",
                    row.type === "proposed" ? "bg-blue-50/20" : "",
                  )} style={{ gridTemplateColumns: "1fr 72px 1fr" }}>
                    <TxnCell txn={row.bankTxn} side="BANK" />
                    <div className="flex flex-col items-center justify-center px-1 py-3 border-x border-border">
                      {row.m?.rule ? (
                        <>
                          <RuleBadge rule={row.m.rule} />
                          {row.m.confidence != null && (
                            <span className="text-[9px] text-muted-foreground mt-0.5">{Math.round((row.m.confidence ?? 0) * 100)}%</span>
                          )}
                        </>
                      ) : (
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                      )}
                    </div>
                    <TxnCell txn={row.bookTxn} side="GL" />
                  </div>
                ))}
                {rows.length > 200 && (
                  <div className="px-6 py-3 text-center text-[12px] text-muted-foreground border-t border-border">
                    Showing first 200 of {rows.length}. Download Excel for the full export.
                  </div>
                )}
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}
