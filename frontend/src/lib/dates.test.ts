import { describe, expect, it } from "vitest";
import { isIsoDate, nextMonday, shortDate } from "./dates";

describe("dates", () => {
  it("checks real calendar dates", () => {
    expect(isIsoDate("2026-11-02")).toBe(true);
    expect(isIsoDate("2028-02-29")).toBe(true);
    for (const bad of ["2026-02-30", "2026-13-01", "11/02/2026", "2026-1-2", "", "2027-02-29"]) expect(isIsoDate(bad)).toBe(false);
  });

  it("finds the next Monday strictly after today", () => {
    expect(nextMonday(new Date(2026, 9, 28))).toBe("2026-11-02"); // Wednesday
    expect(nextMonday(new Date(2026, 10, 2))).toBe("2026-11-09"); // a Monday goes to the following one
    expect(nextMonday(new Date(2026, 10, 1))).toBe("2026-11-02"); // Sunday
    expect(nextMonday(new Date(2026, 10, 7))).toBe("2026-11-09"); // Saturday
    expect(nextMonday(new Date(2026, 11, 30))).toBe("2027-01-04"); // across a year boundary
  });

  it("formats short dates without shifting the day", () => {
    expect(shortDate("2026-11-02")).toBe("Nov 2");
    expect(shortDate("2026-12-31")).toBe("Dec 31");
  });
});
