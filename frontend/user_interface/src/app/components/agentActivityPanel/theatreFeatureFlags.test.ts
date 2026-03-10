import { describe, expect, it } from "vitest";
import { resolveStagedTheatreEnabled } from "./theatreFeatureFlags";

describe("resolveStagedTheatreEnabled", () => {
  it("enables by default", () => {
    expect(resolveStagedTheatreEnabled(undefined)).toBe(true);
  });

  it("disables only when explicitly false", () => {
    expect(resolveStagedTheatreEnabled("false")).toBe(false);
    expect(resolveStagedTheatreEnabled("FALSE")).toBe(false);
  });

  it("treats other values as enabled", () => {
    expect(resolveStagedTheatreEnabled("0")).toBe(true);
    expect(resolveStagedTheatreEnabled("true")).toBe(true);
    expect(resolveStagedTheatreEnabled("canary")).toBe(true);
  });
});

