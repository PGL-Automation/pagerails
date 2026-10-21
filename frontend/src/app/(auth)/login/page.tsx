"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { login } from "@/lib/api";
import { BASE } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RefreshCw, AlertCircle, Info } from "lucide-react";
import { cn } from "@/lib/utils";

type Tab = "pin" | "password";

async function pinLogin(email: string, pin: string) {
  const res = await fetch(`${BASE}/api/auth/pin-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, pin }),
  });
  if (!res.ok) throw new Error("Invalid email or PIN");
  const data = await res.json();
  if (typeof window !== "undefined") {
    sessionStorage.setItem("recon_token", data.access_token);
    sessionStorage.setItem("recon_user", JSON.stringify({
      name: data.name, role: data.role, permissions: data.permissions ?? []
    }));
  }
  return data as { access_token: string; name: string; role: string; permissions: string[] };
}

export default function LoginPage() {
  const router       = useRouter();
  const searchParams = useSearchParams();

  const prefillEmail = searchParams.get("email") ?? "";

  const [tab,      setTab]      = useState<Tab>("pin");
  const [email,    setEmail]    = useState(prefillEmail);
  const [pin,      setPin]      = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);

  const pinRef      = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  // When a pre-filled email arrives, focus the credential field
  useEffect(() => {
    if (prefillEmail) {
      if (tab === "pin") {
        pinRef.current?.focus();
      } else {
        passwordRef.current?.focus();
      }
    }
  }, [prefillEmail, tab]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (tab === "pin") {
        await pinLogin(email, pin);
      } else {
        await login(email, password);
      }
      router.replace("/dashboard");
    } catch {
      setError(tab === "pin" ? "Invalid email or PIN" : "Invalid email or password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center gap-2.5 mb-10">
          <div className="w-8 h-8 rounded-lg bg-foreground flex items-center justify-center">
            <RefreshCw className="w-4 h-4 text-background" />
          </div>
          <div>
            <p className="text-[15px] font-semibold leading-none">PageRails</p>
            <p className="text-[11px] text-muted-foreground mt-0.5">Page Capital Group</p>
          </div>
        </div>

        <div className="bg-card border border-border rounded-xl p-6">
          <h1 className="text-[16px] font-semibold mb-1">Sign in</h1>
          <p className="text-[12px] text-muted-foreground mb-4">
            {prefillEmail
              ? "Enter your PIN to continue"
              : "Enter your work email and PIN"}
          </p>

          {/* Approval-email hint */}
          {prefillEmail && (
            <div className="flex items-start gap-2 text-[12px] text-blue-700 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 mb-4">
              <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              Logging in to review a payment request
            </div>
          )}

          {/* Tab switcher */}
          <div className="flex rounded-lg overflow-hidden border border-border mb-4">
            <button
              type="button"
              onClick={() => { setTab("pin"); setError(""); }}
              className={cn(
                "flex-1 text-[12px] py-1.5 font-medium transition-colors",
                tab === "pin"
                  ? "bg-foreground text-background"
                  : "bg-transparent text-muted-foreground hover:bg-muted/40",
              )}
            >
              PIN
            </button>
            <button
              type="button"
              onClick={() => { setTab("password"); setError(""); }}
              className={cn(
                "flex-1 text-[12px] py-1.5 font-medium transition-colors",
                tab === "password"
                  ? "bg-foreground text-background"
                  : "bg-transparent text-muted-foreground hover:bg-muted/40",
              )}
            >
              Password
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-[12px]">Email address</Label>
              <Input
                type="email"
                placeholder="you@pagecapital.ng"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="h-9 text-[13px]"
                required
              />
            </div>

            {tab === "pin" ? (
              <div className="space-y-1.5">
                <Label className="text-[12px]">PIN</Label>
                <Input
                  ref={pinRef}
                  type="password"
                  inputMode="numeric"
                  placeholder="Enter your PIN"
                  value={pin}
                  onChange={e => setPin(e.target.value)}
                  className="h-9 text-[13px]"
                  required
                />
              </div>
            ) : (
              <div className="space-y-1.5">
                <Label className="text-[12px]">Password</Label>
                <Input
                  ref={passwordRef}
                  type="password"
                  placeholder="Enter your password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="h-9 text-[13px]"
                  required
                />
              </div>
            )}

            {error && (
              <div className="flex items-center gap-2 text-[12px] text-red-600 bg-red-50 rounded-lg px-3 py-2">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                {error}
              </div>
            )}

            <Button type="submit" className="w-full h-9 text-[13px]" disabled={loading}>
              {loading ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          <div className="mt-5 pt-4 border-t border-border">
            <p className="text-[11px] text-muted-foreground">
              First-time setup: use <code className="font-mono bg-muted px-1 rounded text-[10px]">admin@pagerails.app</code> with the password set in your <code className="font-mono bg-muted px-1 rounded text-[10px]">.env</code> file.
              Create your team accounts from Settings after logging in.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
