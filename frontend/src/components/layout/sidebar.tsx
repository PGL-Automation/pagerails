"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  LayoutDashboard, RefreshCw, FileUp, Shield,
  Settings, ChevronRight, AlertTriangle, Building2, LogOut, Rss,
  CheckSquare, PlusCircle, KeyRound,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { logout, currentUser, apiFetch } from "@/lib/api";

const NAV = [
  { href: "/dashboard",  label: "Dashboard",    icon: LayoutDashboard },
  { href: "/payouts",    label: "Payouts",       icon: CheckSquare },
  { href: "/payouts/new", label: "Raise Request", icon: PlusCircle },
  { href: "/runs",       label: "Runs",          icon: RefreshCw },
  { href: "/review",     label: "Review Queue",  icon: AlertTriangle,  highlight: true },
  { href: "/accounts",   label: "Accounts",      icon: Building2 },
  { href: "/feeds",      label: "Data Feeds",    icon: Rss },
  { href: "/files",      label: "Files",         icon: FileUp },
  { href: "/audit",      label: "Audit Log",     icon: Shield },
  { href: "/settings",   label: "Settings",      icon: Settings },
];

export function Sidebar() {
  const path   = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<{ name: string; role: string } | null>(null);
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    const u = currentUser();
    setUser(u);
    if (u) {
      apiFetch("/api/payouts/pending")
        .then((data: unknown) => {
          if (Array.isArray(data)) setPendingCount(data.length);
          else if (data && typeof data === "object" && "items" in data && Array.isArray((data as { items: unknown[] }).items))
            setPendingCount((data as { items: unknown[] }).items.length);
        })
        .catch(() => {/* silently ignore — user may not have approve_payout */});
    }
  }, []);

  function handleLogout() {
    logout();
    router.push("/login");
  }

  const initials = user?.name
    ? user.name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase()
    : "??";

  return (
    <aside className="flex flex-col w-[220px] min-h-screen bg-sidebar border-r border-sidebar-border shrink-0">
      {/* Wordmark */}
      <div className="h-14 flex items-center px-5 border-b border-sidebar-border">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded bg-white/10 flex items-center justify-center">
            <RefreshCw className="w-3.5 h-3.5 text-white" />
          </div>
          <div>
            <p className="text-[13px] font-semibold text-white leading-none">PageRails</p>
            <p className="text-[10px] text-sidebar-foreground/50 mt-0.5 leading-none">Page Capital Group</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 px-2">
        <div className="space-y-0.5">
          {NAV.map(({ href, label, icon: Icon, highlight }) => {
            const active = path === href || (href !== "/dashboard" && path.startsWith(href));
            const showBadge = href === "/payouts" && pendingCount > 0;
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded-md text-[13px] font-medium transition-colors",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground"
                )}
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span className="flex-1">{label}</span>
                {showBadge && (
                  <Badge className="ml-auto h-4 min-w-4 px-1 text-[10px] bg-amber-500 text-white border-0">
                    {pendingCount}
                  </Badge>
                )}
                {active && !highlight && !showBadge && <ChevronRight className="w-3 h-3 opacity-40" />}
              </Link>
            );
          })}
        </div>
      </nav>

      {/* User */}
      <div className="p-3 border-t border-sidebar-border space-y-1">
        <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-md">
          <div className="w-7 h-7 rounded-full bg-white/10 flex items-center justify-center text-[11px] font-semibold text-white shrink-0">
            {initials}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[12px] font-medium text-white truncate">{user?.name ?? "Not signed in"}</p>
            <p className="text-[10px] text-sidebar-foreground/50 truncate">{user?.role ?? ""}</p>
          </div>
        </div>
        <div className="flex gap-1">
          <Link
            href="/pin-setup"
            className="flex-1 flex items-center gap-2 px-2 py-1.5 rounded-md text-[12px] text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/40 transition-colors"
          >
            <KeyRound className="w-3.5 h-3.5" />
            Set PIN
          </Link>
          <button
            onClick={handleLogout}
            className="flex-1 flex items-center gap-2 px-2 py-1.5 rounded-md text-[12px] text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/40 transition-colors"
          >
            <LogOut className="w-3.5 h-3.5" />
            Sign out
          </button>
        </div>
      </div>
    </aside>
  );
}
