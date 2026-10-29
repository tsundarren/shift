import { useState } from "react";
import { api } from "../api";
import type { Employee, Level, Rotation } from "../api";
import { isHexColor, normalizeHex } from "../lib/color";
import { describeThrown } from "../lib/errors";
import type { EmployeeForm } from "../lib/forms";
import { emptyEmployeeForm, employeeToForm, formToEmployeeInput, validateEmployeeForm } from "../lib/forms";
import { levelLabel } from "../lib/people";
import { WEEKDAYS_SHORT } from "../lib/time";
import Chip from "./Chip";
import Problems from "./Problems";

interface Props { employee: Employee | null; rotations: Rotation[]; onDone: (changed: boolean) => void }

export default function EmployeeEditor({ employee, rotations, onDone }: Props) {
  const [form, setForm] = useState<EmployeeForm>(() => (employee ? employeeToForm(employee, rotations) : emptyEmployeeForm(rotations)));
  const [problems, setProblems] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const set = <K extends keyof EmployeeForm>(key: K, value: EmployeeForm[K]) => setForm((f) => ({ ...f, [key]: value }));
  const previewColor = isHexColor(normalizeHex(form.color) ?? "") ? (normalizeHex(form.color) as string) : "#CCCCCC";

  async function save() {
    const found = validateEmployeeForm(form);
    if (found.length > 0) {
      setProblems(found);
      return;
    }
    setSaving(true);
    try {
      await api.saveEmployee(employee ? employee.id : null, formToEmployeeInput(form));
      onDone(true);
    } catch (err) {
      setProblems([describeThrown(err)]);
      setSaving(false);
    }
  }

  async function archive() {
    if (!employee || !window.confirm(`Archive ${employee.name}? They stay on past schedules but can't be scheduled.`)) return;
    try {
      await api.archiveEmployee(employee.id);
      onDone(true);
    } catch (err) {
      setProblems([describeThrown(err)]);
    }
  }

  return (
    <div className="editor">
      <h3>{employee ? `Edit ${employee.name}` : "New employee"}</h3>
      <div className="row">
        <label>Name <input value={form.name} onChange={(e) => set("name", e.target.value)} /></label>
        <label>Rank <input value={form.rank} placeholder="e.g. Senior" onChange={(e) => set("rank", e.target.value)} /></label>
        <label>Color
          <span className="inline">
            <input type="color" value={previewColor} onChange={(e) => set("color", e.target.value.toUpperCase())} />
            <input value={form.color} className="narrow" onChange={(e) => set("color", e.target.value)} />
          </span>
        </label>
        <span className="preview"><Chip color={previewColor}>{form.name || "Name"}</Chip></span>
      </div>
      <div className="row">
        <label>Max hours / week <input value={form.maxHours} className="narrow" onChange={(e) => set("maxHours", e.target.value)} /></label>
        <label>Target hours / week <input value={form.targetHours} className="narrow" onChange={(e) => set("targetHours", e.target.value)} /></label>
      </div>

      <h4>Rotations</h4>
      {rotations.length === 0 && <p className="muted">Create a rotation first.</p>}
      <div className="levels">
        {rotations.map((r) => (
          <label key={r.id}>{r.name}
            <select value={form.levels[r.id] ?? "none"} onChange={(e) => setForm((f) => ({ ...f, levels: { ...f.levels, [r.id]: e.target.value as Level | "none" } }))}>
              {(["none", "training", "trained", "trainer"] as const).map((level) => (
                <option key={level} value={level}>{levelLabel(level)}</option>
              ))}
            </select>
          </label>
        ))}
      </div>

      <h4>Weekly availability</h4>
      {form.availability.map((w, i) => (
        <div className="row" key={i}>
          <select value={w.weekday} onChange={(e) => set("availability", form.availability.map((x, j) => (j === i ? { ...x, weekday: Number(e.target.value) } : x)))}>
            {WEEKDAYS_SHORT.map((d, n) => (<option key={d} value={n}>{d}</option>))}
          </select>
          <input type="time" value={w.start} onChange={(e) => set("availability", form.availability.map((x, j) => (j === i ? { ...x, start: e.target.value } : x)))} />
          <span>to</span>
          <input type="time" value={w.end} onChange={(e) => set("availability", form.availability.map((x, j) => (j === i ? { ...x, end: e.target.value } : x)))} />
          <button onClick={() => set("availability", form.availability.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <button onClick={() => set("availability", [...form.availability, { weekday: 0, start: "07:00", end: "15:00" }])}>Add a window</button>

      <h4>Time off</h4>
      {form.timeOff.map((t, i) => (
        <div className="row" key={i}>
          <input type="date" value={t.date} onChange={(e) => set("timeOff", form.timeOff.map((x, j) => (j === i ? { ...x, date: e.target.value } : x)))} />
          <select value={t.kind} onChange={(e) => set("timeOff", form.timeOff.map((x, j) => (j === i ? { ...x, kind: e.target.value as "approved" | "preferred" } : x)))}>
            <option value="approved">Approved (must be off)</option>
            <option value="preferred">Preferred (try to avoid)</option>
          </select>
          <button onClick={() => set("timeOff", form.timeOff.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <button onClick={() => set("timeOff", [...form.timeOff, { date: "", kind: "approved" }])}>Add time off</button>

      <Problems problems={problems} />
      <div className="row">
        <button className="primary" disabled={saving} onClick={() => void save()}>{saving ? "Saving..." : "Save"}</button>
        <button onClick={() => onDone(false)}>Cancel</button>
        {employee && <button className="danger" onClick={() => void archive()}>Archive</button>}
      </div>
    </div>
  );
}
