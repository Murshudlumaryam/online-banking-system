import type { ReactNode } from "react";

import { statusTone } from "@/lib/format";

const toneClasses = {
  success: "bg-forest-500/10 text-forest-600",
  warning: "bg-amber-500/10 text-amber-600",
  danger: "bg-brick-500/10 text-brick-600",
  neutral: "bg-slate-200 text-slate-600",
};

export function Badge({ children, status }: { children: ReactNode; status?: string }) {
  const tone = status ? statusTone(status) : "neutral";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${toneClasses[tone]}`}
    >
      {children}
    </span>
  );
}
