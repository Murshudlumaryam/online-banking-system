import { describe, expect, it } from "vitest";

import { tokenStorage } from "@/lib/tokenStorage";

describe("tokenStorage", () => {
  it("returns null when no tokens are stored", () => {
    expect(tokenStorage.getAccessToken()).toBeNull();
    expect(tokenStorage.getRefreshToken()).toBeNull();
  });

  it("persists and retrieves both tokens", () => {
    tokenStorage.setTokens("access-123", "refresh-456");
    expect(tokenStorage.getAccessToken()).toBe("access-123");
    expect(tokenStorage.getRefreshToken()).toBe("refresh-456");
  });

  it("clears both tokens", () => {
    tokenStorage.setTokens("access-123", "refresh-456");
    tokenStorage.clear();
    expect(tokenStorage.getAccessToken()).toBeNull();
    expect(tokenStorage.getRefreshToken()).toBeNull();
  });
});
