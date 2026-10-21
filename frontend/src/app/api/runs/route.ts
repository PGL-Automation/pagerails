import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import type { RunRow } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const db = getDb();
    const runs = db.prepare(
      "SELECT * FROM runs ORDER BY created_at DESC"
    ).all() as RunRow[];
    return NextResponse.json({ runs });
  } catch (err) {
    return NextResponse.json({ error: String(err), runs: [] }, { status: 500 });
  }
}
