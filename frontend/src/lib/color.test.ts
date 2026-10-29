import { describe, expect, it } from "vitest";
import { contrastRatio, isHexColor, normalizeHex, textColorFor } from "./color";

describe("hex colors", () => {
  it("accepts only #RRGGBB", () => {
    expect(isHexColor("#36B37E")).toBe(true);
    expect(isHexColor("#36b37e")).toBe(true);
    for (const bad of ["36B37E", "#36B37", "#GGGGGG", "blue", "", "#36B37E0"]) expect(isHexColor(bad)).toBe(false);
  });

  it("normalizes friendly input", () => {
    expect(normalizeHex("36b37e")).toBe("#36B37E");
    expect(normalizeHex("  #36b37e ")).toBe("#36B37E");
    expect(normalizeHex("#3b7")).toBe("#33BB77");
    expect(normalizeHex("blue")).toBeNull();
    expect(normalizeHex("#12345")).toBeNull();
  });
});

describe("readable text on a colored chip", () => {
  it("uses dark text on light colors and white on dark ones", () => {
    expect(textColorFor("#FFFFFF")).toBe("#111111");
    expect(textColorFor("#FFE380")).toBe("#111111");
    expect(textColorFor("#36B37E")).toBe("#111111");
    expect(textColorFor("#000000")).toBe("#FFFFFF");
    expect(textColorFor("#6554C0")).toBe("#FFFFFF");
    expect(textColorFor("#172B4D")).toBe("#FFFFFF");
  });

  it("falls back to dark text for junk input", () => {
    expect(textColorFor("nonsense")).toBe("#111111");
  });

  it("has a sane contrast scale", () => {
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 0);
    expect(contrastRatio("#777777", "#777777")).toBeCloseTo(1, 5);
  });
});
