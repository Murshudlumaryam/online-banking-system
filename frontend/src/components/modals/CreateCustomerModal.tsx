import { useState } from "react";
import type { FormEvent } from "react";

import type { AdminCreateCustomerPayload } from "@/services/adminService";
import { Button } from "@/components/ui/Button";
import { ErrorBanner } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";

interface CreateCustomerModalProps {
  isSubmitting: boolean;
  errorMessage: string | null;
  onSubmit: (payload: AdminCreateCustomerPayload) => void;
  onCancel: () => void;
}

const initialForm = {
  email: "",
  temporary_password: "",
  first_name: "",
  last_name: "",
  date_of_birth: "",
  phone_number: "",
  address: "",
  national_id: "",
};

export function CreateCustomerModal({
  isSubmitting,
  errorMessage,
  onSubmit,
  onCancel,
}: CreateCustomerModalProps) {
  const [form, setForm] = useState(initialForm);

  function updateField<K extends keyof typeof initialForm>(field: K, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onSubmit({ ...form, address: form.address || undefined });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 px-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg">
        <h2 className="font-display text-lg text-ink">Open an account for a customer</h2>
        <p className="mt-1 text-sm text-slate-500">
          For a walk-in customer who can&apos;t self-register. Give them the temporary password
          directly — it&apos;s never shown again after this.
        </p>

        <form className="mt-5 flex max-h-[60vh] flex-col gap-4 overflow-y-auto pr-1" onSubmit={handleSubmit}>
          {errorMessage && <ErrorBanner message={errorMessage} />}
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="First name"
              required
              value={form.first_name}
              onChange={(e) => updateField("first_name", e.target.value)}
            />
            <Input
              label="Last name"
              required
              value={form.last_name}
              onChange={(e) => updateField("last_name", e.target.value)}
            />
          </div>
          <Input
            label="Email"
            type="email"
            required
            value={form.email}
            onChange={(e) => updateField("email", e.target.value)}
          />
          <Input
            label="Temporary password"
            type="text"
            required
            hint="At least 8 characters. Hand this to the customer in person or by phone."
            value={form.temporary_password}
            onChange={(e) => updateField("temporary_password", e.target.value)}
          />
          <Input
            label="Date of birth"
            type="date"
            required
            value={form.date_of_birth}
            onChange={(e) => updateField("date_of_birth", e.target.value)}
          />
          <Input
            label="Phone number"
            required
            placeholder="+994501234567"
            value={form.phone_number}
            onChange={(e) => updateField("phone_number", e.target.value)}
          />
          <Input
            label="National ID"
            required
            value={form.national_id}
            onChange={(e) => updateField("national_id", e.target.value)}
          />
          <Input
            label="Address (optional)"
            value={form.address}
            onChange={(e) => updateField("address", e.target.value)}
          />

          <div className="flex gap-3 pt-2">
            <Button type="submit" isLoading={isSubmitting}>
              Create customer
            </Button>
            <Button type="button" variant="ghost" onClick={onCancel} disabled={isSubmitting}>
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
