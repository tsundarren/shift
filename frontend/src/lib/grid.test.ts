import { describe, expect, it } from "vitest";
import type { SlotView } from "../api";
import { buildGrid } from "./grid";

function slot(rotation_id: number, name: string, block: string, start: string, day: number): SlotView {
  return {
    id: `r${rotation_id}:${day}:${block}`, rotation_id, rotation_name: name, block, day, date: `2026-11-0${2 + day}`, weekday: "Mon",
    start, end: "12:00", headcount: 1, max_trainees: 1, assignments: [], workers: 0, short: 1,
  };
}

describe("schedule grid", () => {
  const slots = [
    slot(2, "Packing", "PM", "11:00", 1), slot(1, "Intake", "PM", "11:00", 0), slot(1, "Intake", "AM", "07:00", 0),
    slot(1, "Intake", "AM", "07:00", 1), slot(2, "Packing", "AM", "07:00", 0),
  ];
  const grid = buildGrid(slots);

  it("has one column per day, in order", () => {
    expect(grid.days.map((d) => d.day)).toEqual([0, 1]);
  });

  it("has one row per rotation and block, ordered by rotation then time", () => {
    expect(grid.rows.map((r) => `${r.rotationName} ${r.block}`)).toEqual(["Intake AM", "Intake PM", "Packing AM", "Packing PM"]);
  });

  it("puts each slot in the right cell and leaves gaps for days a rotation doesn't run", () => {
    const intakeAm = grid.rows[0];
    expect(intakeAm.cells[0].id).toBe("r1:0:AM");
    expect(intakeAm.cells[1].id).toBe("r1:1:AM");
    const intakePm = grid.rows[1];
    expect(intakePm.cells[0].id).toBe("r1:0:PM");
    expect(intakePm.cells[1]).toBeUndefined();
  });

  it("copes with nothing", () => {
    expect(buildGrid([])).toEqual({ days: [], rows: [] });
  });
});
