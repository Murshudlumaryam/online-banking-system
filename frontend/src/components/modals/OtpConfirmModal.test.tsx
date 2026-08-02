import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OtpConfirmModal } from "@/components/modals/OtpConfirmModal";

describe("OtpConfirmModal", () => {
  it("disables the confirm button until a 6-digit code is entered", () => {
    render(
      <OtpConfirmModal
        referenceNumber="TXN-ABC123"
        expiresInSeconds={300}
        isSubmitting={false}
        errorMessage={null}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    const confirmButton = screen.getByRole("button", { name: /confirm transfer/i });
    expect(confirmButton).toBeDisabled();

    const input = screen.getByLabelText(/one-time code/i);
    fireEvent.change(input, { target: { value: "123" } });
    expect(confirmButton).toBeDisabled();

    fireEvent.change(input, { target: { value: "123456" } });
    expect(confirmButton).not.toBeDisabled();
  });

  it("strips non-digit characters from the code input", () => {
    render(
      <OtpConfirmModal
        referenceNumber="TXN-ABC123"
        expiresInSeconds={300}
        isSubmitting={false}
        errorMessage={null}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    const input = screen.getByLabelText(/one-time code/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "12a3-45!6789" } });
    expect(input.value).toBe("123456");
  });

  it("calls onConfirm with the entered code on submit", () => {
    const handleConfirm = vi.fn();
    render(
      <OtpConfirmModal
        referenceNumber="TXN-ABC123"
        expiresInSeconds={300}
        isSubmitting={false}
        errorMessage={null}
        onConfirm={handleConfirm}
        onCancel={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText(/one-time code/i), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: /confirm transfer/i }));
    expect(handleConfirm).toHaveBeenCalledWith("654321");
  });

  it("shows an error message when provided", () => {
    render(
      <OtpConfirmModal
        referenceNumber="TXN-ABC123"
        expiresInSeconds={300}
        isSubmitting={false}
        errorMessage="The OTP code is incorrect (3 attempt(s) remaining)"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(/3 attempt/);
  });

  it("calls onCancel when the cancel button is clicked", () => {
    const handleCancel = vi.fn();
    render(
      <OtpConfirmModal
        referenceNumber="TXN-ABC123"
        expiresInSeconds={300}
        isSubmitting={false}
        errorMessage={null}
        onConfirm={vi.fn()}
        onCancel={handleCancel}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(handleCancel).toHaveBeenCalled();
  });
});
