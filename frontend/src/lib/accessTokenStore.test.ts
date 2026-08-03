import { beforeEach, describe, expect, it } from "vitest";

import { accessTokenStore } from "./accessTokenStore";

describe("accessTokenStore", () => {
  beforeEach(() => {
    accessTokenStore.clear();
  });

  it("returns null when nothing has been set", () => {
    expect(accessTokenStore.get()).toBeNull();
  });

  it("returns the token that was set", () => {
    accessTokenStore.set("abc.def.ghi");
    expect(accessTokenStore.get()).toBe("abc.def.ghi");
  });

  it("overwrites a previously set token", () => {
    accessTokenStore.set("first-token");
    accessTokenStore.set("second-token");
    expect(accessTokenStore.get()).toBe("second-token");
  });

  it("clear() resets to null", () => {
    accessTokenStore.set("some-token");
    accessTokenStore.clear();
    expect(accessTokenStore.get()).toBeNull();
  });

  it("never touches localStorage or sessionStorage", () => {
    accessTokenStore.set("some-token");
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});
