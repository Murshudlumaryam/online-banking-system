import { useState } from "react";
import type { FormEvent } from "react";

import { useAccounts } from "@/hooks/useAccounts";
import { useBeneficiaries } from "@/hooks/useBeneficiaries";
import { useConfirmTransfer, useInitiateTransfer } from "@/hooks/useTransactions";
import { getApiErrorCode, getApiErrorMessage } from "@/lib/apiClient";
import { formatMoney } from "@/lib/format";
import type { InitiateTransferResponse } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Card, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { OtpConfirmModal } from "@/components/modals/OtpConfirmModal";

// Error codes that mean the transaction itself is no longer confirmable â€”
// the modal should close and the person should start a fresh transfer,
// rather than retry the same OTP.
const TERMINAL_CONFIRM_ERRORS = new Set(["OTP_EXPIRED", "TOO_MANY_OTP_ATTEMPTS", "TRANSACTION_ALREADY_PROCESSED"]);

export function TransferPage() {
  const { data: accounts, isLoading: accountsLoading } = useAccounts();
  const { data: beneficiaries } = useBeneficiaries();

  const [senderAccountId, setSenderAccountId] = useState("");
  const [receiverAccountNumber, setReceiverAccountNumber] = useState("");
  const [amount, setAmount] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [pendingTransfer, setPendingTransfer] = useState<InitiateTransferResponse | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const initiateTransfer = useInitiateTransfer();
  const confirmTransfer = useConfirmTransfer();

  const activeAccounts = (accounts ?? []).filter((a) => a.status === "ACTIVE");
  const selectedAccount = activeAccounts.find((a) => a.id === senderAccountId);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setSuccessMessage(null);

    if (!selectedAccount) {
      setFormError("Choose an account to transfer from.");
      return;
    }

    try {
      const result = await initiateTransfer.mutateAsync({
        sender_account_id: selectedAccount.id,
        receiver_account_number: receiverAccountNumber.trim(),
        amount,
        currency: selectedAccount.currency,
      });
      setPendingTransfer(result);
    } catch (err) {
      setFormError(getApiErrorMessage(err, "Couldn't start this transfer."));
    }
  }

  async function handleConfirm(otpCode: string) {
    if (!pendingTransfer) return;
    setConfirmError(null);
    try {
      await confirmTransfer.mutateAsync({
        transactionId: pendingTransfer.transaction.id,
        otpCode,
      });
      setPendingTransfer(null);
      setSuccessMessage(
        `Transfer ${pendingTransfer.transaction.reference_number} completed successfully.`,
      );
      setAmount("");
      setReceiverAccountNumber("");
    } catch (err) {
      const code = getApiErrorCode(err);
      const message = getApiErrorMessage(err, "That code didn't work.");
      if (code && TERMINAL_CONFIRM_ERRORS.has(code)) {
        setPendingTransfer(null);
        setFormError(`${message} Please start a new transfer.`);
      } else {
        setConfirmError(message);
      }
    }
  }

  if (accountsLoading) return <Spinner label="Loading your accounts" />;

  return (
    <div className="max-w-lg">
      {successMessage && (
        <div className="mb-4 rounded-md border border-forest-500/30 bg-forest-500/5 px-4 py-3 text-sm text-forest-600">
          {successMessage}
        </div>
      )}

      <Card className="p-6">
        <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
          {formError && <ErrorBanner message={formError} />}

          <Select
            label="From account"
            required
            value={senderAccountId}
            onChange={(e) => setSenderAccountId(e.target.value)}
          >
            <option value="" disabled>
              Select an account
            </option>
            {activeAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.account_number} &middot; {formatMoney(account.balance, account.currency)}
              </option>
            ))}
          </Select>

          <Input
            label="Receiver account number"
            required
            value={receiverAccountNumber}
            onChange={(e) => setReceiverAccountNumber(e.target.value)}
            list="beneficiary-accounts"
            placeholder="Enter or pick a saved beneficiary"
          />
          {beneficiaries && beneficiaries.length > 0 && (
            <datalist id="beneficiary-accounts">
              {beneficiaries.map((b) => (
                <option key={b.id} value={b.beneficiary_account_number}>
                  {b.nickname ?? b.beneficiary_name}
                </option>
              ))}
            </datalist>
          )}

          <Input
            label={`Amount${selectedAccount ? ` (${selectedAccount.currency})` : ""}`}
            required
            inputMode="decimal"
            placeholder="0.00"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />

          <Button type="submit" isLoading={initiateTransfer.isPending} className="mt-2">
            Continue
          </Button>
        </form>
      </Card>

      {pendingTransfer && (
        <OtpConfirmModal
          referenceNumber={pendingTransfer.transaction.reference_number}
          expiresInSeconds={pendingTransfer.otp_expires_in_seconds}
          isSubmitting={confirmTransfer.isPending}
          errorMessage={confirmError}
          onConfirm={handleConfirm}
          onCancel={() => {
            setPendingTransfer(null);
            setConfirmError(null);
          }}
        />
      )}
    </div>
  );
}
