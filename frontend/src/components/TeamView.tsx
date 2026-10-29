import { useState } from "react";
import type { Employee, Rotation } from "../api";
import { textColorFor } from "../lib/color";
import { rotationSummary, summarizeAvailability } from "../lib/people";
import EmployeeEditor from "./EmployeeEditor";

interface Props { employees: Employee[]; rotations: Rotation[]; onChanged: () => void }

export default function TeamView({ employees, rotations, onChanged }: Props) {
  const [editing, setEditing] = useState<Employee | "new" | null>(null);
  return (
    <section>
      <div className="toolbar">
        <h2>Team</h2>
        <button className="primary" onClick={() => setEditing("new")}>Add employee</button>
      </div>
      {editing && (
        <EmployeeEditor
          key={editing === "new" ? "new" : editing.id}
          employee={editing === "new" ? null : editing}
          rotations={rotations}
          onDone={(changed) => {
            setEditing(null);
            if (changed) onChanged();
          }}
        />
      )}
      {employees.length === 0 && <p className="muted">No one yet. Add your first employee.</p>}
      <div className="cards">
        {employees.map((e) => (
          <button key={e.id} className="person-card" style={{ background: e.color, color: textColorFor(e.color) }} onClick={() => setEditing(e)}>
            <strong>{e.name}</strong>
            <span>{e.rank || "No rank"}</span>
            <small>{rotationSummary(e.rotations, rotations)}</small>
            <small>{summarizeAvailability(e.availability)}</small>
          </button>
        ))}
      </div>
    </section>
  );
}
