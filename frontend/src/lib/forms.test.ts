import { describe, expect, it } from "vitest";
import type { Employee, Rotation } from "../api";
import {
  emptyEmployeeForm, emptyRotationForm, employeeToForm, formToEmployeeInput, formToRotationInput, rotationToForm,
  validateEmployeeForm, validateRotationForm,
} from "./forms";

const rotations: Rotation[] = [
  { id: 1, name: "Intake", active: true, weekdays: [0, 1, 2, 3, 4], max_trainees: 1, blocks: [{ name: "AM", start: "07:00", end: "11:00", headcount: 2 }] },
  { id: 2, name: "Packing", active: true, weekdays: [0, 1], max_trainees: 0, blocks: [{ name: "Day", start: "08:00", end: "16:00", headcount: 1 }] },
];

describe("employee form", () => {
  it("starts valid except for the name, with a level for every rotation", () => {
    const form = emptyEmployeeForm(rotations);
    expect(form.levels).toEqual({ 1: "none", 2: "none" });
    expect(validateEmployeeForm(form)).toEqual(["Name is required."]);
    expect(validateEmployeeForm({ ...form, name: "Ava" })).toEqual([]);
  });

  it("round-trips an existing employee", () => {
    const employee: Employee = {
      id: 7, active: true, name: "Ava", rank: "Lead", color: "#ff991f", max_hours_week: 40, target_hours_week: 36,
      rotations: [{ rotation_id: 1, level: "trainer" }, { rotation_id: 2, level: "training" }, { rotation_id: 99, level: "trained" }],
      availability: [{ weekday: 0, start: "06:00", end: "12:00" }], time_off: [{ date: "2026-11-04", kind: "preferred" }],
    };
    const form = employeeToForm(employee, rotations);
    expect(form.levels).toEqual({ 1: "trainer", 2: "training" }); // a link to an unknown rotation is dropped
    const input = formToEmployeeInput(form);
    expect(input.color).toBe("#FF991F");
    expect(input.rotations).toEqual([{ rotation_id: 1, level: "trainer" }, { rotation_id: 2, level: "training" }]);
    expect(input.availability).toEqual(employee.availability);
    expect(input.time_off).toEqual(employee.time_off);
    expect(input.max_hours_week).toBe(40);
  });

  it("omits rotations set to 'none'", () => {
    const form = { ...emptyEmployeeForm(rotations), name: "Ben", levels: { 1: "trained", 2: "none" } as const };
    expect(formToEmployeeInput(form).rotations).toEqual([{ rotation_id: 1, level: "trained" }]);
  });

  it("explains each problem", () => {
    const form = {
      ...emptyEmployeeForm(rotations), name: " ", color: "blue", maxHours: "0",
      availability: [{ weekday: 0, start: "9pm", end: "10:00" }, { weekday: 1, start: "12:00", end: "08:00" }],
      timeOff: [{ date: "2026-13-01", kind: "approved" as const }],
    };
    const errors = validateEmployeeForm(form);
    expect(errors).toContain("Name is required.");
    expect(errors).toContain("Color must be a hex code like #36B37E.");
    expect(errors).toContain("Maximum weekly hours must be between 1 and 168.");
    expect(errors).toContain("Availability row 1: times must look like 07:00.");
    expect(errors).toContain("Availability row 2: the end must be after the start.");
    expect(errors).toContain("Every time-off date must be a real date.");
  });

  it("checks target against maximum and rejects duplicate dates", () => {
    const base = { ...emptyEmployeeForm(rotations), name: "Cy" };
    expect(validateEmployeeForm({ ...base, maxHours: "20", targetHours: "30" })).toEqual(["Target weekly hours must be between 0 and the maximum."]);
    const twice = [{ date: "2026-11-04", kind: "approved" as const }, { date: "2026-11-04", kind: "preferred" as const }];
    expect(validateEmployeeForm({ ...base, timeOff: twice })).toEqual(["Each time-off date can only appear once."]);
  });
});

describe("rotation form", () => {
  it("has a valid default shape once named", () => {
    const form = emptyRotationForm();
    expect(validateRotationForm(form)).toEqual(["Name is required."]);
    expect(validateRotationForm({ ...form, name: "Intake" })).toEqual([]);
  });

  it("round-trips a rotation", () => {
    const input = formToRotationInput(rotationToForm(rotations[0]));
    expect(input).toEqual({ name: "Intake", weekdays: [0, 1, 2, 3, 4], max_trainees: 1, blocks: [{ name: "AM", start: "07:00", end: "11:00", headcount: 2 }] });
  });

  it("catches overlapping blocks, duplicate names, bad times and counts", () => {
    const form = {
      ...emptyRotationForm(), name: "X",
      blocks: [
        { name: "A", start: "07:00", end: "11:00", headcount: "1" },
        { name: "B", start: "10:00", end: "12:00", headcount: "0" },
        { name: "A", start: "7pm", end: "20:00", headcount: "1" },
      ],
    };
    const errors = validateRotationForm(form);
    expect(errors).toContain("A and B overlap.");
    expect(errors).toContain("Block names must be different from each other.");
    expect(errors).toContain("A: times must look like 07:00.");
    expect(errors).toContain("B: people needed must be a whole number from 1 to 50.");
  });

  it("requires weekdays and at least one block", () => {
    const errors = validateRotationForm({ ...emptyRotationForm(), name: "X", weekdays: [], blocks: [] });
    expect(errors).toContain("Pick at least one weekday.");
    expect(errors).toContain("Add at least one block.");
  });

  it("touching blocks are fine and weekdays come out sorted", () => {
    const form = { ...emptyRotationForm(), name: "X", weekdays: [4, 0, 2] };
    expect(validateRotationForm(form)).toEqual([]);
    expect(formToRotationInput(form).weekdays).toEqual([0, 2, 4]);
  });
});
