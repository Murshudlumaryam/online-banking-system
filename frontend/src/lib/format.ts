export function formatMoney(amount: string | number, currency: string): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      currencyDisplay: "narrowSymbol",
    }).format(value);
  } catch {
    // Unknown/synthetic currency code â€” fall back to a plain numeric format.
    return `${value.toFixed(2)} ${currency}`;
  }
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { dateStyle: "medium" });
}

/** Breaks a long account/card number into groups of 4 for readability. */
export function formatAccountNumber(value: string): string {
  return value.replace(/(.{4})/g, "$1 ").trim();
}

export function statusTone(status: string): "success" | "warning" | "danger" | "neutral" {
  switch (status) {
    case "ACTIVE":
    case "SUCCESS":
      return "success";
    case "PENDING":
      return "warning";
    case "BLOCKED":
    case "FAILED":
    case "CLOSED":
    case "EXPIRED":
      return "danger";
    default:
      return "neutral";
  }
}
