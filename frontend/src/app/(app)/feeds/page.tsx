"use client";

import { useState } from "react";
import { Topbar } from "@/components/layout/topbar";
import { useFetchStatement, useFetchLedger, useAccounts, useSchedulerJobs } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Download, RefreshCw, Clock, CheckCircle2,
  AlertTriangle, Loader2, Zap, Upload, CalendarClock,
} from "lucide-react";
import { cn } from "@/lib/utils";

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function FetchCard({
  title, description, icon: Icon, accentClass,
  onFetch, isPending, isSuccess, isError, errorMessage, successMessage,
  disabled, disabledReason,
}: {
  title: string;
  description: string;
  icon: React.ElementType;
  accentClass: string;
  onFetch: (start: string, end: string) => void;
  isPending: boolean;
  isSuccess: boolean;
  isError: boolean;
  errorMessage?: string;
  successMessage?: string;
  disabled?: boolean;
  disabledReason?: string;
}) {
  const [start, setStart] = useState(todayISO());
  const [end,   setEnd]   = useState(todayISO());

  return (
    <div className={cn("bg-card border rounded-xl overflow-hidden", accentClass)}>
      <div className="px-5 py-4 border-b border-border flex items-start gap-3">
        <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5",
          disabled ? "bg-muted" : "bg-foreground")}>
          <Icon className={cn("w-4 h-4", disabled ? "text-muted-foreground" : "text-background")} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[13px] font-semibold">{title}</p>
          <p className="text-[11px] text-muted-foreground mt-0.5">{description}</p>
        </div>
      </div>

      <div className="px-5 py-4 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label className="text-[11px]">From</Label>
            <Input type="date" value={start} onChange={e => setStart(e.target.value)}
              className="h-8 text-[12px]" disabled={disabled} />
          </div>
          <div className="space-y-1.5">
            <Label className="text-[11px]">To</Label>
            <Input type="date" value={end} onChange={e => setEnd(e.target.value)}
              className="h-8 text-[12px]" disabled={disabled} />
          </div>
        </div>

        {disabled && disabledReason && (
          <div className="flex items-start gap-2 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            {disabledReason}
          </div>
        )}

        {isSuccess && successMessage && (
          <div className="flex items-center gap-2 text-[11px] text-emerald-700 bg-emerald-50 rounded-lg px-3 py-2">
            <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
            {successMessage}
          </div>
        )}

        {isError && errorMessage && (
          <div className="flex items-start gap-2 text-[11px] text-red-700 bg-red-50 rounded-lg px-3 py-2">
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            {errorMessage}
          </div>
        )}

        <Button
          className="w-full h-9 text-[12px] gap-2"
          disabled={disabled || isPending}
          onClick={() => onFetch(start, end)}
        >
          {isPending
            ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />Fetching…</>
            : <><Download className="w-3.5 h-3.5" />Fetch now</>}
        </Button>
      </div>
    </div>
  );
}

export default function FeedsPage() {
  const { data: accountsData } = useAccounts();
  const { data: jobs = [] }    = useSchedulerJobs();
  const accounts: any[]        = accountsData?.accounts ?? [];

  const [selectedAccount, setSelectedAccount] = useState(accounts[0]?.id ?? "PAM-PRV-CLIENTS");
  const account = accounts.find((a: any) => a.id === selectedAccount) ?? {};

  const fetchStmt = useFetchStatement();
  const fetchGL   = useFetchLedger();

  const providusConfigured = !!process.env.NEXT_PUBLIC_PROVIDUS_READY; // false until API creds set
  const symplusConfigured  = false; // false until Neulogic provides API

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <Topbar
        title="Data Feeds"
        subtitle="Pull bank statements and GL data into the system"
      />

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto space-y-6">

          {/* How it works banner */}
          <div className="bg-card border border-border rounded-xl p-5">
            <h2 className="text-[13px] font-semibold mb-3">How the daily data flow works</h2>
            <div className="flex items-center gap-2 flex-wrap">
              {[
                { icon: RefreshCw,    label: "GL pulled from Symplus",      time: "8:30 PM", done: false },
                { icon: Download,     label: "Bank statement pulled",        time: "9:00 PM", done: false },
                { icon: Zap,          label: "Reconciliation runs",          time: "9:05 PM", done: false },
                { icon: CheckCircle2, label: "Finance reviews & approves",   time: "9:30 PM", done: true  },
                { icon: Upload,       label: "Journals posted to Symplus",   time: "9:45 PM", done: true  },
                { icon: CheckCircle2, label: "Checker signs off",            time: "Next AM", done: true  },
              ].map((step, i) => (
                <div key={i} className="flex items-center gap-1.5">
                  <div className={cn(
                    "flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium border",
                    step.done
                      ? "bg-blue-50 text-blue-700 border-blue-200"
                      : "bg-emerald-50 text-emerald-700 border-emerald-200"
                  )}>
                    <step.icon className="w-3 h-3" />
                    <span>{step.label}</span>
                    <span className="opacity-60 font-normal">· {step.time}</span>
                    {step.done && <span className="text-[9px] bg-blue-100 rounded px-1">Human</span>}
                  </div>
                  {i < 5 && <span className="text-muted-foreground text-[11px]">→</span>}
                </div>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground mt-3">
              <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 mr-1.5" />
              Green steps run automatically.
              <span className="inline-block w-2 h-2 rounded-full bg-blue-500 ml-3 mr-1.5" />
              Blue steps require a human (compliance requirement — cannot be automated).
            </p>
          </div>

          {/* Account selector */}
          <div>
            <Label className="text-[12px] mb-2 block">Account</Label>
            <div className="flex flex-wrap gap-2">
              {accounts.map((a: any) => (
                <button
                  key={a.id}
                  onClick={() => setSelectedAccount(a.id)}
                  className={cn(
                    "px-3 py-1.5 rounded-lg border text-[12px] font-mono transition-colors",
                    selectedAccount === a.id
                      ? "bg-foreground text-background border-foreground"
                      : "bg-card text-foreground border-border hover:border-muted-foreground/50"
                  )}
                >
                  {a.id}
                </button>
              ))}
            </div>
          </div>

          {/* Fetch cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <FetchCard
              title="Fetch Bank Statement"
              description="Pull the Providus account statement for the selected date range via the Providus Bank API or IMAP email."
              icon={Download}
              accentClass="border-border"
              onFetch={(start, end) => fetchStmt.mutate({ account_id: selectedAccount, period_start: start, period_end: end })}
              isPending={fetchStmt.isPending}
              isSuccess={fetchStmt.isSuccess}
              isError={fetchStmt.isError}
              successMessage={(fetchStmt.data as any)?.message}
              errorMessage={(fetchStmt.error as any)?.message}
              disabled={!selectedAccount}
              disabledReason={
                !selectedAccount ? "Select an account above first." : undefined
              }
            />

            <FetchCard
              title="Fetch GL from Symplus"
              description="Pull ledger entries for this account from Symplus (GL export). Currently uses the watch-folder mode — place the Symplus export in the configured directory."
              icon={RefreshCw}
              accentClass="border-border"
              onFetch={(start, end) => fetchGL.mutate({ account_id: selectedAccount, period_start: start, period_end: end })}
              isPending={fetchGL.isPending}
              isSuccess={fetchGL.isSuccess}
              isError={fetchGL.isError}
              successMessage={(fetchGL.data as any)?.message}
              errorMessage={(fetchGL.error as any)?.message}
              disabled={!selectedAccount}
            />
          </div>

          {/* Scheduler status */}
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="px-5 py-3.5 border-b border-border flex items-center gap-2">
              <CalendarClock className="w-4 h-4 text-muted-foreground" />
              <h2 className="text-[13px] font-semibold">Automatic Schedule</h2>
            </div>

            {(jobs as any[]).length === 0 ? (
              <div className="px-5 py-8 text-center space-y-2">
                <p className="text-[13px] font-medium">No scheduled jobs active</p>
                <p className="text-[12px] text-muted-foreground max-w-md mx-auto">
                  Daily auto-fetch runs at <strong>8:30 PM</strong> (GL) and <strong>9:00 PM</strong> (statement) once
                  enabled per account. Set <code className="font-mono bg-muted px-1 rounded text-[11px]">auto_fetch.enabled: true</code> in{" "}
                  <code className="font-mono bg-muted px-1 rounded text-[11px]">accounts.yaml</code> and restart the backend.
                </p>
                <div className="mt-3 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5 inline-block">
                  <AlertTriangle className="w-3.5 h-3.5 inline mr-1.5" />
                  Requires: Providus API credentials (PROVIDUS_CLIENT_ID / PROVIDUS_CLIENT_SECRET) and Symplus API access from Neulogic
                </div>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {(jobs as any[]).map((job: any) => (
                  <div key={job.id} className="px-5 py-3 flex items-center gap-4">
                    <div className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-[12px] font-medium truncate">{job.name}</p>
                      <p className="text-[11px] text-muted-foreground font-mono">{job.trigger}</p>
                    </div>
                    {job.next_run && (
                      <div className="text-right shrink-0">
                        <p className="text-[11px] text-muted-foreground">Next run</p>
                        <p className="text-[11px] font-medium tabular-nums">
                          {new Date(job.next_run).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" })}
                        </p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* API status */}
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="px-5 py-3.5 border-b border-border">
              <h2 className="text-[13px] font-semibold">Connection Status</h2>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Configure credentials in the backend <code className="font-mono bg-muted px-1 rounded">.env</code> file
              </p>
            </div>
            <div className="divide-y divide-border">
              {[
                {
                  name: "Providus Bank API",
                  desc: "Account Statement API — pulls daily statement automatically",
                  status: "Pending",
                  note: "Contact your Providus RM to enable API access on developer.providusbank.com",
                  ready: false,
                },
                {
                  name: "Symplus GL Export",
                  desc: "Watch-directory mode — active (Symplus admin exports file manually)",
                  status: "Active (Manual)",
                  note: "Symplus API posting endpoint pending — contact Neulogic",
                  ready: true,
                },
                {
                  name: "Symplus Posting API",
                  desc: "Auto-post approved journals directly to Symplus without CSV download",
                  status: "Pending",
                  note: "Neulogic to provide REST API endpoint and credentials",
                  ready: false,
                },
              ].map(c => (
                <div key={c.name} className="px-5 py-3.5 flex items-start gap-4">
                  <div className={cn(
                    "w-2 h-2 rounded-full mt-1.5 shrink-0",
                    c.ready ? "bg-emerald-500" : "bg-amber-400"
                  )} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-[12px] font-medium">{c.name}</p>
                      <span className={cn(
                        "text-[9px] rounded-full px-1.5 py-0.5 font-medium",
                        c.ready ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"
                      )}>{c.status}</span>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5">{c.desc}</p>
                    <p className="text-[10px] text-muted-foreground/70 mt-0.5 italic">{c.note}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
