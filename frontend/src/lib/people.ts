import type { AvailabilityWindow, Level, RotationLink, SlotAssignment } from "../api";
import { WEEKDAYS_SHORT } from "./time";

export function levelLabel(level: Level | "none"): string {
  return { none: "Not trained", training: "Learning", trained: "Trained", trainer: "Trainer" }[level];
}

/** "Ava", or "John (trained by Jane)" for a trainee. */
export function describeAssignment(a: SlotAssignment): string {
  if (a.role === "trainee") return a.trainer_name ? `${a.name} (trained by ${a.trainer_name})` : `${a.name} (trainee)`;
  return a.name;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts.length === 1 ? parts[0].slice(0, 2) : parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function summarizeWeekdays(days: number[]): string {
  const sorted = [...new Set(days)].sort((a, b) => a - b);
  const runs: number[][] = [];
  for (const d of sorted) {
    const last = runs[runs.length - 1];
    if (last && d === last[last.length - 1] + 1) last.push(d);
    else runs.push([d]);
  }
  return runs
    .map((run) => (run.length >= 3 ? `${WEEKDAYS_SHORT[run[0]]}-${WEEKDAYS_SHORT[run[run.length - 1]]}` : run.map((d) => WEEKDAYS_SHORT[d]).join(", ")))
    .join(", ");
}

/** "Mon-Fri 06:00-16:00; Sat 08:00-12:00" */
export function summarizeAvailability(windows: AvailabilityWindow[]): string {
  if (windows.length === 0) return "No availability set";
  const groups = new Map<string, number[]>();
  for (const w of windows) {
    const key = `${w.start}-${w.end}`;
    groups.set(key, [...(groups.get(key) ?? []), w.weekday]);
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([range, days]) => `${summarizeWeekdays(days)} ${range}`).join("; ");
}

/** "Intake, Packing (trainer), Sorting (learning)" */
export function rotationSummary(links: RotationLink[], rotations: { id: number; name: string }[]): string {
  const names = new Map(rotations.map((r) => [r.id, r.name]));
  const parts = links
    .filter((l) => names.has(l.rotation_id))
    .sort((a, b) => a.rotation_id - b.rotation_id)
    .map((l) => `${names.get(l.rotation_id)}${l.level === "trainer" ? " (trainer)" : l.level === "training" ? " (learning)" : ""}`);
  return parts.length ? parts.join(", ") : "No rotations yet";
}
