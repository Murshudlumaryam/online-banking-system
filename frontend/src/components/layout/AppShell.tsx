import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router";

import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/Button";

export interface NavItem {
  to: string;
  label: string;
}

export function AppShell({
  navItems,
  title,
  children,
}: {
  navItems: NavItem[];
  title: string;
  children: ReactNode;
}) {
  const { logout, role } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex min-h-screen bg-paper">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white md:flex">
        <div className="flex h-16 items-center gap-2 border-b border-slate-200 px-5">
          <span className="font-display text-lg font-semibold text-ledger-800">Ledger</span>
          {role === "ADMIN" && (
            <span className="rounded bg-brass-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-brass-700">
              Admin
            </span>
          )}
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-3">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-ledger-50 text-ledger-800"
                    : "text-slate-600 hover:bg-slate-50 hover:text-ink"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-200 p-3">
          <Button variant="ghost" size="sm" className="w-full justify-start" onClick={handleLogout}>
            Sign out
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-4 md:px-8">
          <h1 className="font-display text-xl text-ink">{title}</h1>
          <button
            className="rounded-md px-3 py-1.5 text-sm text-slate-600 md:hidden"
            onClick={handleLogout}
          >
            Sign out
          </button>
        </header>
        <main className="flex-1 px-4 py-6 md:px-8 md:py-8">{children}</main>
      </div>
    </div>
  );
}
