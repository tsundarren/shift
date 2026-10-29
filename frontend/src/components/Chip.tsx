import type { ReactNode } from "react";
import { textColorFor } from "../lib/color";

/** A person, drawn as a rounded pill in their color, with text that stays readable on any background. */
export default function Chip({ color, children, title, dashed = false }: { color: string; children: ReactNode; title?: string; dashed?: boolean }) {
  return (
    <span className={dashed ? "chip trainee" : "chip"} title={title} style={{ background: color, color: textColorFor(color) }}>
      {children}
    </span>
  );
}
