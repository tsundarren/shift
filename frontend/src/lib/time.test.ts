import { describe, expect, it } from "vitest";
import { isHHMM, toMinutes } from "./time";

describe("times", () => {
  it("parses valid times", () => {
    expect(toMinutes("07:30")).toBe(450);
    expect(toMinutes("7:05")).toBe(425);
    expect(toMinutes("00:00")).toBe(0);
    expect(toMinutes("24:00")).toBe(1440);
    expect(toMinutes(" 11:00 ")).toBe(660);
  });

  it("rejects everything else", () => {
    for (const bad of ["25:00", "07:60", "24:30", "0730", "7pm", "", "ab:cd", "7:5"]) expect(isHHMM(bad)).toBe(false);
  });
});
