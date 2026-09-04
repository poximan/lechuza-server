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
      <div className={styles.heading}><h2>Duración de estados</h2><p>Actividad e inactividad históricas por alarma.</p></div>
      <div className={styles.tableWrap}>
        <table>
          <thead><tr><th>Alarma</th><th>Despeje esperado</th><th>Actividad mediana / P90</th><th>Inactividad mediana / P90</th><th>Muestras A/I</th></tr></thead>
          <tbody>{items.map((item) => (
            <tr key={`${item.source_id}/${item.alarm_key}`}><td>{item.title}</td><td>{presenter.minutes(item.configured_minutes)}</td><td>{presenter.minutes(item.median_active_minutes)} / {presenter.minutes(item.p90_active_minutes)}</td><td>{presenter.minutes(item.median_inactive_minutes)} / {presenter.minutes(item.p90_inactive_minutes)}</td><td>{item.active_sample_count}/{item.inactive_sample_count}</td></tr>
          ))}</tbody>
        </table>
        {items.length === 0 && <p className={styles.empty}>Aún no hay alarmas confirmadas.</p>}
      </div>
    </Card>
  );
}
