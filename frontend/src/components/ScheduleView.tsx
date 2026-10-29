import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { Employee, Lock, Rotation, ScheduleDetail, ScheduleMeta, SlotView } from "../api";
import { isIsoDate, nextMonday, shortDate } from "../lib/dates";
import { describeThrown } from "../lib/errors";
import { buildGrid } from "../lib/grid";
import { describeAssignment } from "../lib/people";
import Chip from "./Chip";
import SlotPanel from "./SlotPanel";

interface Props { employees: Employee[]; rotations: Rotation[] }

const slotLabel = (s: SlotView) => `${s.rotation_name} ${s.block}, ${s.weekday.slice(0, 3)} ${shortDate(s.date)}`;

export default function ScheduleView({ employees, rotations }: Props) {
  const [schedules, setSchedules] = useState<ScheduleMeta[]>([]);
  const [detail, setDetail] = useState<ScheduleDetail | null>(null);
  const [revision, setRevision] = useState(0); // bumped on every change so the slot panel refetches
  const [selectedSlotId, setSelectedSlotId] = useState<string | null>(null);
  const [changes, setChanges] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("Schedule");
  const [start, setStart] = useState(() => nextMonday(new Date()));
  const [days, setDays] = useState(7);
  const [limit, setLimit] = useState(10);

  const show = useCallback((d: ScheduleDetail, keepSelection: boolean) => {
    setDetail(d);
    setRevision((n) => n + 1);
    setChanges(d.changes ?? []);
    if (!keepSelection) setSelectedSlotId(null);
  }, []);

  const open = useCallback(async (id: number) => {
    setBusy("Loading...");
    try {
      show(await api.getSchedule(id), false);
      setError(null);
    } catch (err) {
      setError(describeThrown(err));
    } finally {
      setBusy(null);
    }
  }, [show]);

  useEffect(() => {
    api.listSchedules()
      .then((list) => {
        setSchedules(list);
        if (list.length > 0) void open(list[0].id);
      })
      .catch((err) => setError(describeThrown(err)));
  }, [open]);

  async function create() {
    if (!isIsoDate(start)) return setError("Pick a start date.");
    if (rotations.length === 0 || employees.length === 0) return setError("Add at least one rotation and one employee first.");
    setBusy(`Solving (up to ${limit} seconds)...`);
    try {
      const d = await api.createSchedule({ name: name.trim() || "Schedule", start_date: start, num_days: days, time_limit: limit });
      show(d, false);
      setSchedules(await api.listSchedules());
      setError(null);
    } catch (err) {
      setError(describeThrown(err));
    } finally {
      setBusy(null);
    }
  }

  async function unlock(lock: Lock) {
    if (!detail) return;
    try {
      await api.removeLock(detail.schedule.id, lock.id);
      show(await api.getSchedule(detail.schedule.id), true);
    } catch (err) {
      setError(describeThrown(err));
    }
  }

  const grid = useMemo(() => (detail ? buildGrid(detail.view.slots) : null), [detail]);
  const selected = detail?.view.slots.find((s) => s.id === selectedSlotId) ?? null;
  const names = useMemo(() => new Map(employees.map((e) => [e.id, e.name])), [employees]);
  const summary = detail?.view.summary;

  return (
    <section>
      <div className="toolbar">
        <h2>Schedule</h2>
        {schedules.length > 0 && (
          <select value={detail?.schedule.id ?? ""} onChange={(e) => void open(Number(e.target.value))}>
            {schedules.map((s) => (<option key={s.id} value={s.id}>{s.name}, from {shortDate(s.start_date)}</option>))}
          </select>
        )}
      </div>

      <div className="editor">
        <div className="row">
          <label>Name <input value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label>Starts <input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label>
          <label>Days
            <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[3, 7, 14].map((n) => (<option key={n} value={n}>{n}</option>))}
            </select>
          </label>
          <label>Solve for up to
            <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
              {[5, 10, 30].map((n) => (<option key={n} value={n}>{n} s</option>))}
            </select>
          </label>
          <button className="primary" disabled={busy !== null} onClick={() => void create()}>Create schedule</button>
        </div>
      </div>

      {busy && <p className="muted">{busy}</p>}
      {error && <p className="error">{error}</p>}
      {!detail && !busy && <p className="muted">No schedule yet. Add rotations and team members, then create one.</p>}

      {detail && summary && grid && (
        <>
          <div className="stats">
            <div><strong>{summary.coverage_pct.toFixed(0)}%</strong><span>seats filled</span></div>
            <div><strong>{summary.uncovered_slots}</strong><span>slots short</span></div>
            <div><strong>{summary.hours_stddev.toFixed(1)} h</strong><span>spread in hours</span></div>
            <div><strong>{summary.trainee_assignments}</strong><span>trainee shifts</span></div>
            <div><strong>{detail.schedule.solver_status.toLowerCase()}</strong><span>solver</span></div>
          </div>

          {detail.view.violations.length > 0 && (
            <div className="error">
              <strong>This schedule no longer follows the rules.</strong> The team or rotations changed after it was created.
              <ul>{detail.view.violations.slice(0, 8).map((v, i) => (<li key={i}>{v.message}</li>))}</ul>
            </div>
          )}

          {changes.length > 0 && (
            <div className="notice">
              <strong>{changes.length} change{changes.length === 1 ? "" : "s"} made:</strong>
              <ul>{changes.map((c, i) => (<li key={i}>{c}</li>))}</ul>
            </div>
          )}

          <div className="split">
            <div className="grid-wrap">
              <table className="grid">
                <thead>
                  <tr>
                    <th>Rotation</th>
                    {grid.days.map((d) => (<th key={d.day}>{d.weekday.slice(0, 3)}<br /><small>{shortDate(d.date)}</small></th>))}
                  </tr>
                </thead>
                <tbody>
                  {grid.rows.map((row) => (
                    <tr key={row.key}>
                      <th>{row.rotationName}<br /><small>{row.block} {row.start}-{row.end}</small></th>
                      {grid.days.map((d) => {
                        const slot = row.cells[d.day];
                        if (!slot) return <td key={d.day} className="empty">-</td>;
                        const classes = ["cell", slot.short > 0 ? "short" : "", slot.id === selectedSlotId ? "selected" : ""].join(" ");
                        return (
                          <td key={d.day}>
                            <button className={classes} onClick={() => setSelectedSlotId(slot.id)}>
                              {slot.assignments.map((a) => (
                                <Chip key={a.employee_id} color={a.color} dashed={a.role === "trainee"} title={`${describeAssignment(a)}, ${a.rank || "no rank"}`}>
                                  {describeAssignment(a)}
                                </Chip>
                              ))}
                              {slot.short > 0 && <span className="need">needs {slot.short} more</span>}
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {selected && (
              <SlotPanel
                scheduleId={detail.schedule.id}
                slot={selected}
                locks={detail.locks}
                revision={revision}
                onRevised={(d) => show(d, true)}
                onClose={() => setSelectedSlotId(null)}
              />
            )}
          </div>

          {detail.locks.length > 0 && (
            <div className="locks">
              <h4>Manual decisions</h4>
              <p className="muted">Every re-solve keeps these. Unlocking forgets the decision but leaves the schedule as it is.</p>
              <ul>
                {detail.locks.map((l) => {
                  const slot = detail.view.slots.find((s) => s.id === l.slot_id);
                  return (
                    <li key={l.id}>
                      <span className="badge">{l.kind === "pin" ? "Pinned" : "Kept off"}</span> {names.get(l.employee_id) ?? `Employee ${l.employee_id}`}
                      {" "}on {slot ? slotLabel(slot) : l.slot_id} <button onClick={() => void unlock(l)}>Unlock</button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}
