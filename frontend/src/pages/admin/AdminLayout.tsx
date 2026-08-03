import { Outlet, useLocation } from "@/lib/router";

import { AppShell, type NavItem } from "@/components/layout/AppShell";

const navItems: NavItem[] = [
  { to: "/admin/customers", label: "Customers" },
  { to: "/admin/accounts", label: "Accounts" },
  { to: "/admin/transactions", label: "Transactions" },
  { to: "/admin/exchange-rates", label: "Exchange rates" },
  { to: "/admin/audit-logs", label: "Audit logs" },
];

const titles: Record<string, string> = {
  "/admin/customers": "Customers",
  "/admin/accounts": "Accounts",
  "/admin/transactions": "Transactions",
  "/admin/exchange-rates": "Exchange rates",
  "/admin/audit-logs": "Audit logs",
};

export function AdminLayout() {
  const location = useLocation();
  const title =
    Object.entries(titles).find(([path]) => location.pathname.startsWith(path))?.[1] ?? "Admin";

  return (
    <AppShell navItems={navItems} title={title}>
      <Outlet />
    </AppShell>
  );
}
