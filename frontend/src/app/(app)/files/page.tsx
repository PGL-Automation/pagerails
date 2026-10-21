"use client";

import { useState } from "react";
import { Topbar } from "@/components/layout/topbar";
import { useAccounts } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Upload, FileSpreadsheet, FileText, File, X, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

const FEED_ICONS: Record<string, React.ElementType> = {
  xlsx: FileSpreadsheet,
  xls:  FileSpreadsheet,
  csv:  FileSpreadsheet,
  pdf:  FileText,
  sta:  File,
};

const RECENT_UPLOADS = [
  { filename: "bank_2026-10.xlsx",       accountId: "PAM-OPS-01",    uploadedAt: "2026-10-31T10:22:00Z", size: 142000 },
  { filename: "gl_2026-10.csv",          accountId: "PAM-OPS-01",    uploadedAt: "2026-10-31T10:24:00Z", size: 84000  },
  { filename: "statement_2026-10.pdf",   accountId: "PAM-CLIENT-01", uploadedAt: "2026-10-31T10:28:00Z", size: 312000 },
  { filename: "cashbook_2026-10.xlsx",   accountId: "PAM-CLIENT-01", uploadedAt: "2026-10-31T10:30:00Z", size: 92000  },
  { filename: "custodian_2026-10.csv",   accountId: "PAM-MMF-CUST",  uploadedAt: "2026-10-31T10:32:00Z", size: 201000 },
  { filename: "PCL_OPS_2026-10.sta",     accountId: "PCL-OPS-01",    uploadedAt: "2026-10-31T10:35:00Z", size: 54000  },
];

function fmtSize(bytes: number) {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

export default function FilesPage() {
  const { data: accountsData } = useAccounts();
  const ACCOUNTS: any[] = accountsData?.accounts ?? [];
  const [selectedAccount, setSelectedAccount] = useState("");
  const [dragging, setDragging] = useState(false);
  const [staged, setStaged] = useState<File[]>([]);
  const [uploaded, setUploaded] = useState<string[]>([]);

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files);
    setStaged(prev => [...prev, ...files]);
  }

  function removeStaged(name: string) {
    setStaged(prev => prev.filter(f => f.name !== name));
  }

  function upload() {
    const names = staged.map(f => f.name);
    setUploaded(prev => [...prev, ...names]);
    setStaged([]);
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <Topbar title="File Upload" subtitle="Drop input files per account" />

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto space-y-6">

          {/* Upload card */}
          <div className="bg-card border border-border rounded-xl p-6 space-y-5">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-[12px]">Account</Label>
                <Select value={selectedAccount} onValueChange={v => setSelectedAccount(v ?? "")}>
                  <SelectTrigger className="h-9 text-[13px]">
                    <SelectValue placeholder="Select account…" />
                  </SelectTrigger>
                  <SelectContent>
                    {ACCOUNTS.map(a => (
                      <SelectItem key={a.id} value={a.id} className="text-[13px]">
                        <span className="font-mono">{a.id}</span>
                        <span className="text-muted-foreground ml-2">{a.bank}</span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-[12px]">Period</Label>
                <Select>
                  <SelectTrigger className="h-9 text-[13px]">
                    <SelectValue placeholder="Select period…" />
                  </SelectTrigger>
                  <SelectContent>
                    {["2026-10", "2026-09", "2026-08"].map(p => (
                      <SelectItem key={p} value={p} className="text-[13px] font-mono">{p}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Drop zone */}
            <div
              onDragOver={e => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cn(
                "border-2 border-dashed rounded-xl p-10 flex flex-col items-center gap-3 transition-colors cursor-pointer",
                dragging ? "border-foreground bg-muted/40" : "border-border hover:border-muted-foreground/40 hover:bg-muted/20"
              )}
              onClick={() => document.getElementById("file-input")?.click()}
            >
              <div className="w-10 h-10 rounded-xl bg-muted flex items-center justify-center">
                <Upload className="w-5 h-5 text-muted-foreground" />
              </div>
              <div className="text-center">
                <p className="text-[13px] font-medium">Drop files here or click to browse</p>
                <p className="text-[11px] text-muted-foreground mt-1">CSV, XLS, XLSX, PDF, STA — up to 50MB each</p>
              </div>
              <input
                id="file-input"
                type="file"
                multiple
                className="hidden"
                accept=".csv,.xls,.xlsx,.pdf,.sta"
                onChange={e => {
                  if (e.target.files) setStaged(prev => [...prev, ...Array.from(e.target.files!)]);
                }}
              />
            </div>

            {/* Staged files */}
            {staged.length > 0 && (
              <div className="space-y-2">
                {staged.map(f => {
                  const ext = (f.name ?? "").split(".").pop()?.toLowerCase() ?? "";
                  const Icon = FEED_ICONS[ext] ?? File;
                  return (
                    <div key={f.name} className="flex items-center gap-3 p-3 bg-muted/30 rounded-lg">
                      <Icon className="w-4 h-4 text-muted-foreground shrink-0" />
                      <span className="text-[13px] font-medium flex-1 truncate">{f.name}</span>
                      <span className="text-[11px] text-muted-foreground tabular-nums">{fmtSize(f.size)}</span>
                      <button onClick={() => removeStaged(f.name)} className="text-muted-foreground hover:text-foreground transition-colors">
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  );
                })}
                <Button
                  className="w-full h-9 text-[13px] gap-2 mt-1"
                  onClick={upload}
                  disabled={!selectedAccount}
                >
                  <Upload className="w-3.5 h-3.5" />
                  Upload {staged.length} file{staged.length !== 1 ? "s" : ""}
                </Button>
              </div>
            )}

            {uploaded.length > 0 && (
              <div className="flex items-center gap-2 text-emerald-600 text-[12px]">
                <CheckCircle2 className="w-4 h-4" />
                {uploaded.length} file{uploaded.length !== 1 ? "s" : ""} uploaded successfully
              </div>
            )}
          </div>

          {/* Recent uploads */}
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="px-5 py-3.5 border-b border-border">
              <h2 className="text-[13px] font-semibold">Recent Uploads</h2>
              <p className="text-[11px] text-muted-foreground mt-0.5">Today · Oct 31, 2026</p>
            </div>
            <div className="divide-y divide-border">
              {RECENT_UPLOADS.map((u, i) => {
                const ext = u.filename.split(".").pop()?.toLowerCase() ?? "";
                const Icon = FEED_ICONS[ext] ?? File;
                return (
                  <div key={i} className="px-5 py-3 flex items-center gap-3">
                    <Icon className="w-4 h-4 text-muted-foreground shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-[13px] font-medium truncate">{u.filename}</p>
                      <p className="text-[11px] text-muted-foreground">
                        <span className="font-mono">{u.accountId}</span> · {fmtSize(u.size)}
                      </p>
                    </div>
                    <span className="text-[11px] text-muted-foreground tabular-nums shrink-0">
                      {fmtTime(u.uploadedAt)}
                    </span>
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                  </div>
                );
              })}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
