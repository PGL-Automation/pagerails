/**
 * Singleton SQLite connection for Next.js API routes (server-side only).
 * Reads from the engine's recon.db produced by pcg_recon.
 */
import Database from "better-sqlite3";
import path from "path";
import fs from "fs";

let _db: Database.Database | null = null;

function dbPath(): string {
  const env = process.env.RECON_DB_PATH;
  if (env) {
    return path.isAbsolute(env) ? env : path.resolve(process.cwd(), env);
  }
  return path.resolve(process.cwd(), "../pcg_recon/recon.db");
}

export function getDb(): Database.Database {
  if (_db) return _db;
  const p = dbPath();
  if (!fs.existsSync(p)) {
    throw new Error(`recon.db not found at ${p}. Run a reconciliation first.`);
  }
  _db = new Database(p, { readonly: true, fileMustExist: true });
  return _db;
}

// ── Typed row shapes matching the engine's SQLite schema ──────────────────────

export interface RunRow {
  run_id: string;
  account_id: string;
  entity: string;
  period_start: string;
  period_end: string;
  created_at: string;
  maker: string;
  checker: string | null;
  signed_at: string | null;
  signoff_note: string | null;
  bank_open: number;
  bank_close: number;
  book_open: number;
  book_close: number;
  adj_bank: number;
  adj_book: number;
  difference: number;
  status: string;
  rules_hash: string;
  inputs_hash: string;
  report_path: string | null;
}

export interface OpenItemRow {
  uid: string;
  run_id: string;
  side: string;
  account_id: string;
  txn_date: string;
  amount: number;
  description: string;
  reference: string;
  source: string;
  source_row: number;
  currency: string;
  running_balance: number | null;
  doc_type: string;
  refs: string;
  category: string;
  origin_period: string;
}

export interface AuditRow {
  seq: number;
  ts: string;
  actor: string;
  action: string;
  detail: string;   // JSON string (engine calls it "detail")
  prev_hash: string;
  hash: string;
}

export interface DecisionRow {
  id: number;
  account_id: string;
  action: string;
  bank_uids: string;  // semicolon-separated
  book_uids: string;
  reviewer: string;
  note: string;
  created_at: string;
}
