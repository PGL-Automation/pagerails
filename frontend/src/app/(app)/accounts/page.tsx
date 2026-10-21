import type { Metadata } from "next";
import { Topbar } from "@/components/layout/topbar";
import { PurposeBadge, RunStatusBadge } from "@/components/domain/status-badge";
import { fmtAmount, fmtPeriod } from "@/lib/format";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Accounts" };
export const dynamic = "force-dynamic";

const PURPOSE_DESC: Record<string, string> = {
  operating:    "Day-to-day operational transactions",
  client_money: "Client funds — SEC/CBN regulated, zero tolerance",
  fund_custody: "Fund custodian cash — daily reconciliation",
  collections:  "Loan repayment inflow account",
  disbursement: "Outgoing disbursements",
};

async function fetchData() {
  try {
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    // Use basic internal token fetch — accounts and stats are read via the stats route
    const localBase = process.env.NEXT_INTERNAL_BASE ?? "http://localhost:3000";
    const [accRes, statsRes] = await Promise.all([
      fetch(`${base}/api/accounts/`, { headers: { Authorization: "Bearer internal" }, cache: "no-store" }).catch(() => null),
      fetch(`${localBase}/api/stats`, { cache: "no-store" }).catch(() => null),
    ]);

    const accData  = accRes?.ok  ? await accRes.json()  : null;
    const statsData = statsRes?.ok ? await statsRes.json() : null;

    return { accounts: accData?.accounts ?? [], entities: accData?.entities ?? {}, latestRuns: statsData?.runs ?? [] };
  } catch {
    return { accounts: [], entities: {}, latestRuns: [] };
  }
}

export default async function AccountsPage() {
  const { accounts, entities, latestRuns } = await fetchData();

  const runByAccount: Record<string, any> = {};
  for (const r of latestRuns) runByAccount[r.account_id] = r;

  const entityIds = ["PAM", "PCL"];

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <Topbar title="Accounts" subtitle={`${accounts.length} accounts · read-only from accounts.yaml`} />

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-5xl mx-auto space-y-8">
          {entityIds.map(eid => {
            const meta = entities[eid] ?? {};
            const entityAccounts = accounts.filter((a: any) => a.entity === eid);
            if (!entityAccounts.length) return null;

            return (
              <section key={eid}>
                <div className="flex items-start gap-4 mb-4">
                  <div className={cn(
                    "w-8 h-8 rounded-lg flex items-center justify-center text-[11px] font-bold text-white shrink-0",
                    eid === "PAM" ? "bg-blue-600" : "bg-purple-600"
                  )}>
                    {eid}
                  </div>
                  <div>
                    <h2 className="text-[14px] font-semibold">{meta.name ?? eid}</h2>
                    <p className="text-[11px] text-muted-foreground">{meta.regulator}</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-3">
                  {entityAccounts.map((acc: any) => {
                    const run = runByAccount[acc.id];
                    const purpose = acc.purpose ?? "operating";
                    return (
                      <div key={acc.id} className="bg-card border border-border rounded-xl p-5">
                        <div className="flex items-start gap-4">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <h3 className="text-[14px] font-semibold font-mono">{acc.id}</h3>
                              <PurposeBadge purpose={purpose} clientMoney={!!acc.client_money} />
                              {acc.client_money && (
                                <span className="text-[10px] bg-red-50 text-red-700 ring-1 ring-red-200/60 rounded-full px-2 py-0.5 font-medium">
                                  Client Money
                                </span>
                              )}
                              <span className={cn(
                                "text-[10px] px-1.5 py-0.5 rounded-full font-medium",
                                acc.cadence === "daily" ? "bg-blue-50 text-blue-700" : "bg-gray-50 text-gray-600"
                              )}>
                                {acc.cadence}
                              </span>
                            </div>
                            <p className="text-[12px] text-muted-foreground mt-1">
                              {acc.bank} · {acc.account_masked} · GL {acc.gl_account}
                            </p>
                            <p className="text-[11px] text-muted-foreground mt-0.5">
                              {PURPOSE_DESC[purpose] ?? purpose}
                            </p>
                          </div>

                          {run ? (
                            <div className="text-right shrink-0 space-y-1">
                              <RunStatusBadge status={run.status} />
                              <p className="text-[12px] font-medium tabular-nums">
                                {fmtAmount(run.bank_close, { compact: true })}
                              </p>
                              <p className="text-[10px] text-muted-foreground">
                                {run.period_end}
                              </p>
                            </div>
                          ) : (
                            <span className="text-[11px] text-muted-foreground italic shrink-0">No runs yet</span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}
