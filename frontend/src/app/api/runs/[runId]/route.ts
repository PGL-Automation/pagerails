import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import type { RunRow, OpenItemRow } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET(_: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await params;
    const db = getDb();

    const run = db.prepare("SELECT * FROM runs WHERE run_id = ?").get(runId) as RunRow | undefined;
    if (!run) {
      return NextResponse.json({ error: "Run not found" }, { status: 404 });
    }

    // open_items stores each transaction as a JSON payload blob — txn_date is inside, not a column
    const rawItems = db.prepare(
      "SELECT run_id, account_id, uid, side, payload FROM open_items WHERE run_id = ? ORDER BY side"
    ).all(runId) as { run_id: string; account_id: string; uid: string; side: string; payload: string }[];

    const openItems: OpenItemRow[] = rawItems.map(r => {
      const p = JSON.parse(r.payload);
      return {
        uid: r.uid, run_id: r.run_id, side: r.side, account_id: r.account_id,
        txn_date:        p.txn_date       ?? "",
        amount:          p.amount         ?? 0,
        description:     p.description    ?? "",
        reference:       p.reference      ?? "",
        source:          p.source         ?? "",
        source_row:      p.source_row     ?? 0,
        currency:        p.currency       ?? "NGN",
        running_balance: p.running_balance ?? null,
        doc_type:        p.doc_type       ?? "",
        refs:            Array.isArray(p.refs) ? p.refs.join(" ") : (p.refs ?? ""),
        category:        p.category       ?? "",
        origin_period:   p.origin_period  ?? "",
      };
    });

    const openBank = openItems.filter(t => t.side === "BANK");
    const openBook = openItems.filter(t => t.side === "BOOK");

    const stats = {
      openBankCount: openBank.length,
      openBookCount: openBook.length,
      bankLines: openBank.length,
      bookLines: openBook.length,
    };

    return NextResponse.json({ run, openBank, openBook, stats });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
