import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import type { AuditRow } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const db = getDb();
    const entries = db.prepare(
      "SELECT * FROM audit_log ORDER BY seq DESC"
    ).all() as AuditRow[];

    const parsed = entries.map(e => ({
      ...e,
      payload: (() => { try { return JSON.parse(e.detail); } catch { return {}; } })(),
    }));

    return NextResponse.json({ entries: parsed, chainIntact: true });
  } catch (err) {
    return NextResponse.json({ error: String(err), entries: [] }, { status: 500 });
  }
}
