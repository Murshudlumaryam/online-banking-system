import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import QRCode from "qrcode";

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

function TwoFactorEnrollment({ onEnabled }: { onEnabled: () => void }) {
  const [secret, setSecret] = useState<string | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);

  async function startSetup() {
    setError(null);
    setIsStarting(true);
    try {
      const result = await authService.setupTwoFactor();
      setSecret(result.secret);
      // Generated entirely in the browser — the provisioning URI (which
      // embeds the TOTP secret) is never sent to any third-party QR
      // rendering service, unlike a common shortcut of pointing an <img>
      // at a public "QR code as a service" API.
      const dataUrl = await QRCode.toDataURL(result.provisioning_uri, { width: 220, margin: 1 });
      setQrDataUrl(dataUrl);
    } catch (err) {
      setError(getApiErrorMessage(err, "Couldn't start 2FA setup."));
    } finally {
      setIsStarting(false);
    }
  }

  async function handleConfirm(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsConfirming(true);
    try {
      await authService.enableTwoFactor(code);
      onEnabled();
    } catch (err) {
      setError(getApiErrorMessage(err, "That code didn't match. Check your authenticator app and try again."));
    } finally {
      setIsConfirming(false);
    }
  }

  if (!secret) {
    return (
      <div className="mt-4">
        {error && <ErrorBanner message={error} />}
        <p className="text-sm text-slate-500">
          Add an extra step at login using an authenticator app (Google Authenticator, Authy, or similar).
        </p>
        <Button className="mt-3" onClick={startSetup} isLoading={isStarting}>
          Set up two-factor authentication
        </Button>
      </div>
    );
  }

  return (
    <form className="mt-4 flex flex-col gap-4" onSubmit={handleConfirm} noValidate>
      {error && <ErrorBanner message={error} />}
      <p className="text-sm text-slate-500">
        Scan this code with your authenticator app, then enter the 6-digit code it shows to confirm.
      </p>
      {qrDataUrl && (
        <img
          src={qrDataUrl}
          alt="Scan this QR code with your authenticator app"
          className="h-[220px] w-[220px] rounded-md border border-slate-200"
        />
      )}
      <div>
        <p className="text-xs font-medium text-slate-500">Can't scan it? Enter this key manually:</p>
        <p className="mt-1 select-all break-all rounded-md bg-slate-50 px-3 py-2 font-mono text-xs text-ink">
          {secret}
        </p>
      </div>
      <Input
        label="6-digit code"
        required
        inputMode="numeric"
        pattern="\d{6}"
        maxLength={6}
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
      />
      <div>
        <Button type="submit" isLoading={isConfirming}>
          Confirm and enable
        </Button>
      </div>
    </form>
  );
}

function TwoFactorDisable({ onDisabled }: { onDisabled: () => void }) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await authService.disableTwoFactor(password, code);
      onDisabled();
    } catch (err) {
      setError(getApiErrorMessage(err, "Couldn't disable two-factor authentication."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="mt-4 flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
      {error && <ErrorBanner message={error} />}
      <p className="text-sm font-medium text-forest-600">Two-factor authentication is on.</p>
      <p className="text-sm text-slate-500">
        Confirm your password and a current code from your authenticator app to turn it off.
      </p>
      <Input
        label="Password"
        type="password"
        autoComplete="current-password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <Input
        label="6-digit code"
        required
        inputMode="numeric"
        pattern="\d{6}"
        maxLength={6}
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
      />
      <div>
        <Button type="submit" variant="danger" isLoading={isSubmitting}>
          Disable two-factor authentication
        </Button>
      </div>
    </form>
  );
}

function TwoFactorSection() {
  const { data: profile, isLoading, refetch } = useMyProfile();

  if (isLoading || !profile) return null;

  return (
    <Card className="mt-6 p-6">
      <h3 className="font-display text-lg text-ink">Two-factor authentication</h3>
      {profile.totp_enabled ? (
        <TwoFactorDisable onDisabled={() => void refetch()} />
      ) : (
        <TwoFactorEnrollment onEnabled={() => void refetch()} />
      )}
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
      <TwoFactorSection />
      <ChangePasswordForm />
    </div>
  );
}
