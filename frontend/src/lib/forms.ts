import type { AvailabilityWindow, Block, Employee, EmployeeInput, Level, Rotation, RotationInput, TimeOffKind } from "../api";
import { isHexColor, normalizeHex } from "./color";
import { isIsoDate } from "./dates";
import { toMinutes } from "./time";

// ---------------- employees ----------------

export interface EmployeeForm {
  name: string; rank: string; color: string; maxHours: string; targetHours: string;
  levels: Record<number, Level | "none">; // one entry per active rotation
  availability: AvailabilityWindow[];
  timeOff: { date: string; kind: TimeOffKind }[];
}

export function emptyEmployeeForm(rotations: Rotation[]): EmployeeForm {
  return {
    name: "", rank: "", color: "#4C9AFF", maxHours: "40", targetHours: "32",
    levels: Object.fromEntries(rotations.map((r) => [r.id, "none"])) as EmployeeForm["levels"],
    availability: [0, 1, 2, 3, 4].map((weekday) => ({ weekday, start: "07:00", end: "15:00" })),
    timeOff: [],
  };
}

export function employeeToForm(e: Employee, rotations: Rotation[]): EmployeeForm {
  const levels = Object.fromEntries(rotations.map((r) => [r.id, "none"])) as EmployeeForm["levels"];
  for (const link of e.rotations) if (link.rotation_id in levels) levels[link.rotation_id] = link.level;
  return {
    name: e.name, rank: e.rank, color: e.color, maxHours: String(e.max_hours_week), targetHours: String(e.target_hours_week),
    levels, availability: e.availability.map((w) => ({ ...w })), timeOff: e.time_off.map((t) => ({ ...t })),
  };
}

export function validateEmployeeForm(f: EmployeeForm): string[] {
  const errors: string[] = [];
  if (!f.name.trim()) errors.push("Name is required.");
  if (!isHexColor(normalizeHex(f.color) ?? "")) errors.push("Color must be a hex code like #36B37E.");
  const max = Number(f.maxHours);
  const target = Number(f.targetHours);
  if (!(max > 0) || max > 168) errors.push("Maximum weekly hours must be between 1 and 168.");
  else if (!(target >= 0) || target > max) errors.push("Target weekly hours must be between 0 and the maximum.");
  f.availability.forEach((w, i) => {
    const start = toMinutes(w.start);
    const end = toMinutes(w.end);
    if (start === null || end === null) errors.push(`Availability row ${i + 1}: times must look like 07:00.`);
    else if (start >= end) errors.push(`Availability row ${i + 1}: the end must be after the start.`);
  });
  const dates = f.timeOff.map((t) => t.date);
  if (dates.some((d) => !isIsoDate(d))) errors.push("Every time-off date must be a real date.");
  else if (new Set(dates).size !== dates.length) errors.push("Each time-off date can only appear once.");
  return errors;
}

export function formToEmployeeInput(f: EmployeeForm): EmployeeInput {
  return {
    name: f.name.trim(), rank: f.rank.trim(), color: normalizeHex(f.color) ?? f.color,
    max_hours_week: Number(f.maxHours), target_hours_week: Number(f.targetHours),
    rotations: Object.entries(f.levels).filter(([, level]) => level !== "none").map(([id, level]) => ({ rotation_id: Number(id), level: level as Level })),
    availability: f.availability.map((w) => ({ weekday: w.weekday, start: w.start.trim(), end: w.end.trim() })),
    time_off: f.timeOff.map((t) => ({ date: t.date, kind: t.kind })),
  };
}

// ---------------- rotations ----------------

export interface RotationForm {
  name: string; weekdays: number[]; maxTrainees: string;
  blocks: { name: string; start: string; end: string; headcount: string }[];
}

export function emptyRotationForm(): RotationForm {
  return {
    name: "", weekdays: [0, 1, 2, 3, 4], maxTrainees: "1",
    blocks: [{ name: "AM", start: "07:00", end: "11:00", headcount: "1" }, { name: "PM", start: "11:00", end: "15:00", headcount: "1" }],
  };
}

export function rotationToForm(r: Rotation): RotationForm {
  return {
    name: r.name, weekdays: [...r.weekdays], maxTrainees: String(r.max_trainees),
    blocks: r.blocks.map((b: Block) => ({ name: b.name, start: b.start, end: b.end, headcount: String(b.headcount) })),
  };
}

export function validateRotationForm(f: RotationForm): string[] {
  const errors: string[] = [];
  if (!f.name.trim()) errors.push("Name is required.");
  if (f.weekdays.length === 0) errors.push("Pick at least one weekday.");
  const trainees = Number(f.maxTrainees);
  if (!Number.isInteger(trainees) || trainees < 0 || trainees > 10) errors.push("Trainees per block must be a whole number from 0 to 10.");
  if (f.blocks.length === 0) errors.push("Add at least one block.");

  const spans: { name: string; start: number; end: number }[] = [];
  f.blocks.forEach((b, i) => {
    const label = b.name.trim() || `block ${i + 1}`;
    const start = toMinutes(b.start);
    const end = toMinutes(b.end);
    const headcount = Number(b.headcount);
    if (!b.name.trim()) errors.push(`Block ${i + 1} needs a name.`);
    if (start === null || end === null) errors.push(`${label}: times must look like 07:00.`);
    else if (start >= end) errors.push(`${label}: the end must be after the start.`);
    else spans.push({ name: label, start, end });
    if (!Number.isInteger(headcount) || headcount < 1 || headcount > 50) errors.push(`${label}: people needed must be a whole number from 1 to 50.`);
  });
  const names = f.blocks.map((b) => b.name.trim()).filter(Boolean);
  if (new Set(names).size !== names.length) errors.push("Block names must be different from each other.");
  spans.sort((a, b) => a.start - b.start);
  for (let i = 1; i < spans.length; i++) {
    if (spans[i].start < spans[i - 1].end) errors.push(`${spans[i - 1].name} and ${spans[i].name} overlap.`);
  }
  return errors;
}

export function formToRotationInput(f: RotationForm): RotationInput {
  return {
    name: f.name.trim(), weekdays: [...f.weekdays].sort((a, b) => a - b), max_trainees: Number(f.maxTrainees),
    blocks: f.blocks.map((b) => ({ name: b.name.trim(), start: b.start.trim(), end: b.end.trim(), headcount: Number(b.headcount) })),
  };
}
