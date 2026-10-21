import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import type { RunRow } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const db = getDb();
    const runs = db.prepare("SELECT * FROM runs ORDER BY created_at DESC").all() as RunRow[];

    const latest = new Map<string, RunRow>();
    for (const r of runs) {
      if (!latest.has(r.account_id)) latest.set(r.account_id, r);
    }

    const currentRuns = [...latest.values()];
    const reconciled   = currentRuns.filter(r => r.status === "RECONCILED").length;
    const unreconciled = currentRuns.filter(r => r.status === "UNRECONCILED").length;
    const pendingSignoff = currentRuns.filter(r => !r.signed_at && r.status === "RECONCILED").length;

    const openCounts = db.prepare(
      "SELECT run_id, COUNT(*) as cnt FROM open_items GROUP BY run_id"
    ).all() as { run_id: string; cnt: number }[];

    const openMap = new Map(openCounts.map(r => [r.run_id, r.cnt]));
    const totalOpen = currentRuns.reduce((s, r) => s + (openMap.get(r.run_id) ?? 0), 0);

    return NextResponse.json({
      totalAccounts: latest.size,
      reconciledCount: reconciled,
      unreconciledCount: unreconciled,
      pendingSignoff,
      highAlerts: unreconciled,
      openItemsCount: totalOpen,
      proposedMatchesCount: 0,
      runs: currentRuns,
    });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
