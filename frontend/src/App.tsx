import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { Employee, Rotation } from "./api";
import ActivityView from "./components/ActivityView";
import RotationsView from "./components/RotationsView";
import ScheduleView from "./components/ScheduleView";
import TeamView from "./components/TeamView";
import { describeThrown } from "./lib/errors";

type Tab = "schedule" | "team" | "rotations" | "activity";
const TABS: [Tab, string][] = [["schedule", "Schedule"], ["team", "Team"], ["rotations", "Rotations"], ["activity", "Activity"]];

export default function App() {
  const [tab, setTab] = useState<Tab>("schedule");
  const [rotations, setRotations] = useState<Rotation[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [r, e] = await Promise.all([api.listRotations(), api.listEmployees()]);
      setRotations(r);
      setEmployees(e);
      setError(null);
    } catch (err) {
      setError(describeThrown(err));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div className="page">
      <header>
        <span className="brand">Shift</span>
        <nav>
          {TABS.map(([id, label]) => (
            <button key={id} className={tab === id ? "tab active" : "tab"} onClick={() => setTab(id)}>{label}</button>
          ))}
        </nav>
        <span className="muted">synthetic data</span>
      </header>
      {error && <p className="error">Could not reach the server: {error}. Is the API running on port 8000?</p>}
      {loaded && tab === "schedule" && <ScheduleView employees={employees} rotations={rotations} />}
      {loaded && tab === "team" && <TeamView employees={employees} rotations={rotations} onChanged={reload} />}
      {loaded && tab === "rotations" && <RotationsView rotations={rotations} onChanged={reload} />}
      {loaded && tab === "activity" && <ActivityView />}
    </div>
  );
}
