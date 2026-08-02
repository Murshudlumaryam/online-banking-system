import { forwardRef } from "react";
import type { ReactNode, SelectHTMLAttributes } from "react";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  error?: string;
  children: ReactNode;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, id, children, className = "", ...rest }, ref) => {
    const selectId = id ?? label.toLowerCase().replace(/\s+/g, "-");
    return (
      <div className="flex flex-col gap-1.5">
        <label htmlFor={selectId} className="text-sm font-medium text-slate-700">
          {label}
        </label>
        <select
          ref={ref}
          id={selectId}
          className={`rounded-md border bg-white px-3 py-2 text-sm text-ink focus:border-ledger-500 ${
            error ? "border-brick-500" : "border-slate-300"
          } ${className}`}
          aria-invalid={Boolean(error)}
          {...rest}
        >
          {children}
        </select>
        {error && <p className="text-sm text-brick-600">{error}</p>}
      </div>
    );
  },
);
Select.displayName = "Select";
