"use client";

import { useState } from "react";
import { Topbar } from "@/components/layout/topbar";
import { useUsers, useCreateUser, useUpdateUser, useDeleteUser } from "@/lib/hooks";
import { getAllPermissions } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Plus, Pencil, Trash2, ShieldCheck, X } from "lucide-react";
import { cn } from "@/lib/utils";

const PERMISSION_LABELS: Record<string, string> = {
  trigger_run:       "Trigger reconciliation run",
  upload_files:      "Upload files",
  fetch_statement:   "Fetch bank statement (auto)",
  fetch_ledger:      "Fetch GL from ledger (auto)",
  approve_match:     "Approve/reject proposed matches",
  signoff_run:       "Sign off a completed run",
  approve_posting:   "Approve draft journals for posting",
  post_to_ledger:    "Post journals to ledger",
  view_audit:        "View audit log",
  view_reports:      "View reports",
  manage_accounts:   "Manage accounts config",
  manage_users:      "Manage users (admin)",
  manage_connectors: "Configure connectors",
};

const PERMISSION_GROUPS = [
  { label: "Reconciliation", perms: ["trigger_run", "upload_files", "fetch_statement", "fetch_ledger"] },
  { label: "Review",         perms: ["approve_match", "signoff_run"] },
  { label: "Posting",        perms: ["approve_posting", "post_to_ledger"] },
  { label: "Reporting",      perms: ["view_audit", "view_reports"] },
  { label: "Administration", perms: ["manage_accounts", "manage_users", "manage_connectors"] },
];

export default function SettingsPage() {
  const { data: users = [], isLoading } = useUsers();
  const { data: allPermsData } = useQuery({
    queryKey: ["allPerms"],
    queryFn: getAllPermissions,
  });
  const allPerms = allPermsData?.permissions ?? Object.keys(PERMISSION_LABELS);

  const createUser = useCreateUser();
  const updateUser = useUpdateUser();
  const deleteUser = useDeleteUser();

  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing]       = useState<any | null>(null);
  const [form, setForm]             = useState({
    name: "", email: "", password: "", is_admin: false, permissions: [] as string[],
  });

  function resetForm() {
    setForm({ name: "", email: "", password: "", is_admin: false, permissions: [] });
  }

  function openCreate() { resetForm(); setShowCreate(true); }
  function openEdit(user: any) {
    setForm({
      name: user.name, email: user.email, password: "",
      is_admin: user.is_admin, permissions: [...user.permissions],
    });
    setEditing(user);
  }

  function togglePerm(p: string) {
    setForm(f => ({
      ...f,
      permissions: f.permissions.includes(p)
        ? f.permissions.filter(x => x !== p)
        : [...f.permissions, p],
    }));
  }

  async function handleCreate() {
    await createUser.mutateAsync({
      name: form.name, email: form.email, password: form.password,
      is_admin: form.is_admin, permissions: form.is_admin ? allPerms : form.permissions,
    });
    setShowCreate(false);
    resetForm();
  }

  async function handleUpdate() {
    if (!editing) return;
    await updateUser.mutateAsync({
      id: editing.id,
      body: {
        name: form.name,
        permissions: form.is_admin ? allPerms : form.permissions,
        ...(form.password ? { password: form.password } : {}),
      },
    });
    setEditing(null);
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <Topbar title="Settings" subtitle="Users, roles, and permissions" />

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto space-y-8">

          {/* Users section */}
          <section>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-[14px] font-semibold">Team members</h2>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Permissions control what each person can do in the system
                </p>
              </div>
              <Button size="sm" className="h-8 text-[12px] gap-1.5" onClick={openCreate}>
                <Plus className="w-3.5 h-3.5" /> Add user
              </Button>
            </div>

            <div className="bg-card border border-border rounded-xl divide-y divide-border overflow-hidden">
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="px-5 py-4">
                    <Skeleton className="h-4 w-48 mb-2" />
                    <Skeleton className="h-3 w-64" />
                  </div>
                ))
              ) : users.map((user: any) => (
                <div key={user.id} className="flex items-start gap-4 px-5 py-4">
                  <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center text-[11px] font-semibold shrink-0">
                    {user.name.split(" ").map((w: string) => w[0]).join("").slice(0, 2).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-[13px] font-medium">{user.name}</p>
                      {user.is_admin && (
                        <span className="text-[10px] bg-violet-50 text-violet-700 ring-1 ring-violet-200/60 rounded-full px-2 py-0.5 font-medium">
                          admin
                        </span>
                      )}
                      {!user.is_active && (
                        <span className="text-[10px] bg-red-50 text-red-600 ring-1 ring-red-200/60 rounded-full px-2 py-0.5">
                          inactive
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-muted-foreground">{user.email}</p>
                    {!user.is_admin && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {user.permissions.slice(0, 5).map((p: string) => (
                          <span key={p} className="text-[9px] bg-muted text-muted-foreground rounded px-1.5 py-0.5 font-mono">
                            {p}
                          </span>
                        ))}
                        {user.permissions.length > 5 && (
                          <span className="text-[9px] text-muted-foreground">+{user.permissions.length - 5} more</span>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="icon" className="w-7 h-7 text-muted-foreground hover:text-foreground"
                      onClick={() => openEdit(user)}>
                      <Pencil className="w-3.5 h-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon" className="w-7 h-7 text-muted-foreground hover:text-red-600"
                      onClick={() => deleteUser.mutate(user.id)}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <Separator />

          {/* System info */}
          <section>
            <h2 className="text-[14px] font-semibold mb-4">System</h2>
            <div className="bg-card border border-border rounded-xl divide-y divide-border overflow-hidden">
              {[
                { label: "Engine version",        value: "v0.1.0",       sub: "pagerails engine" },
                { label: "Auto-accept threshold", value: "90%",           sub: "Confidence ≥ 0.90 → AUTO" },
                { label: "Run store",             value: "SQLite → PostgreSQL", sub: "Swap via RECON_DB_PATH" },
              ].map(row => (
                <div key={row.label} className="flex items-center justify-between px-5 py-3.5">
                  <div>
                    <p className="text-[13px] font-medium">{row.label}</p>
                    <p className="text-[11px] text-muted-foreground">{row.sub}</p>
                  </div>
                  <span className="text-[12px] font-mono text-muted-foreground">{row.value}</span>
                </div>
              ))}
            </div>
          </section>

        </div>
      </div>

      {/* Create / Edit user dialog */}
      <Dialog open={showCreate || !!editing} onOpenChange={open => { if (!open) { setShowCreate(false); setEditing(null); } }}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-auto">
          <DialogHeader>
            <DialogTitle className="text-[15px]">
              {editing ? `Edit ${editing.name}` : "Add team member"}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 pt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-[12px]">Full name</Label>
                <Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="Finance Manager" className="h-9 text-[13px]" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-[12px]">Email</Label>
                <Input value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                  placeholder="finance@company.ng" className="h-9 text-[13px]" disabled={!!editing} />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-[12px]">{editing ? "New password (leave blank to keep)" : "Password"}</Label>
              <Input type="password" value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                placeholder={editing ? "••••••••" : "Minimum 8 characters"} className="h-9 text-[13px]" />
            </div>

            {/* Admin toggle */}
            <div className="flex items-center gap-3 p-3 bg-muted/30 rounded-lg">
              <button
                onClick={() => setForm(f => ({ ...f, is_admin: !f.is_admin }))}
                className={cn(
                  "w-9 h-5 rounded-full transition-colors relative shrink-0",
                  form.is_admin ? "bg-foreground" : "bg-border"
                )}>
                <span className={cn(
                  "absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform",
                  form.is_admin ? "translate-x-4" : "translate-x-0"
                )} />
              </button>
              <div>
                <p className="text-[12px] font-medium">Administrator</p>
                <p className="text-[11px] text-muted-foreground">Admins have all permissions automatically</p>
              </div>
            </div>

            {/* Permissions matrix */}
            {!form.is_admin && (
              <div className="space-y-3">
                <Label className="text-[12px]">Permissions</Label>
                {PERMISSION_GROUPS.map(group => (
                  <div key={group.label}>
                    <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">
                      {group.label}
                    </p>
                    <div className="space-y-1">
                      {group.perms.map(p => {
                        const checked = form.permissions.includes(p);
                        return (
                          <button key={p} onClick={() => togglePerm(p)}
                            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-muted/50 transition-colors text-left">
                            <div className={cn(
                              "w-4 h-4 rounded flex items-center justify-center border transition-colors shrink-0",
                              checked ? "bg-foreground border-foreground" : "border-border"
                            )}>
                              {checked && <CheckCircle2 className="w-3 h-3 text-background" />}
                            </div>
                            <span className="text-[12px]">{PERMISSION_LABELS[p] ?? p}</span>
                            <span className="text-[10px] font-mono text-muted-foreground/50 ml-auto">{p}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <Button className="w-full h-9 text-[13px]"
              onClick={editing ? handleUpdate : handleCreate}
              disabled={!form.name || (!editing && !form.email) || (!editing && !form.password) || createUser.isPending || updateUser.isPending}>
              {editing ? "Save changes" : "Create user"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

    </div>
  );
}
