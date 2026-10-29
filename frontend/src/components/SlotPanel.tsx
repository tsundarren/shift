import { useEffect, useState } from "react";
import { api } from "../api";
import type { Candidate, Explanation, Lock, ScheduleDetail, SlotView } from "../api";
import { shortDate } from "../lib/dates";
import { describeThrown } from "../lib/errors";
import Chip from "./Chip";

interface Props {
  scheduleId: number;
  slot: SlotView;
  locks: Lock[];
  revision: number;
  onRevised: (detail: ScheduleDetail) => void;
  onClose: () => void;
}

export default function SlotPanel({ scheduleId, slot, locks, revision, onRevised, onClose }: Props) {
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setCandidates(null);
    api.candidates(scheduleId, slot.id)
      .then((c) => {
        if (!cancelled) setCandidates(c);
      })
      .catch((err) => {
        if (!cancelled) setError(describeThrown(err));
      });
    return () => {
      cancelled = true;
    };
  }, [scheduleId, slot.id, revision]);

  useEffect(() => {
    setExplanation(null);
    setError(null);
  }, [slot.id]);

  async function act(work: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (err) {
      setError(describeThrown(err));
    } finally {
      setBusy(false);
    }
  }

  const pair = (c: Candidate) => ({ employee_id: c.employee_id, slot_id: slot.id });
  const pin = (c: Candidate) => act(async () => onRevised(await api.override(scheduleId, { pins: [pair(c)] })));
  const ban = (c: Candidate) => act(async () => onRevised(await api.override(scheduleId, { bans: [pair(c)] })));
  const why = (c: Candidate) => act(async () => setExplanation(await api.explain(scheduleId, c.employee_id, slot.id)));
  const lockFor = (c: Candidate) => locks.find((l) => l.slot_id === slot.id && l.employee_id === c.employee_id);

  const assigned = candidates?.filter((c) => c.status === "assigned") ?? [];
  const eligible = candidates?.filter((c) => c.status === "eligible") ?? [];
  const blocked = candidates?.filter((c) => c.status === "blocked") ?? [];

  const row = (c: Candidate, actions: JSX.Element) => (
    <li key={c.employee_id}>
      <div className="row">
        <Chip color={c.color} dashed={c.role === "trainee"}>{c.name}</Chip>
        <span className="muted">{c.rank}</span>
        {c.role === "trainee" && <span className="badge">as a trainee</span>}
        {lockFor(c) && <span className="badge">{lockFor(c)!.kind === "pin" ? "Pinned" : "Kept off"}</span>}
        {actions}
      </div>
      {c.reasons.length > 0 && <small className="muted">{c.reasons.join("; ")}</small>}
    </li>
  );

  return (
    <aside className="panel">
      <div className="toolbar">
        <h3>{slot.rotation_name} {slot.block}</h3>
        <button onClick={onClose}>Close</button>
      </div>
      <p className="muted">{slot.weekday} {shortDate(slot.date)}, {slot.start}-{slot.end}. Needs {slot.headcount}, has {slot.workers}.</p>
      {error && <p className="error">{error}</p>}
      {!candidates && !error && <p className="muted">Loading...</p>}

      {candidates && (
        <>
          <h4>On this shift</h4>
          {assigned.length === 0 && <p className="muted">Nobody.</p>}
          <ul>{assigned.map((c) => row(c, <button disabled={busy} onClick={() => void ban(c)}>Keep off this shift</button>))}</ul>

          <h4>Could be added</h4>
          {eligible.length === 0 && <p className="muted">Nobody else is eligible.</p>}
          <ul>
            {eligible.map((c) => row(c, (
              <>
                <button className="primary" disabled={busy} onClick={() => void pin(c)}>Put here</button>
                <button disabled={busy} onClick={() => void why(c)}>Why not?</button>
              </>
            )))}
          </ul>

          {explanation && (
            <div className="notice">
              <strong>{explanation.status}</strong>
              <p>{explanation.summary}</p>
              {explanation.proven_optimal === false && <small className="muted">The solver ran out of time, so this may not be the cheapest option.</small>}
            </div>
          )}

          <details>
            <summary>Not possible ({blocked.length})</summary>
            <ul>
              {blocked.map((c) => (
                <li key={c.employee_id}>
                  <div className="row"><Chip color={c.color}>{c.name}</Chip>{lockFor(c) && <span className="badge">Kept off</span>}</div>
                  <small className="muted">{c.reasons.join("; ")}</small>
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
    </aside>
  );
}
