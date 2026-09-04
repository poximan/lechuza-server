import { Card } from "@servicoop/frontend-foundation";

import type { FrequentIncident } from "../AlarmModels";
import styles from "./FrequencyPanel.module.css";

export interface FrequencyPanelProps {
  items: FrequentIncident[];
}

export function FrequencyPanel({ items }: FrequencyPanelProps) {
  return (
    <Card>
      <div className={styles.heading}><h2>Frecuencia</h2><p>Alarmas confirmadas por ventana móvil.</p></div>
      <div className={styles.ranking}>
        {items.length > 0 && <div className={styles.labels}><span>Alarma</span><span>24 h</span><span>7 d</span><span>30 d</span><span>365 d</span></div>}
        {items.map((item) => (
          <div className={styles.item} key={`${item.source_id}/${item.alarm_key}`}>
            <span title={item.title}>{item.title}</span>
            <strong>{item.daily}</strong>
            <strong>{item.weekly}</strong>
            <strong>{item.monthly}</strong>
            <strong>{item.annual}</strong>
          </div>
        ))}
        {items.length === 0 && <p>No hay alarmas confirmadas.</p>}
      </div>
    </Card>
  );
}
