import { Navigate, createBrowserRouter } from "@/lib/router";

import { AdminRoute, GuestOnlyRoute, ProtectedRoute } from "@/components/layout/RouteGuards";
import { AdminLayout } from "@/pages/admin/AdminLayout";
import { AdminAccountsPage } from "@/pages/admin/AdminAccountsPage";
import { AdminAuditLogsPage } from "@/pages/admin/AdminAuditLogsPage";
import { AdminCustomerDetailPage } from "@/pages/admin/AdminCustomerDetailPage";
import { AdminCustomersPage } from "@/pages/admin/AdminCustomersPage";
import { AdminExchangeRatesPage } from "@/pages/admin/AdminExchangeRatesPage";
import { AdminTransactionDetailPage } from "@/pages/admin/AdminTransactionDetailPage";
import { AdminTransactionsPage } from "@/pages/admin/AdminTransactionsPage";
import { ForgotPasswordPage } from "@/pages/auth/ForgotPasswordPage";
import { LoginPage } from "@/pages/auth/LoginPage";
import { RegisterPage } from "@/pages/auth/RegisterPage";
import { ResetPasswordPage } from "@/pages/auth/ResetPasswordPage";
import { AccountDetailPage } from "@/pages/customer/AccountDetailPage";
import { AccountsPage } from "@/pages/customer/AccountsPage";
import { BeneficiariesPage } from "@/pages/customer/BeneficiariesPage";
import { CardsPage } from "@/pages/customer/CardsPage";
import { CustomerLayout } from "@/pages/customer/CustomerLayout";
import { DashboardPage } from "@/pages/customer/DashboardPage";
import { ProfilePage } from "@/pages/customer/ProfilePage";
import { TransactionDetailPage } from "@/pages/customer/TransactionDetailPage";
import { TransactionsPage } from "@/pages/customer/TransactionsPage";
import { TransferPage } from "@/pages/customer/TransferPage";

export const router = createBrowserRouter([
  { index: true, element: <Navigate to="/login" replace /> },

  {
    path: "/login",
    element: (
      <GuestOnlyRoute>
        <LoginPage />
      </GuestOnlyRoute>
    ),
  },
  {
    path: "/register",
    element: (
      <GuestOnlyRoute>
        <RegisterPage />
      </GuestOnlyRoute>
    ),
  },
  {
    path: "/forgot-password",
    element: (
      <GuestOnlyRoute>
        <ForgotPasswordPage />
      </GuestOnlyRoute>
    ),
  },
  { path: "/reset-password/:token", element: <ResetPasswordPage /> },

  {
    path: "/app",
    element: (
      <ProtectedRoute>
        <CustomerLayout />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <Navigate to="dashboard" replace /> },
      { path: "dashboard", element: <DashboardPage /> },
      { path: "accounts", element: <AccountsPage /> },
      { path: "accounts/:accountId", element: <AccountDetailPage /> },
      { path: "transfer", element: <TransferPage /> },
      { path: "transactions", element: <TransactionsPage /> },
      { path: "transactions/:transactionId", element: <TransactionDetailPage /> },
      { path: "beneficiaries", element: <BeneficiariesPage /> },
      { path: "cards", element: <CardsPage /> },
      { path: "profile", element: <ProfilePage /> },
    ],
  },

  {
    path: "/admin",
    element: (
      <AdminRoute>
        <AdminLayout />
      </AdminRoute>
    ),
    children: [
      { index: true, element: <Navigate to="customers" replace /> },
      { path: "customers", element: <AdminCustomersPage /> },
      { path: "customers/:customerId", element: <AdminCustomerDetailPage /> },
      { path: "accounts", element: <AdminAccountsPage /> },
      { path: "transactions", element: <AdminTransactionsPage /> },
      { path: "transactions/:transactionId", element: <AdminTransactionDetailPage /> },
      { path: "exchange-rates", element: <AdminExchangeRatesPage /> },
      { path: "audit-logs", element: <AdminAuditLogsPage /> },
    ],
  },

  { path: "*", element: <Navigate to="/login" replace /> },
]);
