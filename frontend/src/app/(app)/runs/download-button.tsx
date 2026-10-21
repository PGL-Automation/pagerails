"use client";

import { Download } from "lucide-react";

export function DownloadButton({ href }: { href: string }) {
  function handleClick(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    // Trigger browser download without nesting <a> inside <a>
    const link = document.createElement("a");
    link.href = href;
    link.download = "";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className="w-7 h-7 flex items-center justify-center rounded-md hover:bg-muted opacity-0 group-hover:opacity-100 transition-opacity"
      title="Download reconciliation pack"
    >
      <Download className="w-3.5 h-3.5 text-muted-foreground" />
    </button>
  );
}
