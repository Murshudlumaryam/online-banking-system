import { Outlet, useLocation } from "react-router";

import { AppShell, type NavItem } from "@/components/layout/AppShell";

const navItems: NavItem[] = [
  { to: "/app/dashboard", label: "Dashboard" },
  { to: "/app/accounts", label: "Accounts" },
  { to: "/app/transfer", label: "Transfer" },
  { to: "/app/transactions", label: "Transactions" },
  { to: "/app/beneficiaries", label: "Beneficiaries" },
  { to: "/app/scheduled-payments", label: "Scheduled payments" },
  { to: "/app/cards", label: "Cards" },
  { to: "/app/profile", label: "Profile" },
];

const titles: Record<string, string> = {
  "/app/dashboard": "Dashboard",
  "/app/accounts": "Accounts",
  "/app/transfer": "Transfer money",
  "/app/transactions": "Transactions",
  "/app/beneficiaries": "Beneficiaries",
  "/app/scheduled-payments": "Scheduled payments",
  "/app/cards": "Cards",
  "/app/profile": "Profile",
};

export function CustomerLayout() {
  const location = useLocation();
  const title =
    Object.entries(titles).find(([path]) => location.pathname.startsWith(path))?.[1] ?? "Ledger";

  return (
    <AppShell navItems={navItems} title={title}>
      <Outlet />
    </AppShell>
  );
}
