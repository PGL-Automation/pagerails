"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Topbar } from "@/components/layout/topbar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch, BASE, getToken } from "@/lib/api";
import type { PaymentAccount, RequestType } from "@/lib/types";
import { ArrowLeft, CheckCircle2, AlertTriangle, Upload } from "lucide-react";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

interface BeneficiaryCheckResult {
  registered: boolean;
  name?: string;
}

const REQUEST_TYPES: { value: RequestType; label: string }[] = [
  { value: "client_payout", label: "Client Payout" },
  { value: "liquidation",   label: "Liquidation" },
  { value: "transfer",      label: "Transfer" },
  { value: "expense",       label: "Expense" },
  { value: "placement",     label: "Placement" },
];

const ENTITY_OPTIONS = [
  { value: "PAM", label: "Page Asset Management Limited" },
  { value: "PCL", label: "Page Capital Limited" },
];

// ── Helper ────────────────────────────────────────────────────────────────────

function FieldError({ msg }: { msg?: string }) {
  if (!msg) return null;
  return <p className="text-[11px] text-red-500 mt-0.5">{msg}</p>;
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function NewPayoutPage() {
  const router = useRouter();

  // form state
  const [entity,         setEntity]         = useState<"PAM" | "PCL">("PAM");
  const [requestType,    setRequestType]    = useState<RequestType>("client_payout");
  const [accountId,      setAccountId]      = useState<number | "">("");
  const [amountNaira,    setAmountNaira]    = useState("");
  const [beneficiaryName,   setBeneficiaryName]   = useState("");
  const [beneficiaryBank,   setBeneficiaryBank]   = useState("");
  const [beneficiaryAccount, setBeneficiaryAccount] = useState("");
  const [purpose,        setPurpose]        = useState("");

  // account list
  const [accounts,      setAccounts]      = useState<PaymentAccount[]>([]);
  const [loadingAccounts, setLoadingAccounts] = useState(false);

  // beneficiary check
  const [beneficiaryStatus, setBeneficiaryStatus] = useState<"idle" | "checking" | "registered" | "unregistered">("idle");

  // supporting document
  const [docFile,       setDocFile]       = useState<File | null>(null);
  const [docUploading,  setDocUploading]  = useState(false);
  const [docStatus,     setDocStatus]     = useState<"idle" | "success" | "error">("idle");
  const [docError,      setDocError]      = useState("");

  // submission
  const [submitting, setSubmitting] = useState(false);
  const [error,      setError]      = useState("");
  const [errors,     setErrors]     = useState<Record<string, string>>({});

  // Reload accounts when entity changes
  useEffect(() => {
    setAccountId("");
    setLoadingAccounts(true);
    apiFetch<PaymentAccount[]>(`/api/payouts/accounts?entity=${entity}`)
      .then(setAccounts)
      .catch(() => setAccounts([]))
      .finally(() => setLoadingAccounts(false));
  }, [entity]);

  function handleBeneficiaryAccountBlur() {
    if (!beneficiaryAccount) return;
    setBeneficiaryStatus("checking");
    apiFetch<BeneficiaryCheckResult>("/api/payouts/beneficiaries/check", {
      method: "POST",
      body: JSON.stringify({
        entity,
        beneficiary_account: beneficiaryAccount,
        beneficiary_bank:    beneficiaryBank,
      }),
    })
      .then(res => setBeneficiaryStatus(res.registered ? "registered" : "unregistered"))
      .catch(() => setBeneficiaryStatus("unregistered"));
  }

  function validate() {
    const errs: Record<string, string> = {};
    if (!entity)              errs.entity         = "Select an entity.";
    if (!requestType)         errs.requestType    = "Select a request type.";
    if (!accountId)           errs.accountId      = "Select a payment account.";
    const amt = parseFloat(amountNaira.replace(/,/g, ""));
    if (!amountNaira || isNaN(amt) || amt <= 0) errs.amount = "Enter a valid amount.";
    if (!beneficiaryName)     errs.beneficiaryName    = "Enter beneficiary name.";
    if (!beneficiaryBank)     errs.beneficiaryBank    = "Enter beneficiary bank.";
    if (!beneficiaryAccount)  errs.beneficiaryAccount = "Enter beneficiary account number.";
    if (!purpose.trim())      errs.purpose        = "Enter a purpose / narration.";
    return errs;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setErrors({});
    setError("");
    setSubmitting(true);

    try {
      const amountKobo = Math.round(parseFloat(amountNaira.replace(/,/g, "")) * 100);
      const req = await apiFetch<{ id: string }>("/api/payouts/", {
        method: "POST",
        body: JSON.stringify({
          entity,
          request_type:        requestType,
          payment_account_id:  accountId,
          amount_kobo:         amountKobo,
          beneficiary_name:    beneficiaryName,
          beneficiary_bank:    beneficiaryBank,
          beneficiary_account: beneficiaryAccount,
          purpose,
        }),
      });

      // immediately submit (out of draft)
      await apiFetch(`/api/payouts/${req.id}/submit`, { method: "POST" });

      // upload supporting document if one was selected (non-blocking — submit already succeeded)
      if (docFile) {
        setDocUploading(true);
        try {
          const fd = new FormData();
          fd.append("file", docFile);
          // Use raw fetch so the browser sets the correct multipart Content-Type with boundary
          const uploadRes = await fetch(`${BASE}/api/payouts/${req.id}/document`, {
            method: "POST",
            body: fd,
            headers: {
              Authorization: `Bearer ${getToken()}`,
              // No Content-Type — let the browser set it with the multipart boundary
            },
            cache: "no-store",
          });
          if (!uploadRes.ok) {
            const errBody = await uploadRes.json().catch(() => ({ detail: uploadRes.statusText }));
            throw new Error(errBody.detail ?? `Upload error ${uploadRes.status}`);
          }
          setDocStatus("success");
        } catch (uploadErr: unknown) {
          const msg = uploadErr instanceof Error ? uploadErr.message : "Document upload failed.";
          setDocStatus("error");
          setDocError(msg);
        } finally {
          setDocUploading(false);
        }
      }

      router.push(`/payouts/${req.id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to raise request.";
      setError(msg);
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <Topbar
        title="Raise Payment Request"
        subtitle="New payout / transfer instruction"
        actions={
          <Button variant="ghost" size="sm" className="gap-1.5 text-[12px]" onClick={() => router.back()}>
            <ArrowLeft className="w-3.5 h-3.5" />
            Back
          </Button>
        }
      />

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-2xl mx-auto">
          <form onSubmit={handleSubmit} className="space-y-6">

            {/* Naira-only transition reminder */}
            <div className="bg-amber-50 border border-amber-200 text-amber-800 text-[12px] px-4 py-3 rounded-lg flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-amber-500" />
              <span>
                <span className="font-semibold">Naira payments only.</span> All requests must also be recorded on the paper memo during the transition period.
              </span>
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 text-[13px] px-4 py-3 rounded-lg flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                {error}
              </div>
            )}

            {/* ── Entity + Type ────────────────────────────────────────── */}
            <div className="bg-card border border-border rounded-xl p-5 space-y-4">
              <h3 className="text-[13px] font-semibold text-foreground">Request Details</h3>

              <div className="grid grid-cols-2 gap-4">
                {/* Entity */}
                <div className="space-y-1.5">
                  <Label className="text-[12px]">Entity</Label>
                  <select
                    className={cn(
                      "w-full text-[13px] border rounded-md px-3 py-2 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring",
                      errors.entity ? "border-red-400" : "border-border",
                    )}
                    value={entity}
                    onChange={e => setEntity(e.target.value as "PAM" | "PCL")}
                  >
                    {ENTITY_OPTIONS.map(o => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                  <FieldError msg={errors.entity} />
                </div>

                {/* Request Type */}
                <div className="space-y-1.5">
                  <Label className="text-[12px]">Request Type</Label>
                  <select
                    className={cn(
                      "w-full text-[13px] border rounded-md px-3 py-2 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring",
                      errors.requestType ? "border-red-400" : "border-border",
                    )}
                    value={requestType}
                    onChange={e => setRequestType(e.target.value as RequestType)}
                  >
                    {REQUEST_TYPES.map(o => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                  <FieldError msg={errors.requestType} />
                </div>
              </div>

              {/* Payment Account */}
              <div className="space-y-1.5">
                <Label className="text-[12px]">Payment Account</Label>
                {loadingAccounts ? (
                  <Skeleton className="h-9 rounded-md" />
                ) : (
                  <select
                    className={cn(
                      "w-full text-[13px] border rounded-md px-3 py-2 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring",
                      errors.accountId ? "border-red-400" : "border-border",
                    )}
                    value={accountId}
                    onChange={e => setAccountId(e.target.value ? Number(e.target.value) : "")}
                  >
                    <option value="">Select account…</option>
                    {accounts.map(a => (
                      <option key={a.id} value={a.id}>
                        {a.account_name} – {a.bank_name} ({a.account_number})
                      </option>
                    ))}
                  </select>
                )}
                <FieldError msg={errors.accountId} />
              </div>

              {/* Amount */}
              <div className="space-y-1.5">
                <Label className="text-[12px]">Amount (₦ Naira)</Label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[13px] text-muted-foreground">₦</span>
                  <Input
                    className={cn("pl-7", errors.amount ? "border-red-400" : "")}
                    type="text"
                    inputMode="decimal"
                    placeholder="0.00"
                    value={amountNaira}
                    onChange={e => setAmountNaira(e.target.value)}
                  />
                </div>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Naira only — foreign currency payments are not supported at launch
                </p>
                <FieldError msg={errors.amount} />
              </div>
            </div>

            {/* ── Beneficiary ──────────────────────────────────────────── */}
            <div className="bg-card border border-border rounded-xl p-5 space-y-4">
              <h3 className="text-[13px] font-semibold text-foreground">Beneficiary</h3>

              <div className="space-y-1.5">
                <Label className="text-[12px]">Beneficiary Name</Label>
                <Input
                  className={errors.beneficiaryName ? "border-red-400" : ""}
                  placeholder="Full legal name"
                  value={beneficiaryName}
                  onChange={e => setBeneficiaryName(e.target.value)}
                />
                <FieldError msg={errors.beneficiaryName} />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-[12px]">Beneficiary Bank</Label>
                  <Input
                    className={errors.beneficiaryBank ? "border-red-400" : ""}
                    placeholder="e.g. Zenith Bank"
                    value={beneficiaryBank}
                    onChange={e => setBeneficiaryBank(e.target.value)}
                  />
                  <FieldError msg={errors.beneficiaryBank} />
                </div>

                <div className="space-y-1.5">
                  <Label className="text-[12px]">Account Number</Label>
                  <div className="relative">
                    <Input
                      className={cn(
                        errors.beneficiaryAccount ? "border-red-400" : "",
                        (beneficiaryStatus === "registered" || beneficiaryStatus === "unregistered") ? "pr-8" : "",
                      )}
                      placeholder="10 digits"
                      value={beneficiaryAccount}
                      onChange={e => { setBeneficiaryAccount(e.target.value); setBeneficiaryStatus("idle"); }}
                      onBlur={handleBeneficiaryAccountBlur}
                    />
                    {beneficiaryStatus === "checking" && (
                      <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground">…</span>
                    )}
                    {beneficiaryStatus === "registered" && (
                      <CheckCircle2 className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-emerald-500" />
                    )}
                    {beneficiaryStatus === "unregistered" && (
                      <AlertTriangle className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-amber-500" />
                    )}
                  </div>
                  {beneficiaryStatus === "registered" && (
                    <p className="text-[11px] text-emerald-600">Registered client beneficiary</p>
                  )}
                  {beneficiaryStatus === "unregistered" && (
                    <p className="text-[11px] text-amber-600">Not in beneficiary register — compliance step will be added</p>
                  )}
                  <FieldError msg={errors.beneficiaryAccount} />
                </div>
              </div>
            </div>

            {/* ── Purpose + Documents ──────────────────────────────────── */}
            <div className="bg-card border border-border rounded-xl p-5 space-y-4">
              <h3 className="text-[13px] font-semibold text-foreground">Purpose & Supporting Documents</h3>

              <div className="space-y-1.5">
                <Label className="text-[12px]">Purpose / Narration</Label>
                <Textarea
                  className={cn("resize-none min-h-[80px]", errors.purpose ? "border-red-400" : "")}
                  placeholder="Describe the reason for this payment…"
                  value={purpose}
                  onChange={e => setPurpose(e.target.value)}
                />
                <FieldError msg={errors.purpose} />
              </div>

              <div className="space-y-1.5">
                <Label className="text-[12px]">Supporting Document</Label>
                <label
                  htmlFor="doc-upload"
                  className={cn(
                    "border-2 border-dashed rounded-lg px-4 py-6 text-center text-[12px] flex flex-col items-center gap-2 cursor-pointer transition-colors",
                    docFile ? "border-primary/40 bg-primary/5" : "border-border hover:border-primary/40 hover:bg-muted/40",
                    "text-muted-foreground",
                  )}
                >
                  {docUploading ? (
                    <>
                      <Upload className="w-5 h-5 animate-pulse text-primary/60" />
                      <span className="text-primary/70">Uploading…</span>
                    </>
                  ) : docStatus === "success" ? (
                    <>
                      <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                      <span className="text-emerald-600">Document attached</span>
                    </>
                  ) : docFile ? (
                    <>
                      <Upload className="w-5 h-5 text-primary/60" />
                      <span className="text-foreground font-medium truncate max-w-xs">{docFile.name}</span>
                      <span className="text-[11px] text-muted-foreground">Click to change</span>
                    </>
                  ) : (
                    <>
                      <Upload className="w-5 h-5 text-muted-foreground/60" />
                      <span>Click to attach a supporting document</span>
                      <span className="text-[11px]">PDF, JPG, PNG, Excel, Word — max 10 MB</span>
                    </>
                  )}
                </label>
                <input
                  id="doc-upload"
                  type="file"
                  className="sr-only"
                  accept=".pdf,.jpg,.jpeg,.png,.xlsx,.xls,.docx"
                  onChange={e => {
                    const f = e.target.files?.[0] ?? null;
                    setDocFile(f);
                    setDocStatus("idle");
                    setDocError("");
                  }}
                />
                {docStatus === "error" && (
                  <p className="text-[11px] text-red-500 mt-0.5">{docError || "Document upload failed — request was still submitted."}</p>
                )}
              </div>
            </div>

            {/* ── Submit ───────────────────────────────────────────────── */}
            <div className="flex items-center justify-end gap-3">
              <Button type="button" variant="outline" onClick={() => router.back()} disabled={submitting}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting} className="min-w-[120px]">
                {submitting ? "Submitting…" : "Submit Request"}
              </Button>
            </div>

          </form>
        </div>
      </div>
    </div>
  );
}
