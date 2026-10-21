"use client";
/**
 * Central TanStack Query hooks — all data fetching goes through here.
 * Every component that needs server data uses these hooks instead of
 * direct fetch() calls, giving us: caching, background refresh,
 * optimistic updates, and no page reloads.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "./api";

// ── Keys ──────────────────────────────────────────────────────────────────────

export const QK = {
  runs:      () => ["runs"]          as const,
  stats:     () => ["stats"]         as const,
  run:       (id: string) => ["run", id] as const,
  proposed:  (id: string) => ["proposed", id] as const,
  audit:     () => ["audit"]         as const,
  accounts:  () => ["accounts"]      as const,
  users:     () => ["users"]         as const,
  connectors:(id: string) => ["connectors", id] as const,
};

// ── Queries ────────────────────────────────────────────────────────────────────

export function useStats() {
  return useQuery({
    queryKey: QK.stats(),
    queryFn:  () => api.getStats(),
  });
}

export function useRuns() {
  return useQuery({
    queryKey: QK.runs(),
    queryFn:  () => api.getRuns(),
  });
}

export function useRun(runId: string) {
  return useQuery({
    queryKey: QK.run(runId),
    queryFn:  () => api.getRun(runId),
    enabled:  !!runId,
  });
}

export function useProposedMatches(runId: string) {
  return useQuery({
    queryKey: QK.proposed(runId),
    queryFn:  () => api.getProposedMatches(runId),
    enabled:  !!runId,
    staleTime: 60_000,
  });
}

export function useLatestRunId() {
  const { data: runs } = useRuns();
  return Array.isArray(runs) ? (runs[0]?.run_id ?? "") : "";
}

export function useAudit() {
  return useQuery({
    queryKey: QK.audit(),
    queryFn:  () => api.getAudit(),
  });
}

export function useAccounts() {
  return useQuery({
    queryKey: QK.accounts(),
    queryFn:  () => api.getAccounts(),
  });
}

export function useUsers() {
  return useQuery({
    queryKey: QK.users(),
    queryFn:  () => api.getUsers(),
  });
}

export function useConnectorStatus(accountId: string) {
  return useQuery({
    queryKey: QK.connectors(accountId),
    queryFn:  async () => {
      const [stmt, ledger, posting] = await Promise.all([
        api.apiFetchRaw(`/api/connectors/statement/status/${accountId}`),
        api.apiFetchRaw(`/api/connectors/ledger/status/${accountId}`),
        api.apiFetchRaw(`/api/connectors/posting/status/${accountId}`),
      ]);
      return { statement: stmt, ledger, posting };
    },
    enabled: !!accountId,
    staleTime: 120_000,
  });
}

// ── Mutations ─────────────────────────────────────────────────────────────────

export function useTriggerRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.triggerRun,
    onSuccess: () => {
      // Invalidate so the runs list refreshes in the background
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: QK.runs() });
        qc.invalidateQueries({ queryKey: QK.stats() });
      }, 3_000);  // give the background task a moment to write the DB
    },
  });
}

export function useSignOff(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { checker: string; note?: string }) => api.signOff(runId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.run(runId) });
      qc.invalidateQueries({ queryKey: QK.runs() });
      qc.invalidateQueries({ queryKey: QK.stats() });
    },
  });
}

export function useSubmitDecisions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.submitDecisions,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.runs() });
    },
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.createUser,
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.users() }),
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: any }) => api.updateUser(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.users() }),
  });
}

export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteUser(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.users() }),
  });
}

export function useFetchStatement() {
  return useMutation({ mutationFn: api.fetchStatement });
}

export function useFetchLedger() {
  return useMutation({ mutationFn: api.fetchLedger });
}

export function useRunJournals(runId: string) {
  return useQuery({
    queryKey: ["journals", runId],
    queryFn:  () => api.getRunJournals(runId),
    enabled:  !!runId,
  });
}

export function useApproveJournal(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.approveJournal(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["journals", runId] }),
  });
}

export function usePostingQueue(runId?: string) {
  return useQuery({
    queryKey: ["posting_queue", runId],
    queryFn:  () => api.getPostingQueue(runId),
  });
}

export function usePopulateQueue(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.populatePostingQueue(runId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["posting_queue", runId] }),
  });
}

export function useExecutePosting(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.executePosting(runId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["posting_queue", runId] });
      qc.invalidateQueries({ queryKey: QK.run(runId) });
    },
  });
}

export function useSchedulerJobs() {
  return useQuery({
    queryKey: ["scheduler_jobs"],
    queryFn:  api.getSchedulerJobs,
    staleTime: 60_000,
  });
}
