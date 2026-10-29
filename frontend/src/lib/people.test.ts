import { describe, expect, it } from "vitest";
import type { SlotAssignment } from "../api";
import { describeAssignment, initials, levelLabel, rotationSummary, summarizeAvailability, summarizeWeekdays } from "./people";

const base: SlotAssignment = { employee_id: 1, name: "John Smith", rank: "Associate", color: "#4C9AFF", role: "worker", trainer_id: null, trainer_name: null };

describe("assignments", () => {
  it("shows who trained a trainee", () => {
    expect(describeAssignment(base)).toBe("John Smith");
    expect(describeAssignment({ ...base, role: "trainee", trainer_id: 2, trainer_name: "Jane" })).toBe("John Smith (trained by Jane)");
    expect(describeAssignment({ ...base, role: "trainee" })).toBe("John Smith (trainee)");
  });

  it("makes initials", () => {
    expect(initials("John Smith")).toBe("JS");
    expect(initials("Cher")).toBe("CH");
    expect(initials("  ana maria  de la cruz ")).toBe("AC");
    expect(initials("")).toBe("?");
  });

  it("labels levels", () => {
    expect(levelLabel("none")).toBe("Not trained");
    expect(levelLabel("training")).toBe("Learning");
    expect(levelLabel("trainer")).toBe("Trainer");
  });
});

describe("availability summary", () => {
  const w = (weekday: number, start = "06:00", end = "16:00") => ({ weekday, start, end });

  it("compresses runs of days", () => {
    expect(summarizeAvailability([0, 1, 2, 3, 4].map((d) => w(d)))).toBe("Mon-Fri 06:00-16:00");
    expect(summarizeAvailability([w(0), w(2), w(4)])).toBe("Mon, Wed, Fri 06:00-16:00");
    expect(summarizeAvailability([w(0), w(1)])).toBe("Mon, Tue 06:00-16:00");
    expect(summarizeAvailability([w(0), w(1), w(2), w(4)])).toBe("Mon-Wed, Fri 06:00-16:00");
  });

  it("groups different hours separately", () => {
    expect(summarizeAvailability([w(0), w(1), w(2), w(5, "08:00", "12:00")])).toBe("Mon-Wed 06:00-16:00; Sat 08:00-12:00");
  });

  it("handles nothing", () => {
    expect(summarizeAvailability([])).toBe("No availability set");
  });
});

describe("summaries for cards and lists", () => {
  it("lists weekdays compactly", () => {
    expect(summarizeWeekdays([4, 0, 1, 2, 3])).toBe("Mon-Fri");
    expect(summarizeWeekdays([0, 2])).toBe("Mon, Wed");
    expect(summarizeWeekdays([5, 6])).toBe("Sat, Sun");
  });

  it("summarizes an employee's rotations and ignores archived ones", () => {
    const rotations = [{ id: 1, name: "Intake" }, { id: 2, name: "Packing" }, { id: 3, name: "Sorting" }];
    const links = [{ rotation_id: 3, level: "training" as const }, { rotation_id: 1, level: "trained" as const }, { rotation_id: 2, level: "trainer" as const }, { rotation_id: 9, level: "trained" as const }];
    expect(rotationSummary(links, rotations)).toBe("Intake, Packing (trainer), Sorting (learning)");
    expect(rotationSummary([], rotations)).toBe("No rotations yet");
  });
});
