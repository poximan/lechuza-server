import { Card } from "@servicoop/frontend-foundation";

import type { FrequentIncident } from "../AlarmModels";
import styles from "./FrequencyPanel.module.css";

export interface FrequencyPanelProps {
  items: FrequentIncident[];
}

export function FrequencyPanel({ items }: FrequencyPanelProps) {
  const maximum = Math.max(1, ...items.map((item) => item.total));
  return (
    <Card>
      <div className={styles.heading}><h2>Más frecuentes</h2><p>Alarmas confirmadas agrupadas por origen.</p></div>
      <div className={styles.ranking}>
        {items.map((item) => (
          <div className={styles.item} key={item.alarm_key}>
            <span title={item.title}>{item.title}</span>
            <div className={styles.track}><div className={styles.bar} style={{ width: `${Math.round(item.total * 100 / maximum)}%` }} /></div>
            <strong>{item.total}</strong>
          </div>
        ))}
        {items.length === 0 && <p>No hay alarmas confirmadas.</p>}
      </div>
    </Card>
  );
}
