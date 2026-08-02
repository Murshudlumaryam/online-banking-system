import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { useMyProfile, useUpdateProfile } from "@/hooks/useCustomerProfile";
import { getApiErrorMessage } from "@/lib/apiClient";
import { formatDate } from "@/lib/format";
import { authService } from "@/services/authService";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card, ErrorBanner, Spinner } from "@/components/ui/Feedback";

function ProfileForm() {
  const { data: profile, isLoading } = useMyProfile();
  const updateProfile = useUpdateProfile();

  const [phoneNumber, setPhoneNumber] = useState("");
  const [address, setAddress] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  useEffect(() => {
    if (profile) {
      setPhoneNumber(profile.phone_number);
      setAddress(profile.address ?? "");
    }
  }, [profile]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSavedMessage(null);
    try {
      await updateProfile.mutateAsync({ phone_number: phoneNumber, address });
      setSavedMessage("Profile updated.");
    } catch (err) {
      setError(getApiErrorMessage(err, "Couldn't save your profile."));
    }
  }

  if (isLoading) return <Spinner label="Loading profile" />;
  if (!profile) return null;

  return (
    <Card className="p-6">
      <h3 className="font-display text-lg text-ink">Your details</h3>
      <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
        <div>
          <dt className="text-slate-500">Customer number</dt>
          <dd className="font-mono text-ink">{profile.customer_number}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Name</dt>
          <dd className="text-ink">
            {profile.first_name} {profile.last_name}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Date of birth</dt>
          <dd className="text-ink">{formatDate(profile.date_of_birth)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Status</dt>
          <dd className="text-ink">{profile.status}</dd>
        </div>
      </dl>

      <form className="mt-6 flex flex-col gap-4 border-t border-slate-100 pt-6" onSubmit={handleSubmit}>
        {error && <ErrorBanner message={error} />}
        {savedMessage && (
          <p className="rounded-md bg-forest-500/5 px-3 py-2 text-sm text-forest-600">{savedMessage}</p>
        )}
        <Input
          label="Phone number"
          value={phoneNumber}
          onChange={(e) => setPhoneNumber(e.target.value)}
        />
        <Input label="Address" value={address} onChange={(e) => setAddress(e.target.value)} />
        <div>
          <Button type="submit" isLoading={updateProfile.isPending}>
            Save changes
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ChangePasswordForm() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSavedMessage(null);
    setIsSubmitting(true);
    try {
      await authService.changePassword(currentPassword, newPassword);
      setSavedMessage("Password changed. You'll need it next time you sign in.");
      setCurrentPassword("");
      setNewPassword("");
    } catch (err) {
      setError(getApiErrorMessage(err, "Couldn't change your password."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Card className="mt-6 p-6">
      <h3 className="font-display text-lg text-ink">Change password</h3>
      <form className="mt-4 flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
        {error && <ErrorBanner message={error} />}
        {savedMessage && (
          <p className="rounded-md bg-forest-500/5 px-3 py-2 text-sm text-forest-600">{savedMessage}</p>
        )}
        <Input
          label="Current password"
          type="password"
          autoComplete="current-password"
          required
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
        />
        <Input
          label="New password"
          type="password"
          autoComplete="new-password"
          required
          hint="At least 8 characters, one uppercase letter, one digit."
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
        />
        <div>
          <Button type="submit" isLoading={isSubmitting}>
            Update password
          </Button>
        </div>
      </form>
    </Card>
  );
}

export function ProfilePage() {
  return (
    <div className="max-w-xl">
      <ProfileForm />
      <ChangePasswordForm />
    </div>
  );
}
