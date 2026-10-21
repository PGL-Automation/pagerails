"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { BASE, getToken } from "@/lib/api";
import { CheckCircle2, KeyRound, AlertTriangle } from "lucide-react";

export default function PinSetupPage() {
  const router = useRouter();

  const [pin,        setPin]        = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [error,      setError]      = useState("");
  const [loading,    setLoading]    = useState(false);
  const [done,       setDone]       = useState(false);

  function validate(): string {
    if (!pin)                      return "Enter a PIN.";
    if (!/^\d{4,6}$/.test(pin))   return "PIN must be 4–6 digits.";
    if (pin !== confirmPin)        return "PINs do not match.";
    return "";
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const msg = validate();
    if (msg) { setError(msg); return; }
    setError("");
    setLoading(true);

    try {
      const token = getToken();
      const res = await fetch(`${BASE}/api/auth/pin/set`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ pin }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? `Error ${res.status}`);
      }

      setDone(true);
      setTimeout(() => router.push("/dashboard"), 2000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to set PIN.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6">

        {/* Icon + heading */}
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
            <KeyRound className="w-6 h-6 text-primary" />
          </div>
          <div>
            <h1 className="text-[18px] font-semibold text-foreground">Set your PIN</h1>
            <p className="text-[13px] text-muted-foreground mt-1">
              Your PIN is used for quick access and high-value approvals.
            </p>
          </div>
        </div>

        {done ? (
          /* Success state */
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-6 flex flex-col items-center gap-3 text-center">
            <CheckCircle2 className="w-8 h-8 text-emerald-500" />
            <p className="text-[14px] font-medium text-emerald-700">PIN set successfully</p>
            <p className="text-[12px] text-emerald-600">Redirecting to dashboard…</p>
          </div>
        ) : (
          /* Form */
          <form onSubmit={handleSubmit} className="space-y-4">

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 text-[13px] px-4 py-3 rounded-lg flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                {error}
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="pin" className="text-[12px]">PIN (4–6 digits)</Label>
              <Input
                id="pin"
                type="password"
                inputMode="numeric"
                pattern="\d{4,6}"
                maxLength={6}
                placeholder="••••"
                autoComplete="new-password"
                value={pin}
                onChange={e => setPin(e.target.value.replace(/\D/g, ""))}
                className="text-center tracking-[0.4em] text-[18px]"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="confirm-pin" className="text-[12px]">Confirm PIN</Label>
              <Input
                id="confirm-pin"
                type="password"
                inputMode="numeric"
                pattern="\d{4,6}"
                maxLength={6}
                placeholder="••••"
                autoComplete="new-password"
                value={confirmPin}
                onChange={e => setConfirmPin(e.target.value.replace(/\D/g, ""))}
                className="text-center tracking-[0.4em] text-[18px]"
              />
            </div>

            <Button
              type="submit"
              className="w-full"
              disabled={loading}
            >
              {loading ? "Setting PIN…" : "Set PIN"}
            </Button>

            <button
              type="button"
              className="w-full text-center text-[12px] text-muted-foreground hover:text-foreground transition-colors"
              onClick={() => router.push("/dashboard")}
            >
              Skip for now
            </button>

          </form>
        )}
      </div>
    </div>
  );
}
