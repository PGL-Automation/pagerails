"use client";

import { useState, useEffect, useCallback } from "react";
import { Topbar } from "@/components/layout/topbar";
import { RuleBadge } from "@/components/domain/status-badge";
import { fmtAmount, fmtDate, fmtConfidence, amountClass } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Check, X, ChevronLeft, ChevronRight, Keyboard, Loader2, CheckCircle2, Database } from "lucide-react";
import { cn } from "@/lib/utils";
import { getToken, submitDecisions } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Txn {
  uid: string; side: string; account_id: string; txn_date: string;
  amount: number; description: string; reference: string;
  source: string; source_row: number; doc_type: string; category: string;
}

interface ProposedMatch {
  match_id: string; run_id: string; rule: string; confidence: number;
  bank_uids: string[]; book_uids: string[]; status: string;
  difference: number; note: string;
  bank_txns: Txn[]; book_txns: Txn[];
}

type Decision = { action: "APPROVE" | "REJECT"; note: string } | null;

// ── Fetcher ───────────────────────────────────────────────────────────────────

async function fetchProposed(): Promise<{ runId: string; matches: ProposedMatch[] }> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const token = getToken();

  // Get most recent run
  const runsRes = await fetch(`${base}/api/runs/`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const runs: any[] = await runsRes.json();
  if (!runs.length) return { runId: "", matches: [] };

  const latestRunId = runs[0].run_id;
  const propRes = await fetch(`${base}/api/runs/${encodeURIComponent(latestRunId)}/proposed`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const matches = await propRes.json();
  return { runId: latestRunId, matches: Array.isArray(matches) ? matches : [] };
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ReviewPage() {
  const [matches, setMatches] = useState<ProposedMatch[]>([]);
  const [runId, setRunId]     = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");
  const [current, setCurrent] = useState(0);
  const [note, setNote]       = useState("");
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted]   = useState(false);

  useEffect(() => {
    fetchProposed()
      .then(({ runId, matches }) => { setRunId(runId); setMatches(matches); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.target as HTMLElement).tagName === "TEXTAREA") return;
      if (e.key === "a" || e.key === "A") decide("APPROVE");
      if (e.key === "r" || e.key === "R") decide("REJECT");
      if (e.key === "ArrowRight" || e.key === "j") setCurrent(c => Math.min(c + 1, matches.length - 1));
      if (e.key === "ArrowLeft"  || e.key === "k") setCurrent(c => Math.max(c - 1, 0));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [matches, current, note]);

  function decide(action: "APPROVE" | "REJECT") {
    if (!matches[current]) return;
    const m = matches[current];
    setDecisions(prev => ({ ...prev, [m.match_id]: { action, note } }));
    setNote("");
    if (current < matches.length - 1) setCurrent(c => c + 1);
  }

  async function submitAll() {
    const entries = Object.entries(decisions).filter(([, d]) => d !== null);
    if (!entries.length) return;
    setSubmitting(true);
    try {
      const payload = entries.flatMap(([matchId, d]) => {
        const m = matches.find(x => x.match_id === matchId);
        if (!m || !d) return [];   // skip if match or decision is missing
        return [{
          account_id: (m.run_id ?? "").split("-").slice(0, -2).join("-"),
          action: d.action,
          bank_uids: m.bank_uids ?? [],
          book_uids: m.book_uids ?? [],
          note: d.note ?? "",
        }];
      });
      const userRaw = typeof window !== "undefined" ? sessionStorage.getItem("recon_user") : null;
      const userName = userRaw ? JSON.parse(userRaw).name : "Reviewer";
      await submitDecisions({ reviewer: userName, decisions: payload });
      setSubmitted(true);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  const done     = Object.keys(decisions).length;
  const approved = Object.values(decisions).filter(d => d?.action === "APPROVE").length;
  const rejected = Object.values(decisions).filter(d => d?.action === "REJECT").length;
  const match    = matches[current];

  // ── Loading ───────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex flex-col flex-1 overflow-hidden">
        <Topbar title="Review Queue" subtitle="Loading…" />
        <div className="flex-1 flex items-center justify-center gap-2 text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-[13px]">Fetching proposed matches…</span>
        </div>
      </div>
    );
  }

  if (matches.length === 0) {
    return (
      <div className="flex flex-col flex-1 overflow-hidden">
        <Topbar title="Review Queue" subtitle="No proposed matches" />
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center p-6">
          <Database className="w-8 h-8 text-muted-foreground" />
          <p className="text-[14px] font-medium">No proposed matches to review</p>
          <p className="text-[12px] text-muted-foreground max-w-sm">
            {error || "All current matches are either auto-accepted or no runs exist yet. Trigger a new run to generate proposed matches."}
          </p>
        </div>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="flex flex-col flex-1 overflow-hidden">
        <Topbar title="Review Queue" subtitle="Decisions submitted" />
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center">
          <CheckCircle2 className="w-10 h-10 text-emerald-500" />
          <p className="text-[15px] font-semibold">Decisions recorded</p>
          <p className="text-[12px] text-muted-foreground">
            {approved} approved · {rejected} rejected · Re-run the period to apply them.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <Topbar
        title="Review Queue"
        subtitle={`${matches.length} proposed matches · ${done} reviewed · ${runId}`}
        actions={
          <Button
            size="sm"
            className="h-8 text-[12px]"
            disabled={done === 0 || submitting}
            onClick={submitAll}
          >
            {submitting
              ? <><Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />Submitting…</>
              : `Submit ${done} Decision${done !== 1 ? "s" : ""}`
            }
          </Button>
        }
      />

      <div className="flex-1 overflow-auto">
        <div className="max-w-4xl mx-auto p-6 space-y-4">

          {/* Progress track */}
          <div className="flex items-center gap-3">
            <div className="flex-1 flex gap-0.5">
              {matches.map((m, i) => {
                const d = decisions[m.match_id];
                return (
                  <button
                    key={m.match_id}
                    onClick={() => setCurrent(i)}
                    className={cn(
                      "h-1.5 flex-1 rounded-full transition-all",
                      i === current
                        ? "bg-foreground scale-y-125"
                        : d?.action === "APPROVE" ? "bg-emerald-400"
                        : d?.action === "REJECT"  ? "bg-red-400"
                        : "bg-muted"
                    )}
                  />
                );
              })}
            </div>
            <span className="text-[11px] text-muted-foreground shrink-0 tabular-nums">
              {current + 1} / {matches.length}
            </span>
          </div>

          {/* Match card */}
          <MatchCard match={match} decision={decisions[match.match_id] ?? null} />

          {/* Controls */}
          <div className="bg-card border border-border rounded-xl p-4 space-y-3">
            <Textarea
              placeholder="Optional note (required if rejecting)…"
              className="text-[13px] resize-none h-16 border-0 bg-muted/30 focus-visible:ring-1"
              value={note}
              onChange={e => setNote(e.target.value)}
            />

            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                className="flex-1 h-10 gap-2 text-[13px] border-red-200 text-red-700 hover:bg-red-50"
                onClick={() => decide("REJECT")}
              >
                <X className="w-4 h-4" /> Reject
                <kbd className="ml-auto text-[10px] text-muted-foreground bg-muted rounded px-1">R</kbd>
              </Button>
              <Button
                className="flex-1 h-10 gap-2 text-[13px] bg-emerald-600 hover:bg-emerald-700 text-white"
                onClick={() => decide("APPROVE")}
              >
                <Check className="w-4 h-4" /> Approve
                <kbd className="ml-auto text-[10px] bg-emerald-700/50 text-emerald-100 rounded px-1">A</kbd>
              </Button>
            </div>

            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
              <Button variant="ghost" size="sm" className="h-7 gap-1"
                disabled={current === 0} onClick={() => setCurrent(c => c - 1)}>
                <ChevronLeft className="w-3.5 h-3.5" /> Prev
              </Button>
              <div className="flex items-center gap-3">
                <span className="text-emerald-600">{approved} approved</span>
                <span>·</span>
                <span className="text-red-600">{rejected} rejected</span>
                <span>·</span>
                <span className="flex items-center gap-1"><Keyboard className="w-3 h-3" /> A/R/←/→</span>
              </div>
              <Button variant="ghost" size="sm" className="h-7 gap-1"
                disabled={current === matches.length - 1} onClick={() => setCurrent(c => c + 1)}>
                Next <ChevronRight className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

// ── Match card ────────────────────────────────────────────────────────────────

function MatchCard({ match, decision }: { match: ProposedMatch; decision: Decision }) {
  return (
    <div className={cn(
      "bg-card border rounded-xl overflow-hidden transition-colors",
      decision?.action === "APPROVE" ? "border-emerald-300"
      : decision?.action === "REJECT"  ? "border-red-300"
      : "border-border"
    )}>
      {/* Header */}
      <div className="px-5 py-3 border-b border-border flex items-center gap-3 bg-muted/20">
        <span className="text-[11px] font-mono text-muted-foreground">{match.match_id}</span>
        <RuleBadge rule={match.rule} />
        <div className="flex items-center gap-2">
          <div className="w-20 h-1.5 rounded-full bg-gray-100 overflow-hidden">
            <div
              className={cn("h-full rounded-full", match.confidence >= 0.9 ? "bg-emerald-500" : "bg-amber-400")}
              style={{ width: `${match.confidence * 100}%` }}
            />
          </div>
          <span className="text-[12px] font-medium tabular-nums">{fmtConfidence(match.confidence)}</span>
        </div>
        <div className="flex-1" />
        {match.note && <span className="text-[11px] text-muted-foreground italic truncate max-w-xs">{match.note}</span>}
        {decision && (
          <span className={cn(
            "text-[11px] font-medium px-2 py-0.5 rounded-full shrink-0",
            decision.action === "APPROVE"
              ? "bg-emerald-50 text-emerald-700"
              : "bg-red-50 text-red-700"
          )}>
            {decision.action === "APPROVE" ? "✓ Approved" : "✗ Rejected"}
          </span>
        )}
      </div>

      {/* Bank vs Book */}
      <div className="grid grid-cols-2 divide-x divide-border">
        {(["bank_txns", "book_txns"] as const).map((side, idx) => (
          <div key={side} className="p-5">
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-3">
              {idx === 0 ? "Bank Statement" : "Book / Ledger"}
            </p>
            {match[side].length ? match[side].map(t => (
              <div key={t.uid} className="space-y-1">
                <div className="flex items-baseline gap-2 flex-wrap">
                  <span className="text-[12px] text-muted-foreground">{fmtDate(t.txn_date)}</span>
                  <span className={cn("text-[20px] font-semibold tabular-nums", amountClass(t.amount))}>
                    {fmtAmount(t.amount)}
                  </span>
                </div>
                <p className="text-[13px] text-foreground leading-snug">{t.description}</p>
                {t.reference && (
                  <p className="text-[11px] font-mono text-muted-foreground">{t.reference}</p>
                )}
                <div className="flex items-center gap-2 pt-1 flex-wrap">
                  {t.doc_type && (
                    <span className="text-[10px] bg-slate-100 text-slate-600 rounded px-1.5 py-0.5 font-mono">
                      {t.doc_type}
                    </span>
                  )}
                  {t.category && (
                    <span className="text-[10px] bg-violet-50 text-violet-700 rounded px-1.5 py-0.5 font-medium">
                      {t.category.replace(/_/g, " ")}
                    </span>
                  )}
                  <span className="text-[10px] text-muted-foreground font-mono">
                    row {t.source_row}
                  </span>
                </div>
              </div>
            )) : (
              <p className="text-[12px] text-muted-foreground italic">No items on this side</p>
            )}
          </div>
        ))}
      </div>

      {match.difference !== 0 && (
        <div className="px-5 py-2 bg-amber-50/60 border-t border-amber-200 text-[11px] text-amber-700 font-medium">
          Tolerance difference: {fmtAmount(match.difference)} — requires manual review
        </div>
      )}
    </div>
  );
}
