import type { Run, Account, RunDetail, AuditEntry, DashboardStats, Match, Txn, Alert } from "./types";

export const ACCOUNTS: Account[] = [
  { id: "PAM-PRV-CLIENTS", entity: "PAM", bank: "Providus Bank", accountMasked: "****2286", currency: "NGN", glAccount: "GL0811101500", purpose: "client_money", clientMoney: true,  cadence: "daily"   },
  { id: "PAM-OPS-01",      entity: "PAM", bank: "Bank A",        accountMasked: "****1101", currency: "NGN", glAccount: "1010-01",      purpose: "operating",    clientMoney: false, cadence: "monthly" },
  { id: "PAM-CLIENT-01",   entity: "PAM", bank: "Bank B",        accountMasked: "****2202", currency: "NGN", glAccount: "1020-01",      purpose: "client_money", clientMoney: true,  cadence: "daily"   },
  { id: "PAM-MMF-CUST",    entity: "PAM", bank: "Custodian C",   accountMasked: "****3303", currency: "NGN", glAccount: "F1-1001",      purpose: "fund_custody", clientMoney: true,  cadence: "daily"   },
  { id: "PCL-OPS-01",      entity: "PCL", bank: "Bank D",        accountMasked: "****4404", currency: "NGN", glAccount: "1010-01",      purpose: "operating",    clientMoney: false, cadence: "monthly" },
  { id: "PCL-COLL-01",     entity: "PCL", bank: "Bank E",        accountMasked: "****5505", currency: "NGN", glAccount: "1030-01",      purpose: "collections",  clientMoney: false, cadence: "daily"   },
];

export const RUNS: Run[] = [
  // ── Real replay run: Providus client account, May–Sep 2026 (M09, 1 Oct 2026) ──
  {
    runId: "PAM-PRV-CLIENTS-20260930-100122", accountId: "PAM-PRV-CLIENTS", entity: "PAM",
    periodStart: "2026-05-01", periodEnd: "2026-09-30", createdAt: "2026-10-01T10:01:22Z",
    maker: "Claude (M09 replay)", checker: null, signedAt: null, signoffNote: null,
    bankOpen:  187461114758, bankClose: 1000248731274,
    bookOpen: -187460836358, bookClose: -1263580664844,
    adjBank: 0, adjBook: 0, difference:  35089221240,
    status: "UNRECONCILED",
    rulesHash: "a1b2c3d4e5f6", inputsHash: "c9f7e1d3b5a2",
    reportPath: "/packs/PAM-PRV-CLIENTS-202609.xlsx",
  },
  {
    runId: "PAM-OPS-01-20261031-143022",   accountId: "PAM-OPS-01",    entity: "PAM",
    periodStart: "2026-10-01", periodEnd: "2026-10-31", createdAt: "2026-10-31T14:30:22Z",
    maker: "A. Preparer", checker: "B. Reviewer", signedAt: "2026-10-31T16:45:00Z", signoffNote: null,
    bankOpen: 4825000000, bankClose: 5210340000, bookOpen: 4825000000, bookClose: 5210340000,
    adjBank: 0, adjBook: 0, difference: 0,
    status: "RECONCILED", rulesHash: "a1b2c3d4e5f6", inputsHash: "f6e5d4c3b2a1", reportPath: "/packs/PAM-OPS-01-202610.xlsx",
  },
  {
    runId: "PAM-CLIENT-01-20261031-143540", accountId: "PAM-CLIENT-01", entity: "PAM",
    periodStart: "2026-10-01", periodEnd: "2026-10-31", createdAt: "2026-10-31T14:35:40Z",
    maker: "A. Preparer", checker: null, signedAt: null, signoffNote: null,
    bankOpen: 0, bankClose: 125680000, bookOpen: 0, bookClose: 125680000,
    adjBank: 0, adjBook: 0, difference: 0,
    status: "RECONCILED", rulesHash: "a1b2c3d4e5f6", inputsHash: "f6e5d4c3b2a1", reportPath: null,
  },
  {
    runId: "PAM-MMF-CUST-20261031-144010",  accountId: "PAM-MMF-CUST",  entity: "PAM",
    periodStart: "2026-10-01", periodEnd: "2026-10-31", createdAt: "2026-10-31T14:40:10Z",
    maker: "A. Preparer", checker: null, signedAt: null, signoffNote: null,
    bankOpen: 185000000000, bankClose: 192450000000, bookOpen: 185000000000, bookClose: 192400000000,
    adjBank: 0, adjBook: 0, difference: 5000000,
    status: "UNRECONCILED", rulesHash: "a1b2c3d4e5f6", inputsHash: "f6e5d4c3b2a1", reportPath: null,
  },
  {
    runId: "PCL-OPS-01-20261031-144512",    accountId: "PCL-OPS-01",    entity: "PCL",
    periodStart: "2026-10-01", periodEnd: "2026-10-31", createdAt: "2026-10-31T14:45:12Z",
    maker: "A. Preparer", checker: "B. Reviewer", signedAt: "2026-10-31T17:00:00Z", signoffNote: null,
    bankOpen: 9670000000, bankClose: 10115000000, bookOpen: 9670000000, bookClose: 10115000000,
    adjBank: 0, adjBook: 0, difference: 0,
    status: "RECONCILED", rulesHash: "a1b2c3d4e5f6", inputsHash: "f6e5d4c3b2a1", reportPath: "/packs/PCL-OPS-01-202610.xlsx",
  },
  {
    runId: "PCL-COLL-01-20261031-145008",   accountId: "PCL-COLL-01",   entity: "PCL",
    periodStart: "2026-10-01", periodEnd: "2026-10-31", createdAt: "2026-10-31T14:50:08Z",
    maker: "A. Preparer", checker: null, signedAt: null, signoffNote: null,
    bankOpen: 0, bankClose: 87340000, bookOpen: 0, bookClose: 87340000,
    adjBank: 120000, adjBook: 120000, difference: 0,
    status: "RECONCILED-WITH-EXCEPTIONS", rulesHash: "a1b2c3d4e5f6", inputsHash: "f6e5d4c3b2a1", reportPath: null,
  },
  // Sep 2026
  {
    runId: "PAM-OPS-01-20260930-103000",   accountId: "PAM-OPS-01",    entity: "PAM",
    periodStart: "2026-09-01", periodEnd: "2026-09-30", createdAt: "2026-09-30T10:30:00Z",
    maker: "A. Preparer", checker: "B. Reviewer", signedAt: "2026-09-30T14:00:00Z", signoffNote: null,
    bankOpen: 4825000000, bankClose: 4825000000, bookOpen: 4825000000, bookClose: 4825000000,
    adjBank: 0, adjBook: 0, difference: 0,
    status: "RECONCILED", rulesHash: "a1b2c3d4e5f6", inputsHash: "f6e5d4c3b2a1", reportPath: "/packs/PAM-OPS-01-202609.xlsx",
  },
];

const BANK_TXNS: Txn[] = [
  { uid: "B-a1b2c3d4e5f6a7b8", side: "BANK", accountId: "PAM-MMF-CUST", txnDate: "2026-10-15", amount: 50000000, description: "INWARD TRANSFER - SUBSCRIPTION ABC FUND", reference: "NIP20261015001", source: "custodian_2026-10.csv", sourceRow: 14, currency: "NGN", runningBalance: null, docType: "NIP", category: "", originPeriod: "2026-10-31" },
  { uid: "B-b2c3d4e5f6a7b8c9", side: "BANK", accountId: "PAM-MMF-CUST", txnDate: "2026-10-18", amount: -20000000, description: "OUTWARD TRANSFER - REDEMPTION XYZ CLIENT", reference: "NIP20261018002", source: "custodian_2026-10.csv", sourceRow: 22, currency: "NGN", runningBalance: null, docType: "NIP", category: "", originPeriod: "2026-10-31" },
  { uid: "B-c3d4e5f6a7b8c9d0", side: "BANK", accountId: "PAM-MMF-CUST", txnDate: "2026-10-20", amount: -53750, description: "STAMP DUTY OCT 2026", reference: "EMTL-202610", source: "custodian_2026-10.csv", sourceRow: 35, currency: "NGN", runningBalance: null, docType: "", category: "EMTL_STAMP_DUTY", originPeriod: "2026-10-31" },
];

const BOOK_TXNS: Txn[] = [
  { uid: "K-d4e5f6a7b8c9d0e1", side: "BOOK", accountId: "PAM-MMF-CUST", txnDate: "2026-10-15", amount: 50000000, description: "Subscription receipt - ABC Fund Oct batch", reference: "JV/2026/10/001", source: "fund_gl_2026-10.csv", sourceRow: 8, currency: "NGN", runningBalance: null, docType: "JV", category: "", originPeriod: "2026-10-31" },
  { uid: "K-e5f6a7b8c9d0e1f2", side: "BOOK", accountId: "PAM-MMF-CUST", txnDate: "2026-10-18", amount: -20000000, description: "Redemption payment - XYZ Client", reference: "JV/2026/10/002", source: "fund_gl_2026-10.csv", sourceRow: 19, currency: "NGN", runningBalance: null, docType: "JV", category: "", originPeriod: "2026-10-31" },
];

export const PROPOSED_MATCHES: Match[] = [
  {
    matchId: "M00001", rule: "P4_FUZZY", confidence: 0.83,
    bankUids: ["B-c3d4e5f6a7b8c9d0"],
    bookUids: ["K-f6a7b8c9d0e1f2a3"],
    status: "PROPOSED", difference: 0,
    note: "sim 0.83, outside date window",
    bankTxns: [BANK_TXNS[2]],
    bookTxns: [{ uid: "K-f6a7b8c9d0e1f2a3", side: "BOOK", accountId: "PAM-MMF-CUST", txnDate: "2026-10-25", amount: -53750, description: "EMTL Stamp Duty — Oct journal", reference: "JV/2026/10/009", source: "fund_gl_2026-10.csv", sourceRow: 42, currency: "NGN", runningBalance: null, docType: "JV", category: "EMTL_STAMP_DUTY", originPeriod: "2026-10-31" }],
  },
  {
    matchId: "M00002", rule: "P2_AMT_DATE", confidence: 0.87,
    bankUids: ["B-a9b0c1d2e3f4a5b6"],
    bookUids: ["K-b0c1d2e3f4a5b6c7"],
    status: "PROPOSED", difference: 0,
    note: "Δ4d sim 0.62 (ambiguous candidates)",
    bankTxns: [{ uid: "B-a9b0c1d2e3f4a5b6", side: "BANK", accountId: "PAM-MMF-CUST", txnDate: "2026-10-22", amount: 75000000, description: "NAPS SETTLEMENT XFER REF 884421", reference: "884421", source: "custodian_2026-10.csv", sourceRow: 50, currency: "NGN", runningBalance: null, docType: "NIP", category: "", originPeriod: "2026-10-31" }],
    bookTxns: [{ uid: "K-b0c1d2e3f4a5b6c7", side: "BOOK", accountId: "PAM-MMF-CUST", txnDate: "2026-10-26", amount: 75000000, description: "Fund subscription - Quarterly inflow batch", reference: "JV/2026/10/015", source: "fund_gl_2026-10.csv", sourceRow: 57, currency: "NGN", runningBalance: null, docType: "JV", category: "", originPeriod: "2026-10-31" }],
  },
];

export const RUN_DETAIL: RunDetail = {
  ...RUNS[2],
  matches: [
    { matchId: "M00010", rule: "P1_REF", confidence: 1.0, bankUids: ["B-a1b2c3d4e5f6a7b8"], bookUids: ["K-d4e5f6a7b8c9d0e1"], status: "AUTO", difference: 0, note: "ref NIP20261015001", bankTxns: [BANK_TXNS[0]], bookTxns: [BOOK_TXNS[0]] },
    { matchId: "M00011", rule: "P1_REF", confidence: 1.0, bankUids: ["B-b2c3d4e5f6a7b8c9"], bookUids: ["K-e5f6a7b8c9d0e1f2"], status: "AUTO", difference: 0, note: "ref NIP20261018002", bankTxns: [BANK_TXNS[1]], bookTxns: [BOOK_TXNS[1]] },
    ...PROPOSED_MATCHES,
  ],
  openBank: [
    { uid: "B-open1", side: "BANK", accountId: "PAM-MMF-CUST", txnDate: "2026-10-28", amount: 5000000, description: "COLLECTION INWARD UNIDENTIFIED", reference: "", source: "custodian_2026-10.csv", sourceRow: 80, currency: "NGN", runningBalance: null, docType: "", category: "UNIDENTIFIED_RECEIPT", originPeriod: "2026-10-31" },
  ],
  openBook: [],
  alerts: [
    { accountId: "PAM-MMF-CUST", severity: "HIGH", code: "UNIDENTIFIED_CREDIT", message: "Unidentified credit of ₦50,000.00 on 2026-10-28 — routed to AML review", uid: "B-open1" },
    { accountId: "PAM-MMF-CUST", severity: "MEDIUM", code: "PRIOR_NOT_SIGNED", message: "Prior run PAM-MMF-CUST-20260930 not signed off — carried items are unreviewed", uid: "" },
  ],
  journals: [
    {
      category: "EMTL_STAMP_DUTY", gl: "6105-EMTL", total: -53750,
      description: "Draft journal — EMTL stamp duty Oct 2026",
      lines: [
        { date: "2026-10-31", description: "EMTL stamp duty Oct 2026", dr: 53750, cr: 0, gl: "6105-EMTL" },
        { date: "2026-10-31", description: "EMTL stamp duty Oct 2026", dr: 0, cr: 53750, gl: "F1-1001" },
      ],
    },
  ],
  stats: {
    totalBank: 12, totalBook: 11, autoMatchRate: 0.82, autoMatched: 10, proposed: 2,
    openBankCount: 1, openBookCount: 0, carriedInBank: 0, carriedInBook: 0,
  },
};

export const AUDIT_LOG: AuditEntry[] = [
  { seq: 1, ts: "2026-10-31T14:30:22Z", actor: "A. Preparer",  action: "RUN",     payload: { run_id: "PAM-OPS-01-20261031-143022",  status: "RECONCILED",    difference: 0 },         hash: "8f14e45f", prevHash: "00000000" },
  { seq: 2, ts: "2026-10-31T14:35:40Z", actor: "A. Preparer",  action: "RUN",     payload: { run_id: "PAM-CLIENT-01-20261031-143540", status: "RECONCILED",    difference: 0 },         hash: "c9f0d89e", prevHash: "8f14e45f" },
  { seq: 3, ts: "2026-10-31T14:40:10Z", actor: "A. Preparer",  action: "RUN",     payload: { run_id: "PAM-MMF-CUST-20261031-144010",  status: "UNRECONCILED",  difference: 5000000 },   hash: "1679091c", prevHash: "c9f0d89e" },
  { seq: 4, ts: "2026-10-31T16:45:00Z", actor: "B. Reviewer",  action: "SIGNOFF", payload: { run_id: "PAM-OPS-01-20261031-143022",  checker: "B. Reviewer" },                          hash: "45c48cce", prevHash: "1679091c" },
  { seq: 5, ts: "2026-10-31T14:45:12Z", actor: "A. Preparer",  action: "RUN",     payload: { run_id: "PCL-OPS-01-20261031-144512",    status: "RECONCILED",    difference: 0 },         hash: "d3d94468", prevHash: "45c48cce" },
  { seq: 6, ts: "2026-10-31T17:00:00Z", actor: "B. Reviewer",  action: "SIGNOFF", payload: { run_id: "PCL-OPS-01-20261031-144512",    checker: "B. Reviewer" },                        hash: "6512bd43", prevHash: "d3d94468" },
  { seq: 7, ts: "2026-10-31T14:50:08Z", actor: "A. Preparer",  action: "RUN",     payload: { run_id: "PCL-COLL-01-20261031-145008",   status: "RECONCILED-WITH-EXCEPTIONS" },          hash: "c20ad4d7", prevHash: "6512bd43" },
];

export const DASHBOARD_STATS: DashboardStats = {
  totalAccounts: 6,
  reconciledCount: 3,
  unreconciledCount: 2,   // PAM-PRV-CLIENTS (first replay) + PAM-MMF-CUST
  pendingSignoff: 2,
  highAlerts: 2,
  openItemsCount: 1228,   // 1225 from Providus replay + 3 from other accounts
  proposedMatchesCount: 2,
};
