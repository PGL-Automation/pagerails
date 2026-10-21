"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Topbar } from "@/components/layout/topbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { PaymentRequest, RequestStatus, RequestType } from "@/lib/types";
import {
  Clock, AlertCircle, ChevronRight, Plus, Filter,
} from "lucide-react";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtNaira(kobo: number) {
  return new Intl.NumberFormat("en-NG", {
    style: "currency",
    currency: "NGN",
    minimumFractionDigits: 2,
  }).format(kobo / 100);
}

function fmtDateTime(iso?: string) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
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

const TYPE_LABEL: Record<RequestType, string> = {
  client_payout: "Client Payout",
  liquidation:   "Liquidation",
  transfer:      "Transfer",
  expense:       "Expense",
  placement:     "Placement",
};

function StatusBadge({ status }: { status: RequestStatus }) {
  return (
    <span className={cn(
      "inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border",
      STATUS_COLORS[status] ?? "bg-gray-100 text-gray-600 border-gray-200",
    )}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

// ── Pending card ──────────────────────────────────────────────────────────────

function PendingCard({ req }: { req: PaymentRequest }) {
  const router = useRouter();
  return (
    <div className="bg-card border border-border rounded-xl p-4 flex flex-col gap-3 hover:border-primary/30 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[13px] font-mono font-semibold text-foreground">{req.instruction_id}</p>
          <p className="text-[11px] text-muted-foreground mt-0.5">{req.entity}</p>
        </div>
        <StatusBadge status={req.status} />
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[11px] bg-muted px-2 py-0.5 rounded-full text-muted-foreground">
          {TYPE_LABEL[req.request_type] ?? req.request_type}
        </span>
        <span className="text-[13px] font-semibold tabular-nums text-foreground">
          {fmtNaira(req.amount_kobo)}
        </span>
      </div>

      <div>
        <p className="text-[12px] font-medium text-foreground">{req.beneficiary_name}</p>
        <p className="text-[11px] text-muted-foreground">{req.beneficiary_bank}</p>
      </div>

      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1 text-[11px] text-amber-600">
          <Clock className="w-3 h-3" />
          <span>Updated {fmtDateTime(req.updated_at)}</span>
        </div>
        <Button
          size="sm"
          className="h-7 text-[12px]"
          onClick={() => router.push(`/payouts/${req.id}`)}
        >
          Review
        </Button>
      </div>
    </div>
  );
}

// ── All requests table row ────────────────────────────────────────────────────

function RequestRow({ req }: { req: PaymentRequest }) {
  const router = useRouter();
  return (
    <tr
      className="hover:bg-muted/30 cursor-pointer transition-colors"
      onClick={() => router.push(`/payouts/${req.id}`)}
    >
      <td className="px-4 py-3 text-[12px] font-mono font-medium whitespace-nowrap">
        {req.instruction_id}
      </td>
      <td className="px-4 py-3 text-[12px] text-muted-foreground whitespace-nowrap">
        {TYPE_LABEL[req.request_type] ?? req.request_type}
      </td>
      <td className="px-4 py-3 text-[12px] text-muted-foreground whitespace-nowrap">
        {req.entity}
      </td>
      <td className="px-4 py-3 text-[12px] tabular-nums font-medium whitespace-nowrap">
        {fmtNaira(req.amount_kobo)}
      </td>
      <td className="px-4 py-3 text-[12px] max-w-[160px] truncate">
        {req.beneficiary_name}
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={req.status} />
      </td>
      <td className="px-4 py-3 text-[12px] text-muted-foreground whitespace-nowrap">
        {req.raised_by}
      </td>
      <td className="px-4 py-3 text-[12px] text-muted-foreground whitespace-nowrap">
        {fmtDateTime(req.updated_at)}
      </td>
      <td className="px-4 py-3">
        <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
      </td>
    </tr>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const ALL_STATUSES: RequestStatus[] = [
  "draft","submitted","head_concur","internal_control","compliance",
  "finance","pending_signatories","approved","sent_to_bank",
  "confirmed","reconciled","returned","rejected",
];

export default function PayoutsPage() {
  const [pending, setPending]         = useState<PaymentRequest[]>([]);
  const [all, setAll]                 = useState<PaymentRequest[]>([]);
  const [loadingPending, setLoadingP] = useState(true);
  const [loadingAll, setLoadingA]     = useState(true);
  const [entityFilter, setEntityFilter]   = useState("");
  const [statusFilter, setStatusFilter]   = useState<RequestStatus | "">("");

  useEffect(() => {
    apiFetch<PaymentRequest[]>("/api/payouts/pending")
      .then(setPending)
      .catch(() => setPending([]))
      .finally(() => setLoadingP(false));
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (entityFilter) params.set("entity", entityFilter);
    if (statusFilter) params.set("status", statusFilter);
    setLoadingA(true);
    apiFetch<PaymentRequest[]>(`/api/payouts/?${params.toString()}`)
      .then(setAll)
      .catch(() => setAll([]))
      .finally(() => setLoadingA(false));
  }, [entityFilter, statusFilter]);

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <Topbar
        title="Payout Approvals"
        subtitle="Manage and track payment requests across entities"
        actions={
          <Link href="/payouts/new">
            <Button size="sm" className="h-8 gap-1.5 text-[12px]">
              <Plus className="w-3.5 h-3.5" />
              Raise Request
            </Button>
          </Link>
        }
      />

      <div className="flex-1 overflow-auto p-6 space-y-8">
        <div className="max-w-6xl mx-auto space-y-8">


          {/* ── Pending My Action ─────────────────────────────────────────── */}
          <section>
            <div className="flex items-center gap-3 mb-3">
              <h2 className="text-[13px] font-semibold text-foreground flex items-center gap-1.5">
                <AlertCircle className="w-4 h-4 text-amber-500" />
                Pending My Action
              </h2>
              {!loadingPending && pending.length > 0 && (
                <span className="text-[11px] bg-amber-100 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full font-medium">
                  {pending.length}
                </span>
              )}
              <div className="flex-1 h-px bg-border" />
            </div>

            {loadingPending && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-36 rounded-xl" />
                ))}
              </div>
            )}

            {!loadingPending && pending.length === 0 && (
              <div className="bg-muted/40 border border-border rounded-xl p-8 text-center">
                <p className="text-[13px] font-medium text-foreground">Nothing awaiting your action</p>
                <p className="text-[12px] text-muted-foreground mt-1">
                  Requests assigned to you will appear here.
                </p>
              </div>
            )}

            {!loadingPending && pending.length > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {pending.map(req => <PendingCard key={req.id} req={req} />)}
              </div>
            )}
          </section>

          {/* ── All Requests ──────────────────────────────────────────────── */}
          <section>
            <div className="flex items-center gap-3 mb-3">
              <h2 className="text-[13px] font-semibold text-foreground">All Requests</h2>
              <div className="flex-1 h-px bg-border" />
              {!loadingAll && (
                <span className="text-[11px] text-muted-foreground">{all.length} total</span>
              )}
            </div>

            {/* Filters */}
            <div className="flex items-center gap-2 mb-3">
              <Filter className="w-3.5 h-3.5 text-muted-foreground" />
              <select
                className="text-[12px] border border-border rounded-md px-2 py-1 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                value={entityFilter}
                onChange={e => setEntityFilter(e.target.value)}
              >
                <option value="">All Entities</option>
                <option value="PAM">Page Asset Management</option>
                <option value="PCL">Page Capital Limited</option>
              </select>
              <select
                className="text-[12px] border border-border rounded-md px-2 py-1 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                value={statusFilter}
                onChange={e => setStatusFilter(e.target.value as RequestStatus | "")}
              >
                <option value="">All Statuses</option>
                {ALL_STATUSES.map(s => (
                  <option key={s} value={s}>{STATUS_LABEL[s]}</option>
                ))}
              </select>
            </div>

            <div className="bg-card border border-border rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-border bg-muted/20">
                      <th className="px-4 py-2.5 text-[11px] font-medium text-muted-foreground uppercase tracking-wide">ID</th>
                      <th className="px-4 py-2.5 text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Type</th>
                      <th className="px-4 py-2.5 text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Entity</th>
                      <th className="px-4 py-2.5 text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Amount</th>
                      <th className="px-4 py-2.5 text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Beneficiary</th>
                      <th className="px-4 py-2.5 text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Status</th>
                      <th className="px-4 py-2.5 text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Raised By</th>
                      <th className="px-4 py-2.5 text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Updated</th>
                      <th className="px-4 py-2.5" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {loadingAll && Array.from({ length: 5 }).map((_, i) => (
                      <tr key={i}>
                        {Array.from({ length: 9 }).map((__, j) => (
                          <td key={j} className="px-4 py-3">
                            <Skeleton className="h-4 w-full" />
                          </td>
                        ))}
                      </tr>
                    ))}
                    {!loadingAll && all.length === 0 && (
                      <tr>
                        <td colSpan={9} className="px-4 py-10 text-center text-[13px] text-muted-foreground">
                          No requests found
                        </td>
                      </tr>
                    )}
                    {!loadingAll && all.map(req => <RequestRow key={req.id} req={req} />)}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

        </div>
      </div>
    </div>
  );
}
