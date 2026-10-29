import type { SlotView } from "../api";

export interface GridDay { day: number; date: string; weekday: string }
export interface GridRow {
  key: string; rotationId: number; rotationName: string; block: string; start: string; end: string;
  cells: Record<number, SlotView>; // day index -> slot (a rotation that doesn't run that day has no cell)
}
export interface Grid { days: GridDay[]; rows: GridRow[] }

/** Lays slots out as rows (rotation + block) by columns (days). */
export function buildGrid(slots: SlotView[]): Grid {
  const days = new Map<number, GridDay>();
  const rows = new Map<string, GridRow>();
  for (const slot of slots) {
    days.set(slot.day, { day: slot.day, date: slot.date, weekday: slot.weekday });
    const key = `${slot.rotation_id}|${slot.block}`;
    if (!rows.has(key)) {
      rows.set(key, {
        key, rotationId: slot.rotation_id, rotationName: slot.rotation_name, block: slot.block, start: slot.start, end: slot.end, cells: {},
      });
    }
    rows.get(key)!.cells[slot.day] = slot;
  }
  return {
    days: [...days.values()].sort((a, b) => a.day - b.day),
    rows: [...rows.values()].sort((a, b) => a.rotationId - b.rotationId || a.start.localeCompare(b.start) || a.block.localeCompare(b.block)),
  };
}
