import { describe, expect, it } from "vitest";

import { formatAccountNumber, formatMoney, statusTone } from "@/lib/format";

describe("formatMoney", () => {
  it("formats a known currency with symbol", () => {
    expect(formatMoney("150.00", "USD")).toBe("$150.00");
  });

  it("accepts numeric input as well as strings", () => {
    expect(formatMoney(42.5, "USD")).toBe("$42.50");
  });

  it("falls back to a plain numeric format for a malformed currency code", () => {
    expect(formatMoney("10.00", "AB")).toBe("10.00 AB");
  });
});

describe("formatAccountNumber", () => {
  it("groups digits into blocks of four", () => {
    expect(formatAccountNumber("AZ00BANK123456789012")).toBe("AZ00 BANK 1234 5678 9012");
  });
});

describe("statusTone", () => {
  it("maps ACTIVE and SUCCESS to success", () => {
    expect(statusTone("ACTIVE")).toBe("success");
    expect(statusTone("SUCCESS")).toBe("success");
  });

  it("maps PENDING to warning", () => {
    expect(statusTone("PENDING")).toBe("warning");
  });

  it("maps BLOCKED, FAILED, CLOSED, EXPIRED to danger", () => {
    expect(statusTone("BLOCKED")).toBe("danger");
    expect(statusTone("FAILED")).toBe("danger");
    expect(statusTone("CLOSED")).toBe("danger");
    expect(statusTone("EXPIRED")).toBe("danger");
  });

  it("falls back to neutral for unrecognized statuses", () => {
    expect(statusTone("REVERSED")).toBe("neutral");
  });
});
