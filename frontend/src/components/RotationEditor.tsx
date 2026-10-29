import { useState } from "react";
import { api } from "../api";
import type { Rotation } from "../api";
import { describeThrown } from "../lib/errors";
import type { RotationForm } from "../lib/forms";
import { emptyRotationForm, formToRotationInput, rotationToForm, validateRotationForm } from "../lib/forms";
import { WEEKDAYS_SHORT } from "../lib/time";
import Problems from "./Problems";

interface Props { rotation: Rotation | null; onDone: (changed: boolean) => void }

export default function RotationEditor({ rotation, onDone }: Props) {
  const [form, setForm] = useState<RotationForm>(() => (rotation ? rotationToForm(rotation) : emptyRotationForm()));
  const [problems, setProblems] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const setBlock = (i: number, patch: Partial<RotationForm["blocks"][number]>) =>
    setForm((f) => ({ ...f, blocks: f.blocks.map((b, j) => (j === i ? { ...b, ...patch } : b)) }));
  const toggleDay = (day: number) =>
    setForm((f) => ({ ...f, weekdays: f.weekdays.includes(day) ? f.weekdays.filter((d) => d !== day) : [...f.weekdays, day] }));

  async function save() {
    const found = validateRotationForm(form);
    if (found.length > 0) {
      setProblems(found);
      return;
    }
    setSaving(true);
    try {
      await api.saveRotation(rotation ? rotation.id : null, formToRotationInput(form));
      onDone(true);
    } catch (err) {
      setProblems([describeThrown(err)]);
      setSaving(false);
    }
  }

  async function archive() {
    if (!rotation || !window.confirm(`Archive ${rotation.name}? It stops appearing in new schedules.`)) return;
    try {
      await api.archiveRotation(rotation.id);
      onDone(true);
    } catch (err) {
      setProblems([describeThrown(err)]);
    }
  }

  return (
    <div className="editor">
      <h3>{rotation ? `Edit ${rotation.name}` : "New rotation"}</h3>
      <div className="row">
        <label>Name <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label>Trainees allowed per block <input className="narrow" value={form.maxTrainees} onChange={(e) => setForm({ ...form, maxTrainees: e.target.value })} /></label>
      </div>
      <div className="row">
        <span>Runs on</span>
        {WEEKDAYS_SHORT.map((d, n) => (
          <label key={d} className="check"><input type="checkbox" checked={form.weekdays.includes(n)} onChange={() => toggleDay(n)} /> {d}</label>
        ))}
      </div>

      <h4>Blocks</h4>
      <p className="muted">Split the day into blocks. Part-day staff can cover some blocks but not others.</p>
      {form.blocks.map((b, i) => (
        <div className="row" key={i}>
          <input value={b.name} className="narrow" placeholder="Name" onChange={(e) => setBlock(i, { name: e.target.value })} />
          <input type="time" value={b.start} onChange={(e) => setBlock(i, { start: e.target.value })} />
          <span>to</span>
          <input type="time" value={b.end} onChange={(e) => setBlock(i, { end: e.target.value })} />
          <label>people needed <input className="narrow" value={b.headcount} onChange={(e) => setBlock(i, { headcount: e.target.value })} /></label>
          <button onClick={() => setForm({ ...form, blocks: form.blocks.filter((_, j) => j !== i) })}>Remove</button>
        </div>
      ))}
      <button onClick={() => setForm({ ...form, blocks: [...form.blocks, { name: "", start: "15:00", end: "19:00", headcount: "1" }] })}>Add a block</button>

      <Problems problems={problems} />
      <div className="row">
        <button className="primary" disabled={saving} onClick={() => void save()}>{saving ? "Saving..." : "Save"}</button>
        <button onClick={() => onDone(false)}>Cancel</button>
        {rotation && <button className="danger" onClick={() => void archive()}>Archive</button>}
      </div>
    </div>
  );
}
