/**
 * Format minor units (kobo) to a human-readable NGN amount.
 * Matches the engine's fmt() convention exactly.
 */
export function fmtAmount(minor: number, opts?: { sign?: boolean; compact?: boolean }): string {
  const abs = Math.abs(minor);
  const isNeg = minor < 0;
  const major = abs / 100;

  if (opts?.compact && abs >= 1_000_000_00) {
    const billions = major / 1_000_000_000;
    if (billions >= 1) return `${isNeg ? "-" : ""}₦${billions.toFixed(2)}B`;
    const millions = major / 1_000_000;
    return `${isNeg ? "-" : ""}₦${millions.toFixed(2)}M`;
  }

  const formatted = new Intl.NumberFormat("en-NG", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(major);

  return `${isNeg ? "-" : opts?.sign ? "+" : ""}₦${formatted}`;
}

export function fmtDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtPeriod(periodEnd: string): string {
  const d = new Date(periodEnd);
  return d.toLocaleDateString("en-GB", { month: "long", year: "numeric" });
}

export function fmtConfidence(conf: number): string {
  return `${(conf * 100).toFixed(0)}%`;
}

export function amountClass(minor: number): string {
  if (minor > 0) return "amount-positive";
  if (minor < 0) return "amount-negative";
  return "amount-zero";
}
