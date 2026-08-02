import { useState } from "react";
import type { FormEvent } from "react";

import {
  useBeneficiaries,
  useCreateBeneficiary,
  useDeleteBeneficiary,
  useUpdateBeneficiary,
} from "@/hooks/useBeneficiaries";
import { getApiErrorMessage } from "@/lib/apiClient";
import type { BeneficiaryResponse } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";

function AddBeneficiaryForm({ onDone }: { onDone: () => void }) {
  const [accountNumber, setAccountNumber] = useState("");
  const [name, setName] = useState("");
  const [nickname, setNickname] = useState("");
  const [error, setError] = useState<string | null>(null);
  const createBeneficiary = useCreateBeneficiary();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await createBeneficiary.mutateAsync({
        beneficiary_account_number: accountNumber.trim(),
        beneficiary_name: name.trim(),
        nickname: nickname.trim() || undefined,
      });
      onDone();
    } catch (err) {
      setError(getApiErrorMessage(err, "Couldn't save this beneficiary."));
    }
  }

  return (
    <Card className="p-6">
      <h3 className="font-display text-lg text-ink">Add a beneficiary</h3>
      <form className="mt-4 flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
        {error && <ErrorBanner message={error} />}
        <Input
          label="Account number"
          required
          value={accountNumber}
          onChange={(e) => setAccountNumber(e.target.value)}
        />
        <Input label="Full name" required value={name} onChange={(e) => setName(e.target.value)} />
        <Input
          label="Nickname (optional)"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
        />
        <div className="flex gap-3">
          <Button type="submit" isLoading={createBeneficiary.isPending}>
            Save beneficiary
          </Button>
          <Button type="button" variant="ghost" onClick={onDone}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}

function BeneficiaryRow({ beneficiary }: { beneficiary: BeneficiaryResponse }) {
  const [isEditing, setIsEditing] = useState(false);
  const [nickname, setNickname] = useState(beneficiary.nickname ?? "");
  const updateBeneficiary = useUpdateBeneficiary();
  const deleteBeneficiary = useDeleteBeneficiary();

  async function handleSave() {
    await updateBeneficiary.mutateAsync({ id: beneficiary.id, payload: { nickname } });
    setIsEditing(false);
  }

  return (
    <li className="flex items-center justify-between px-5 py-4">
      <div>
        <p className="text-sm font-medium text-ink">{beneficiary.nickname ?? beneficiary.beneficiary_name}</p>
        <p className="font-mono text-xs text-slate-500">{beneficiary.beneficiary_account_number}</p>
      </div>
      {isEditing ? (
        <div className="flex items-center gap-2">
          <input
            className="rounded-md border border-slate-300 px-2 py-1 text-sm"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            placeholder="Nickname"
          />
          <Button size="sm" onClick={handleSave} isLoading={updateBeneficiary.isPending}>
            Save
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setIsEditing(false)}>
            Cancel
          </Button>
        </div>
      ) : (
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" onClick={() => setIsEditing(true)}>
            Edit
          </Button>
          <Button
            size="sm"
            variant="danger"
            isLoading={deleteBeneficiary.isPending}
            onClick={() => deleteBeneficiary.mutate(beneficiary.id)}
          >
            Remove
          </Button>
        </div>
      )}
    </li>
  );
}

export function BeneficiariesPage() {
  const { data: beneficiaries, isLoading, isError, error } = useBeneficiaries();
  const [isAdding, setIsAdding] = useState(false);

  if (isLoading) return <Spinner label="Loading beneficiaries" />;
  if (isError) return <ErrorBanner message={getApiErrorMessage(error)} />;

  return (
    <div className="flex flex-col gap-6">
      {isAdding ? (
        <AddBeneficiaryForm onDone={() => setIsAdding(false)} />
      ) : (
        <div>
          <Button onClick={() => setIsAdding(true)}>Add beneficiary</Button>
        </div>
      )}

      <Card>
        {!beneficiaries || beneficiaries.length === 0 ? (
          <EmptyState
            title="No saved beneficiaries"
            description="Add someone's account number to send money to them faster next time."
          />
        ) : (
          <ul className="divide-y divide-slate-100">
            {beneficiaries.map((b) => (
              <BeneficiaryRow key={b.id} beneficiary={b} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
