"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { signOff } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader,
  DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { CheckCircle2, Loader2 } from "lucide-react";

export function SignoffButton({ runId }: { runId: string }) {
  const router = useRouter();
  const [open, setOpen]       = useState(false);
  const [checker, setChecker] = useState("");
  const [note, setNote]       = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");

  async function submit() {
    if (!checker) return;
    setLoading(true);
    setError("");
    try {
      await signOff(runId, { checker, note });
      setOpen(false);
      router.refresh();
    } catch (e: any) {
      setError(e.message ?? "Sign-off failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Button
        size="sm"
        className="h-6 text-[11px] ml-2 bg-foreground text-background hover:bg-foreground/90"
        onClick={() => setOpen(true)}
      >
        Sign off
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="text-[14px]">Sign off run</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <div className="space-y-1.5">
            <Label className="text-[12px]">Checker name</Label>
            <Input
              value={checker}
              onChange={e => setChecker(e.target.value)}
              placeholder="Your full name"
              className="h-9 text-[13px]"
            />
            <p className="text-[11px] text-muted-foreground">Must be different from the maker</p>
          </div>
          <div className="space-y-1.5">
            <Label className="text-[12px]">Note (optional)</Label>
            <Input
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="All items reviewed and agreed"
              className="h-9 text-[13px]"
            />
          </div>
          {error && <p className="text-[12px] text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
          <Button className="w-full h-9 text-[13px] gap-2" onClick={submit} disabled={!checker || loading}>
            {loading
              ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />Signing off…</>
              : <><CheckCircle2 className="w-3.5 h-3.5" />Confirm sign-off</>
            }
          </Button>
        </div>
      </DialogContent>
      </Dialog>
    </>
  );
}
