import { useState } from "react";
import type { Rotation } from "../api";
import { summarizeWeekdays } from "../lib/people";
import RotationEditor from "./RotationEditor";

interface Props { rotations: Rotation[]; onChanged: () => void }

export default function RotationsView({ rotations, onChanged }: Props) {
  const [editing, setEditing] = useState<Rotation | "new" | null>(null);
  return (
    <section>
      <div className="toolbar">
        <h2>Rotations</h2>
        <button className="primary" onClick={() => setEditing("new")}>Add rotation</button>
      </div>
      {editing && (
        <RotationEditor
          key={editing === "new" ? "new" : editing.id}
          rotation={editing === "new" ? null : editing}
          onDone={(changed) => {
            setEditing(null);
            if (changed) onChanged();
          }}
        />
      )}
      {rotations.length === 0 && <p className="muted">No rotations yet. A rotation is a task or station that needs staffing, split into blocks like AM and PM.</p>}
      <div className="cards">
        {rotations.map((r) => (
          <button key={r.id} className="rotation-card" onClick={() => setEditing(r)}>
            <strong>{r.name}</strong>
            <small>{summarizeWeekdays(r.weekdays)}</small>
            {r.blocks.map((b) => (
              <small key={b.name}>{b.name}: {b.start}-{b.end}, needs {b.headcount}</small>
            ))}
          </button>
        ))}
      </div>
    </section>
  );
}
