import { Card } from "@servicoop/frontend-foundation";

import { AlarmPresenter } from "../AlarmPresenter";
import type { ClearanceMetric } from "../AlarmModels";
import styles from "./ClearanceTable.module.css";

export interface ClearanceTableProps {
  items: ClearanceMetric[];
  presenter: AlarmPresenter;
}

export function ClearanceTable({ items, presenter }: ClearanceTableProps) {
  return (
    <Card>
      <div className={styles.heading}><h2>Tiempos de despeje</h2><p>Configurado frente a mediana y P90 históricos.</p></div>
      <div className={styles.tableWrap}>
        <table>
          <thead><tr><th>Alarma</th><th>Configurado</th><th>Mediana</th><th>P90</th><th>Muestras</th></tr></thead>
          <tbody>{items.map((item) => (
            <tr key={item.alarm_key}><td>{item.title}</td><td>{presenter.minutes(item.configured_minutes)}</td><td>{presenter.minutes(item.median_minutes)}</td><td>{presenter.minutes(item.p90_minutes)}</td><td>{item.sample_count}</td></tr>
          ))}</tbody>
        </table>
        {items.length === 0 && <p className={styles.empty}>Aún no hay alarmas confirmadas.</p>}
      </div>
    </Card>
  );
}
