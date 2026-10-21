export type RunStatus =
  | "RECONCILED"
  | "RECONCILED-WITH-EXCEPTIONS"
  | "UNRECONCILED"
  | "RUNNING"
  | "QUEUED"
  | "FAILED";

export type MatchStatus = "AUTO" | "PROPOSED" | "APPROVED" | "REJECTED";
export type AlertSeverity = "HIGH" | "MEDIUM" | "LOW";
export type UserRole = "maker" | "checker" | "viewer";

export interface Account {
  id: string;
  entity: string;
  bank: string;
  accountMasked: string;
  currency: string;
  glAccount: string;
  purpose: "operating" | "client_money" | "fund_custody" | "collections" | "disbursement";
  clientMoney: boolean;
  cadence: "monthly" | "daily";
}

export interface Run {
  runId: string;
  accountId: string;
  entity: string;
  periodStart: string;
  periodEnd: string;
  createdAt: string;
  maker: string;
  checker: string | null;
  signedAt: string | null;
  signoffNote: string | null;
  bankOpen: number;
  bankClose: number;
  bookOpen: number;
  bookClose: number;
  adjBank: number;
  adjBook: number;
  difference: number;
  status: RunStatus;
  rulesHash: string;
  inputsHash: string;
  reportPath: string | null;
}

export interface Txn {
  uid: string;
  side: "BANK" | "BOOK";
  accountId: string;
  txnDate: string;
  amount: number;
  description: string;
  reference: string;
  source: string;
  sourceRow: number;
  currency: string;
  runningBalance: number | null;
  docType: string;
  category: string;
  originPeriod: string;
}

export interface Match {
  matchId: string;
  rule: string;
  confidence: number;
  bankUids: string[];
  bookUids: string[];
  status: MatchStatus;
  difference: number;
  note: string;
  bankTxns?: Txn[];
  bookTxns?: Txn[];
}

export interface Alert {
  accountId: string;
  severity: AlertSeverity;
  code: string;
  message: string;
  uid: string;
}

export interface RunDetail extends Run {
  matches: Match[];
  openBank: Txn[];
  openBook: Txn[];
  alerts: Alert[];
  journals: Journal[];
  stats: RunStats;
}

export interface RunStats {
  totalBank: number;
  totalBook: number;
  autoMatchRate: number;
  autoMatched: number;
  proposed: number;
  openBankCount: number;
  openBookCount: number;
  carriedInBank: number;
  carriedInBook: number;
}

export interface Journal {
  category: string;
  gl: string;
  lines: JournalLine[];
  total: number;
  description: string;
}

export interface JournalLine {
  date: string;
  description: string;
  dr: number;
  cr: number;
  gl: string;
}

export interface Decision {
  matchId: string;
  accountId: string;
  action: "APPROVE" | "REJECT";
  bankUids: string[];
  bookUids: string[];
  reviewer: string;
  note?: string;
}

export interface AuditEntry {
  seq: number;
  ts: string;
  actor: string;
  action: string;
  payload: Record<string, unknown>;
  hash: string;
  prevHash: string;
}

export interface UploadFile {
  id: string;
  accountId: string;
  period: string;
  filename: string;
  uploadedBy: string;
  uploadedAt: string;
  fileHash: string;
  size: number;
}

export interface DashboardStats {
  totalAccounts: number;
  reconciledCount: number;
  unreconciledCount: number;
  pendingSignoff: number;
  highAlerts: number;
  openItemsCount: number;
  proposedMatchesCount: number;
}

// ── Payout Approval ───────────────────────────────────────────────────────────

export type RequestType = "client_payout" | "liquidation" | "transfer" | "expense" | "placement";

export type RequestStatus =
  | "draft"
  | "submitted"
  | "head_concur"
  | "internal_control"
  | "compliance"
  | "finance"
  | "pending_signatories"
  | "approved"
  | "sent_to_bank"
  | "confirmed"
  | "reconciled"
  | "returned"
  | "rejected";

export type StepStatus = "pending" | "approved" | "returned" | "rejected" | "skipped";

export interface PaymentAccount {
  id: number;
  entity: string;
  bank_name: string;
  account_name: string;
  account_number: string;
  cut_off_time: string;
}

export interface PaymentRequest {
  id: string;
  instruction_id: string;
  entity: string;
  request_type: RequestType;
  payment_account_id: number;
  amount_kobo: number;
  beneficiary_name: string;
  beneficiary_bank: string;
  beneficiary_account: string;
  purpose: string;
  status: RequestStatus;
  compliance_flagged: boolean;
  raised_by: string;
  submitted_at?: string;
  approved_at?: string;
  bank_reference: string;
  created_at: string;
  updated_at: string;
}

export interface ApprovalStep {
  id: string;
  request_id: string;
  step_order: number;
  step_type: string;
  assigned_to: string;
  stand_in_for?: string;
  status: StepStatus;
  due_by: string;
  decided_at?: string;
  notes: string;
}

export interface PayoutAction {
  id: string;
  actor_email: string;
  action: string;
  notes: string;
  source: string;
  created_at: string;
}

export interface PayoutDetail {
  request: PaymentRequest;
  steps: ApprovalStep[];
  log: PayoutAction[];
}
