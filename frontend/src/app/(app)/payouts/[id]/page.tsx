"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Topbar } from "@/components/layout/topbar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch, currentUser } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  PayoutDetail, ApprovalStep, StepStatus, RequestStatus,
} from "@/lib/types";
import {
  ArrowLeft, AlertTriangle, CheckCircle2, XCircle, RotateCcw,
  Clock, Building2, User, Printer, RefreshCw, Banknote, Paperclip,
} from "lucide-react";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtNaira(kobo: number) {
  return new Intl.NumberFormat("en-NG", {
    style: "currency",
    currency: "NGN",
    minimumFractionDigits: 2,
  }).format(kobo / 100);
}

function fmtDateTime(iso?: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function fmtRelative(iso?: string | null) {
  if (!iso) return "";
  const diff = new Date(iso).getTime() - Date.now();
  const abs  = Math.abs(diff);
  const mins = Math.round(abs / 60_000);
  const hrs  = Math.round(abs / 3_600_000);
  const past = diff < 0;
  if (abs < 60_000)     return past ? "just now" : "in <1 min";
  if (abs < 3_600_000)  return past ? `${mins}m ago` : `in ${mins}m`;
  return past ? `${hrs}h ago` : `in ${hrs}h`;
}

const STATUS_COLORS: Record<RequestStatus, string> = {
  draft:               "bg-gray-100 text-gray-600 border-gray-200",
  submitted:           "bg-amber-100 text-amber-700 border-amber-200",
  head_concur:         "bg-amber-100 text-amber-700 border-amber-200",
  internal_control:    "bg-amber-100 text-amber-700 border-amber-200",
  compliance:          "bg-amber-100 text-amber-700 border-amber-200",
  finance:             "bg-amber-100 text-amber-700 border-amber-200",
  pending_signatories: "bg-amber-100 text-amber-700 border-amber-200",
  approved:            "bg-blue-100 text-blue-700 border-blue-200",
  sent_to_bank:        "bg-indigo-100 text-indigo-700 border-indigo-200",
  confirmed:           "bg-emerald-100 text-emerald-700 border-emerald-200",
  reconciled:          "bg-emerald-100 text-emerald-700 border-emerald-200",
  returned:            "bg-orange-100 text-orange-700 border-orange-200",
  rejected:            "bg-red-100 text-red-700 border-red-200",
};

const STATUS_LABEL: Record<RequestStatus, string> = {
  draft:               "Draft",
  submitted:           "Submitted",
  head_concur:         "Head Concur",
  internal_control:    "Internal Control",
  compliance:          "Compliance",
  finance:             "Finance",
  pending_signatories: "Pending Signatories",
  approved:            "Approved",
  sent_to_bank:        "Sent to Bank",
  confirmed:           "Confirmed",
  reconciled:          "Reconciled",
  returned:            "Returned",
  rejected:            "Rejected",
};

const STEP_TYPE_LABEL: Record<string, string> = {
  head_concur:      "Head Concurrence",
  internal_control: "Internal Control",
  compliance:       "Compliance",
  finance:          "Finance",
  signatory_1:      "Signatory 1",
  signatory_2:      "Signatory 2",
  md:               "MD",
  ceo:              "CEO",
};

function stepIcon(status: StepStatus) {
  switch (status) {
    case "approved": return <CheckCircle2 className="w-4 h-4 text-emerald-500" />;
    case "returned": return <RotateCcw    className="w-4 h-4 text-orange-500" />;
    case "rejected": return <XCircle      className="w-4 h-4 text-red-500"    />;
    case "skipped":  return <CheckCircle2 className="w-4 h-4 text-gray-300"   />;
    default:         return <Clock        className="w-4 h-4 text-amber-400"  />;
  }
}

// ── Reason dialog ──────────────────────────────────────────────────────────────

function ReasonDialog({
  open,
  title,
  onClose,
  onConfirm,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  onConfirm: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-card border border-border rounded-xl shadow-xl p-6 w-full max-w-md space-y-4">
        <h3 className="text-[14px] font-semibold text-foreground">{title}</h3>
        <div className="space-y-1.5">
          <Label className="text-[12px]">Reason / Notes</Label>
          <Textarea
            className="resize-none min-h-[80px]"
            placeholder="Required…"
            value={reason}
            onChange={e => setReason(e.target.value)}
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={() => { setReason(""); onClose(); }}>Cancel</Button>
          <Button size="sm" disabled={!reason.trim()} onClick={() => { onConfirm(reason); setReason(""); }}>
            Confirm
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Bank ref dialog ────────────────────────────────────────────────────────────

function BankRefDialog({
  open,
  onClose,
  onConfirm,
  title,
  label,
  placeholder,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: (ref: string) => void;
  title: string;
  label: string;
  placeholder: string;
}) {
  const [ref, setRef] = useState("");
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-card border border-border rounded-xl shadow-xl p-6 w-full max-w-md space-y-4">
        <h3 className="text-[14px] font-semibold text-foreground">{title}</h3>
        <div className="space-y-1.5">
          <Label className="text-[12px]">{label}</Label>
          <Input placeholder={placeholder} value={ref} onChange={e => setRef(e.target.value)} />
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={() => { setRef(""); onClose(); }}>Cancel</Button>
          <Button size="sm" disabled={!ref.trim()} onClick={() => { onConfirm(ref); setRef(""); }}>
            Confirm
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PayoutDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id     = params.id as string;

  const [data,    setData]    = useState<PayoutDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting,  setActing]  = useState(false);
  const [actionError, setActionError] = useState("");

  // dialogs
  const [returnDialog, setReturnDialog] = useState(false);
  const [rejectDialog, setRejectDialog] = useState(false);
  const [bankRefDialog, setBankRefDialog]   = useState(false);
  const [confirmDialog, setConfirmDialog]   = useState(false);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const me = typeof window !== "undefined" ? currentUser() : null;

  const load = useCallback(() => {
    apiFetch<PayoutDetail>(`/api/payouts/${id}`)
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    load();
    timerRef.current = setInterval(load, 30_000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [load]);

  // ── Actions ────────────────────────────────────────────────────────────────

  async function act(action: "approve" | "return" | "reject", notes = "") {
    setActing(true);
    setActionError("");
    try {
      await apiFetch(`/api/payouts/${id}/act`, {
        method: "POST",
        body: JSON.stringify({ action, notes }),
      });
      load();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Action failed.";
      setActionError(msg);
    } finally {
      setActing(false);
    }
  }

  async function markSentToBank(ref: string) {
    setActing(true);
    setActionError("");
    try {
      await apiFetch(`/api/payouts/${id}/dispatch`, {
        method: "POST",
        body: JSON.stringify({ bank_reference: ref }),
      });
      load();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to mark sent to bank.");
    } finally {
      setActing(false);
    }
  }

  async function attachConfirmation(ref: string) {
    setActing(true);
    setActionError("");
    try {
      await apiFetch(`/api/payouts/${id}/confirm`, {
        method: "POST",
        body: JSON.stringify({ bank_reference: ref }),
      });
      load();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to attach confirmation.");
    } finally {
      setActing(false);
    }
  }

  // ── Derived ────────────────────────────────────────────────────────────────

  const req    = data?.request;
  const steps  = data?.steps ?? [];
  const log    = data?.log   ?? [];

  // step currently pending and assigned to me
  const myStep: ApprovalStep | undefined = steps.find(
    s => s.status === "pending" && (
      s.assigned_to === me?.name ||
      s.assigned_to === (me as unknown as { email?: string })?.email
    ),
  );

  // ── Render ─────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex flex-col flex-1 overflow-hidden">
        <Topbar title="Loading…" />
        <div className="flex-1 p-6 space-y-4 max-w-4xl mx-auto w-full">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      </div>
    );
  }

  if (!req) {
    return (
      <div className="flex flex-col flex-1 overflow-hidden">
        <Topbar title="Not found" />
        <div className="flex-1 p-6 flex items-center justify-center">
          <p className="text-[14px] text-muted-foreground">Request not found or you do not have access.</p>
        </div>
      </div>
    );
  }

  const statusColor = STATUS_COLORS[req.status] ?? "bg-gray-100 text-gray-600 border-gray-200";

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <Topbar
        title={req.instruction_id}
        subtitle={`${req.entity} · ${req.request_type.replace(/_/g, " ")}`}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 text-[12px]"
              onClick={() => window.open(`/api/payouts/${id}/letter`, "_blank")}
            >
              <Printer className="w-3.5 h-3.5" />
              Print Letter
            </Button>
            <Button variant="ghost" size="sm" className="gap-1.5 text-[12px]" onClick={() => router.push("/payouts")}>
              <ArrowLeft className="w-3.5 h-3.5" />
              Back
            </Button>
          </div>
        }
      />

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto space-y-5">

          {/* Status bar */}
          <div className="flex items-center gap-3">
            <span className={cn("inline-flex items-center px-3 py-1 rounded-full text-[12px] font-medium border", statusColor)}>
              {STATUS_LABEL[req.status] ?? req.status}
            </span>
            <span className="text-[12px] text-muted-foreground">
              Last updated {fmtDateTime(req.updated_at)}
            </span>
          </div>

          {/* Compliance banner */}
          {req.compliance_flagged && (
            <div className="bg-amber-50 border border-amber-200 text-amber-700 text-[13px] px-4 py-3 rounded-lg flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              Compliance flagged — beneficiary not in registered client list. Compliance step has been inserted.
            </div>
          )}

          {/* Action error */}
          {actionError && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-[13px] px-4 py-3 rounded-lg flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              {actionError}
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

            {/* ── Left: Info + Timeline + Log ────────────────────────── */}
            <div className="lg:col-span-2 space-y-5">

              {/* Info card */}
              <div className="bg-card border border-border rounded-xl p-5 space-y-4">
                <h3 className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wide">Payment Details</h3>
                <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-[13px]">
                  <div>
                    <dt className="text-muted-foreground text-[11px]">Amount</dt>
                    <dd className="font-semibold tabular-nums text-foreground mt-0.5">{fmtNaira(req.amount_kobo)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground text-[11px]">Request Type</dt>
                    <dd className="font-medium text-foreground mt-0.5 capitalize">{req.request_type.replace(/_/g, " ")}</dd>
                  </div>
                  <div className="col-span-2">
                    <dt className="text-muted-foreground text-[11px]">Beneficiary</dt>
                    <dd className="font-medium text-foreground mt-0.5">{req.beneficiary_name}</dd>
                    <dd className="text-muted-foreground text-[12px]">{req.beneficiary_bank} · {req.beneficiary_account}</dd>
                  </div>
                  <div className="col-span-2">
                    <dt className="text-muted-foreground text-[11px]">Purpose</dt>
                    <dd className="text-foreground mt-0.5 leading-relaxed">{req.purpose}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground text-[11px] flex items-center gap-1"><Building2 className="w-3 h-3" />Entity</dt>
                    <dd className="font-medium text-foreground mt-0.5">{req.entity}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground text-[11px] flex items-center gap-1"><User className="w-3 h-3" />Raised By</dt>
                    <dd className="font-medium text-foreground mt-0.5">{req.raised_by}</dd>
                  </div>
                  {req.bank_reference && (
                    <div className="col-span-2">
                      <dt className="text-muted-foreground text-[11px]">Bank Reference</dt>
                      <dd className="font-mono text-foreground mt-0.5">{req.bank_reference}</dd>
                    </div>
                  )}
                  {req.submitted_at && (
                    <div>
                      <dt className="text-muted-foreground text-[11px]">Submitted</dt>
                      <dd className="text-foreground mt-0.5">{fmtDateTime(req.submitted_at)}</dd>
                    </div>
                  )}
                  {req.approved_at && (
                    <div>
                      <dt className="text-muted-foreground text-[11px]">Approved</dt>
                      <dd className="text-foreground mt-0.5">{fmtDateTime(req.approved_at)}</dd>
                    </div>
                  )}
                </dl>
              </div>

              {/* Approval timeline */}
              <div className="bg-card border border-border rounded-xl p-5">
                <h3 className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wide mb-4">Approval Timeline</h3>
                <div className="space-y-0">
                  {steps.map((step, i) => (
                    <div key={step.id} className="flex gap-3">
                      {/* line */}
                      <div className="flex flex-col items-center">
                        <div className={cn(
                          "w-7 h-7 rounded-full flex items-center justify-center shrink-0 border-2",
                          step.status === "approved" ? "border-emerald-400 bg-emerald-50" :
                          step.status === "returned" ? "border-orange-400 bg-orange-50"  :
                          step.status === "rejected" ? "border-red-400 bg-red-50"         :
                          step.status === "skipped"  ? "border-gray-200 bg-gray-50"       :
                          "border-amber-300 bg-amber-50",
                        )}>
                          {stepIcon(step.status)}
                        </div>
                        {i < steps.length - 1 && (
                          <div className="w-px flex-1 bg-border min-h-[20px] my-1" />
                        )}
                      </div>
                      {/* content */}
                      <div className="pb-5 flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="text-[13px] font-medium text-foreground">
                              {STEP_TYPE_LABEL[step.step_type] ?? step.step_type}
                            </p>
                            <p className="text-[11px] text-muted-foreground mt-0.5">
                              {step.assigned_to}
                              {step.stand_in_for && <span className="italic"> (stand-in for {step.stand_in_for})</span>}
                            </p>
                          </div>
                          <div className="text-right shrink-0">
                            {step.decided_at ? (
                              <p className="text-[11px] text-muted-foreground">{fmtDateTime(step.decided_at)}</p>
                            ) : (
                              <p className={cn(
                                "text-[11px]",
                                new Date(step.due_by) < new Date() ? "text-red-500" : "text-amber-600",
                              )}>
                                Due {fmtRelative(step.due_by)}
                              </p>
                            )}
                          </div>
                        </div>
                        {step.notes && (
                          <p className="text-[12px] text-muted-foreground mt-1 italic">{step.notes}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Action log */}
              <div className="bg-card border border-border rounded-xl p-5">
                <h3 className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wide mb-3">Action Log</h3>
                {log.length === 0 ? (
                  <p className="text-[12px] text-muted-foreground">No actions recorded yet.</p>
                ) : (
                  <div className="space-y-2">
                    {log.map(entry => (
                      <div key={entry.id} className="flex items-start gap-3 text-[12px]">
                        <span className="text-muted-foreground shrink-0 w-32">{fmtDateTime(entry.created_at)}</span>
                        <span className="font-medium text-foreground shrink-0">{entry.actor_email}</span>
                        <span className="text-muted-foreground capitalize">{entry.action.replace(/_/g, " ")}</span>
                        {entry.notes && <span className="text-muted-foreground italic">— {entry.notes}</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>

            </div>

            {/* ── Right: Action panel ─────────────────────────────────── */}
            <div className="space-y-4">

              {/* Approval actions */}
              {myStep && (
                <div className="bg-card border border-border rounded-xl p-5 space-y-3">
                  <h3 className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wide">Your Action Required</h3>
                  <p className="text-[12px] text-muted-foreground">
                    Step: <span className="font-medium text-foreground">{STEP_TYPE_LABEL[myStep.step_type] ?? myStep.step_type}</span>
                    <br />Due {fmtRelative(myStep.due_by)}
                  </p>
                  <div className="space-y-2 pt-1">
                    <Button
                      className="w-full gap-1.5"
                      size="sm"
                      disabled={acting}
                      onClick={() => act("approve")}
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Approve
                    </Button>
                    <Button
                      className="w-full gap-1.5"
                      size="sm"
                      variant="outline"
                      disabled={acting}
                      onClick={() => setReturnDialog(true)}
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      Return
                    </Button>
                    <Button
                      className="w-full gap-1.5"
                      size="sm"
                      variant="outline"
                      disabled={acting}
                      onClick={() => setRejectDialog(true)}
                    >
                      <XCircle className="w-3.5 h-3.5 text-red-500" />
                      <span className="text-red-600">Reject</span>
                    </Button>
                  </div>
                </div>
              )}

              {/* Mark sent to bank */}
              {req.status === "approved" && (
                <div className="bg-card border border-border rounded-xl p-5 space-y-3">
                  <h3 className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wide">Dispatch</h3>
                  <p className="text-[12px] text-muted-foreground">
                    This request is fully approved. Mark it as sent to bank once the wire is initiated.
                  </p>
                  <Button
                    className="w-full gap-1.5"
                    size="sm"
                    disabled={acting}
                    onClick={() => setBankRefDialog(true)}
                  >
                    <Banknote className="w-3.5 h-3.5" />
                    Mark Sent to Bank
                  </Button>
                </div>
              )}

              {/* Attach confirmation */}
              {req.status === "sent_to_bank" && (
                <div className="bg-card border border-border rounded-xl p-5 space-y-3">
                  <h3 className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wide">Confirmation</h3>
                  <p className="text-[12px] text-muted-foreground">
                    Attach the bank debit confirmation reference once received.
                  </p>
                  <Button
                    className="w-full gap-1.5"
                    size="sm"
                    disabled={acting}
                    onClick={() => setConfirmDialog(true)}
                  >
                    <Paperclip className="w-3.5 h-3.5" />
                    Attach Confirmation
                  </Button>
                </div>
              )}

              {/* Refresh indicator */}
              <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground justify-center">
                <RefreshCw className="w-3 h-3 animate-spin-slow" />
                Auto-refreshes every 30s
              </div>

            </div>
          </div>
        </div>
      </div>

      {/* ── Dialogs ──────────────────────────────────────────────────────── */}
      <ReasonDialog
        open={returnDialog}
        title="Return Request"
        onClose={() => setReturnDialog(false)}
        onConfirm={reason => { setReturnDialog(false); act("return", reason); }}
      />
      <ReasonDialog
        open={rejectDialog}
        title="Reject Request"
        onClose={() => setRejectDialog(false)}
        onConfirm={reason => { setRejectDialog(false); act("reject", reason); }}
      />
      <BankRefDialog
        open={bankRefDialog}
        title="Mark Sent to Bank"
        label="Bank / Session Reference"
        placeholder="e.g. FT2310151234"
        onClose={() => setBankRefDialog(false)}
        onConfirm={ref => { setBankRefDialog(false); markSentToBank(ref); }}
      />
      <BankRefDialog
        open={confirmDialog}
        title="Attach Bank Confirmation"
        label="Bank Debit Reference"
        placeholder="e.g. DR-00293847"
        onClose={() => setConfirmDialog(false)}
        onConfirm={ref => { setConfirmDialog(false); attachConfirmation(ref); }}
      />
    </div>
  );
}
