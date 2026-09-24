import { Card } from "@servicoop/frontend-foundation";

import type { FrequentIncident } from "../AlarmModels";
import styles from "./FrequencyPanel.module.css";

export interface FrequencyPanelProps {
  items: FrequentIncident[];
}

function frequencyValue(value: number | null, window: string) {
  if (value !== null) return <strong>{value}</strong>;
  const explanation = `Historial insuficiente para confirmar la ventana móvil de ${window}.`;
  return <strong><span aria-label={explanation} className={styles.unknown} tabIndex={0} title={explanation}>!?</span></strong>;
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
            {frequencyValue(item.daily, "24 horas")}
            {frequencyValue(item.weekly, "7 días")}
            {frequencyValue(item.monthly, "30 días")}
            {frequencyValue(item.annual, "365 días")}
          </div>
        ))}
        {items.length === 0 && <p>No hay alarmas confirmadas.</p>}
      </div>
    </Card>
  );
}
