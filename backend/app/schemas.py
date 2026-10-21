"""Pydantic response + request models."""
from pydantic import BaseModel, Field
from typing import Any


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    name: str
    role: str
    permissions: list[str] = []


class RunSummary(BaseModel):
    run_id: str
    account_id: str
    entity: str
    period_start: str
    period_end: str
    created_at: str
    maker: str
    checker: str | None
    signed_at: str | None
    bank_open: int
    bank_close: int
    book_open: int
    book_close: int
    adj_bank: int
    adj_book: int
    difference: int
    status: str
    rules_hash: str
    inputs_hash: str
    report_path: str | None


class OpenItem(BaseModel):
    uid: str
    side: str
    account_id: str
    txn_date: str
    amount: int
    description: str
    reference: str
    source: str
    source_row: int
    currency: str
    running_balance: int | None
    doc_type: str
    refs: str
    category: str
    origin_period: str


class Match(BaseModel):
    match_id: str
    run_id: str
    rule: str
    confidence: float
    bank_uids: list[str]
    book_uids: list[str]
    status: str
    difference: int
    note: str


class RunDetail(RunSummary):
    open_bank: list[OpenItem]
    open_book: list[OpenItem]
    matches: list[Match]
    stats: dict[str, Any]


class TriggerRunRequest(BaseModel):
    account_ids: list[str] = Field(..., description="Account IDs to reconcile")
    period: str = Field(..., description="Period: 2026-09 | 2026-09-29 | 2026-09-01:2026-09-30")
    maker: str = Field(..., description="Name of the preparer")


class TriggerRunResponse(BaseModel):
    job_id: str
    status: str
    message: str


class DecisionItem(BaseModel):
    account_id: str
    action: str        # APPROVE | REJECT | MANUAL
    bank_uids: list[str]
    book_uids: list[str]
    note: str = ""


class DecisionsRequest(BaseModel):
    reviewer: str
    decisions: list[DecisionItem]


class SignoffRequest(BaseModel):
    checker: str
    note: str = ""


class AuditEntry(BaseModel):
    seq: int
    ts: str
    actor: str
    action: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str


class UploadedFile(BaseModel):
    id: int
    account_id: str
    period: str
    filename: str
    size: int
    file_hash: str
    uploaded_by: str
    uploaded_at: str


class DashboardStats(BaseModel):
    total_accounts: int
    reconciled_count: int
    unreconciled_count: int
    pending_signoff: int
    open_items_count: int
    high_alerts: int
    runs: list[RunSummary]
