import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  icon?: LucideIcon;
  trend?: "up" | "down" | "neutral";
  accent?: "default" | "danger" | "warning" | "success";
  className?: string;
}

const ACCENT_ICON: Record<string, string> = {
  default: "bg-gray-100 text-gray-500",
  danger:  "bg-red-50 text-red-500",
  warning: "bg-amber-50 text-amber-500",
  success: "bg-emerald-50 text-emerald-600",
};

const ACCENT_VALUE: Record<string, string> = {
  default: "text-foreground",
  danger:  "text-red-600",
  warning: "text-amber-600",
  success: "text-emerald-600",
};

export function StatCard({ label, value, sub, icon: Icon, accent = "default", className }: StatCardProps) {
  return (
    <div className={cn(
      "bg-card border border-border rounded-xl p-5 flex flex-col gap-3",
      className
    )}>
      <div className="flex items-start justify-between">
        <p className="text-[12px] font-medium text-muted-foreground tracking-wide uppercase">{label}</p>
        {Icon && (
          <div className={cn("w-7 h-7 rounded-lg flex items-center justify-center", ACCENT_ICON[accent])}>
            <Icon className="w-3.5 h-3.5" />
          </div>
        )}
      </div>
      <div>
        <p className={cn("text-2xl font-semibold tabular-nums", ACCENT_VALUE[accent])}>
          {value}
        </p>
        {sub && <p className="text-[12px] text-muted-foreground mt-1">{sub}</p>}
      </div>
    </div>
  );
}
