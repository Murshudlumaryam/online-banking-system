import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { useAuth } from "@/context/AuthContext";
import { getApiErrorMessage } from "@/lib/apiClient";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ErrorBanner } from "@/components/ui/Feedback";

const initialForm = {
  firstName: "",
  lastName: "",
  email: "",
  password: "",
  dateOfBirth: "",
  phoneNumber: "",
  address: "",
};

function validatePassword(password: string): string | null {
  if (password.length < 8) return "Password must be at least 8 characters.";
  if (!/[A-Z]/.test(password)) return "Password must contain at least one uppercase letter.";
  if (!/\d/.test(password)) return "Password must contain at least one digit.";
  return null;
}

export function RegisterPage() {
  const { register, login } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState(initialForm);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function updateField<K extends keyof typeof initialForm>(field: K, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    const passwordError = validatePassword(form.password);
    if (passwordError) {
      setError(passwordError);
      return;
    }

    setIsSubmitting(true);
    try {
      await register({
        email: form.email,
        password: form.password,
        first_name: form.firstName,
        last_name: form.lastName,
        date_of_birth: form.dateOfBirth,
        phone_number: form.phoneNumber,
        address: form.address || undefined,
      });
      await login(form.email, form.password);
      navigate("/app/dashboard", { replace: true });
    } catch (err) {
      setError(getApiErrorMessage(err, "Couldn't complete registration. Please check your details."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout title="Open your account" subtitle="Takes about a minute">
      <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
        {error && <ErrorBanner message={error} />}
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="First name"
            required
            value={form.firstName}
            onChange={(e) => updateField("firstName", e.target.value)}
          />
          <Input
            label="Last name"
            required
            value={form.lastName}
            onChange={(e) => updateField("lastName", e.target.value)}
          />
        </div>
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={form.email}
          onChange={(e) => updateField("email", e.target.value)}
        />
        <Input
          label="Password"
          type="password"
          autoComplete="new-password"
          required
          hint="At least 8 characters, one uppercase letter, one digit."
          value={form.password}
          onChange={(e) => updateField("password", e.target.value)}
        />
        <Input
          label="Date of birth"
          type="date"
          required
          value={form.dateOfBirth}
          onChange={(e) => updateField("dateOfBirth", e.target.value)}
        />
        <Input
          label="Phone number"
          type="tel"
          required
          placeholder="+994501234567"
          value={form.phoneNumber}
          onChange={(e) => updateField("phoneNumber", e.target.value)}
        />
        <Input
          label="Address (optional)"
          value={form.address}
          onChange={(e) => updateField("address", e.target.value)}
        />
        <Button type="submit" isLoading={isSubmitting} className="w-full">
          Create account
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-500">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-ledger-700 hover:underline">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
