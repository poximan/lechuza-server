import { Card } from "@servicoop/frontend-foundation";

import type { IncidentCounts } from "../AlarmModels";
import styles from "./SummaryGrid.module.css";

export interface SummaryGridProps {
  counts: IncidentCounts;
}

export function SummaryGrid({ counts }: SummaryGridProps) {
  const items = [
    ["Potenciales", counts.potential],
    ["Activas", counts.active],
    ["En recuperación", counts.recovering],
    ["Resueltas", counts.resolved],
  ] as const;
  return (
    <section className={styles.grid} aria-label="Resumen de alarmas">
      {items.map(([label, value]) => (
        <Card className={styles.item} key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </Card>
      ))}
    </section>
  );
}
