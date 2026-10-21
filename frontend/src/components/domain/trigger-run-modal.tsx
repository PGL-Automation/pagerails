"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { triggerRun } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader,
  DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { Play, Loader2, CheckCircle2 } from "lucide-react";

const ACCOUNTS = [
  "PAM-PRV-CLIENTS", "PAM-OPS-01", "PAM-CLIENT-01",
  "PAM-MMF-CUST", "PCL-OPS-01", "PCL-COLL-01",
];

export function TriggerRunModal() {
  const router = useRouter();
  const [open, setOpen]         = useState(false);
  const [period, setPeriod]     = useState("2026-09");
  const [maker, setMaker]       = useState("");
  const [selected, setSelected] = useState<string[]>(["PAM-PRV-CLIENTS"]);
  const [status, setStatus]     = useState<"idle" | "running" | "done" | "error">("idle");
  const [message, setMessage]   = useState("");

  function toggle(id: string) {
    setSelected(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  }

  async function submit() {
    if (!selected.length || !period || !maker) return;
    setStatus("running");
    setMessage("");
    try {
      const res = await triggerRun({ account_ids: selected, period, maker });
      setStatus("done");
      setMessage(res.message);
      setTimeout(() => {
        setOpen(false);
        setStatus("idle");
        router.refresh();
      }, 2500);
    } catch (e: any) {
      setStatus("error");
      setMessage(e.message ?? "Run failed");
    }
  }

  return (
    <>
      <Button size="sm" className="h-8 text-[12px] gap-1.5" onClick={() => setOpen(true)}>
        <Play className="w-3 h-3" />
        New Run
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>

      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-[15px]">Trigger reconciliation run</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 pt-2">
          {/* Period */}
          <div className="space-y-1.5">
            <Label className="text-[12px]">Period</Label>
            <Input
              value={period}
              onChange={e => setPeriod(e.target.value)}
              placeholder="2026-09 or 2026-09-01:2026-09-30"
              className="h-9 text-[13px] font-mono"
            />
            <p className="text-[11px] text-muted-foreground">Month (2026-09), day (2026-09-29), or range</p>
          </div>

          {/* Maker */}
          <div className="space-y-1.5">
            <Label className="text-[12px]">Your name (maker)</Label>
            <Input
              value={maker}
              onChange={e => setMaker(e.target.value)}
              placeholder="Your full name"
              className="h-9 text-[13px]"
            />
          </div>

          {/* Accounts */}
          <div className="space-y-1.5">
            <Label className="text-[12px]">Accounts</Label>
            <div className="grid grid-cols-2 gap-1.5">
              {ACCOUNTS.map(id => (
                <button
                  key={id}
                  type="button"
                  onClick={() => toggle(id)}
                  className={`text-left px-3 py-2 rounded-lg border text-[12px] font-mono transition-colors ${
                    selected.includes(id)
                      ? "border-foreground bg-foreground text-background"
                      : "border-border hover:border-muted-foreground/50"
                  }`}
                >
                  {id}
                </button>
              ))}
            </div>
          </div>

          {/* Status */}
          {status === "done" && (
            <div className="flex items-center gap-2 text-[12px] text-emerald-600 bg-emerald-50 rounded-lg px-3 py-2">
              <CheckCircle2 className="w-3.5 h-3.5" />
              {message}
            </div>
          )}
          {status === "error" && (
            <div className="text-[12px] text-red-600 bg-red-50 rounded-lg px-3 py-2">{message}</div>
          )}

          <Button
            className="w-full h-9 text-[13px] gap-2"
            onClick={submit}
            disabled={!selected.length || !period || !maker || status === "running"}
          >
            {status === "running" ? (
              <><Loader2 className="w-3.5 h-3.5 animate-spin" />Running…</>
            ) : (
              <><Play className="w-3.5 h-3.5" />Run {selected.length} account{selected.length !== 1 ? "s" : ""}</>
            )}
          </Button>
        </div>
      </DialogContent>
      </Dialog>
    </>
  );
}
