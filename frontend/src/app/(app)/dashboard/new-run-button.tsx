"use client";
import { Button } from "@/components/ui/button";
import { BarChart3 } from "lucide-react";

export function NewRunButton() {
  return (
    <Button size="sm" className="h-8 text-[12px] gap-1.5">
      <BarChart3 className="w-3.5 h-3.5" />
      New Run
    </Button>
  );
}
