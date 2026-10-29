import { describeError } from "./lib/errors";

export type Level = "training" | "trained" | "trainer";
export type TimeOffKind = "approved" | "preferred";

export interface Block { name: string; start: string; end: string; headcount: number }
export interface RotationInput { name: string; weekdays: number[]; max_trainees: number; blocks: Block[] }
export interface Rotation extends RotationInput { id: number; active: boolean }

export interface RotationLink { rotation_id: number; level: Level }
export interface AvailabilityWindow { weekday: number; start: string; end: string }
export interface TimeOff { date: string; kind: TimeOffKind }
export interface EmployeeInput {
  name: string; rank: string; color: string; max_hours_week: number; target_hours_week: number;
  rotations: RotationLink[]; availability: AvailabilityWindow[]; time_off: TimeOff[];
}
export interface Employee extends EmployeeInput { id: number; active: boolean }

export interface SlotAssignment {
  employee_id: number; name: string; rank: string; color: string; role: "worker" | "trainee";
  trainer_id: number | null; trainer_name: string | null;
}
export interface SlotView {
  id: string; rotation_id: number; rotation_name: string; block: string; day: number; date: string; weekday: string;
  start: string; end: string; headcount: number; max_trainees: number; assignments: SlotAssignment[]; workers: number; short: number;
}
export interface Summary {
  valid: boolean; violations: number; seats_required: number; seats_filled: number; coverage_pct: number;
  uncovered_slots: number; hours_mean: number; hours_stddev: number; hours_min: number; hours_max: number;
  over_target_hours: number; under_target_hours: number; preferred_off_worked: number; trainee_assignments: number;
}
export interface Violation { rule: string; message: string }
export interface ScheduleMeta {
  id: number; name: string; start_date: string; num_days: number; solver_status: string; objective: number | null; created_at: string | null;
}
export interface Lock { id: number; employee_id: number; slot_id: string; kind: "pin" | "ban" }
export interface ScheduleDetail {
  schedule: ScheduleMeta;
  view: { slots: SlotView[]; summary: Summary; violations: Violation[] };
  locks: Lock[];
  changes?: string[];
}
export interface Candidate {
  employee_id: number; name: string; rank: string; color: string; status: "assigned" | "eligible" | "blocked";
  role: "worker" | "trainee" | null; needs_change: boolean; reasons: string[];
}
export interface Explanation {
  employee_id: number; slot_id: string; status: string; summary: string; proven_optimal: boolean | null;
  blockers: { code: string; message: string }[];
  changes: { kind: string; employee_id: number; slot_id: string; role: string; text: string }[];
  cost_delta: { coverage: number; fairness: number; preference: number; training: number; total: number } | null;
}
export interface AuditEntry { id: number; at: string | null; action: string; entity_type: string; entity_id: string; details: Record<string, unknown> }

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = ((await res.json()) as { detail?: unknown }).detail ?? detail;
    } catch {
      /* not JSON: keep the status text */
    }
    throw new ApiError(describeError(detail), res.status);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

const send = (method: string, body?: unknown): RequestInit => ({ method, body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  listRotations: () => request<Rotation[]>("/api/rotations"),
  saveRotation: (id: number | null, body: RotationInput) =>
    id === null ? request<Rotation>("/api/rotations", send("POST", body)) : request<Rotation>(`/api/rotations/${id}`, send("PUT", body)),
  archiveRotation: (id: number) => request<void>(`/api/rotations/${id}`, send("DELETE")),

  listEmployees: () => request<Employee[]>("/api/employees"),
  saveEmployee: (id: number | null, body: EmployeeInput) =>
    id === null ? request<Employee>("/api/employees", send("POST", body)) : request<Employee>(`/api/employees/${id}`, send("PUT", body)),
  archiveEmployee: (id: number) => request<void>(`/api/employees/${id}`, send("DELETE")),

  listSchedules: () => request<ScheduleMeta[]>("/api/schedules"),
  createSchedule: (body: { name: string; start_date: string; num_days: number; time_limit: number }) =>
    request<ScheduleDetail>("/api/schedules", send("POST", body)),
  getSchedule: (id: number) => request<ScheduleDetail>(`/api/schedules/${id}`),
  candidates: (id: number, slotId: string) => request<Candidate[]>(`/api/schedules/${id}/slots/${encodeURIComponent(slotId)}/candidates`),
  override: (id: number, body: { pins?: { employee_id: number; slot_id: string }[]; bans?: { employee_id: number; slot_id: string }[] }) =>
    request<ScheduleDetail>(`/api/schedules/${id}/overrides`, send("POST", body)),
  removeLock: (id: number, lockId: number) => request<void>(`/api/schedules/${id}/locks/${lockId}`, send("DELETE")),
  explain: (id: number, employeeId: number, slotId: string) =>
    request<Explanation>(`/api/schedules/${id}/explain?employee_id=${employeeId}&slot_id=${encodeURIComponent(slotId)}`),

  audit: () => request<AuditEntry[]>("/api/audit?limit=100"),
};
