import { Card, StatusBadge } from "@servicoop/frontend-foundation";
import type { ReactNode } from "react";

import { AlarmPresenter } from "../AlarmPresenter";
import type { Incident } from "../AlarmModels";
import styles from "./IncidentsTable.module.css";

export interface IncidentsTableProps {
  incidents: Incident[];
  presenter: AlarmPresenter;
  referenceNow: string;
  toolbar: ReactNode;
}

export function IncidentsTable({ incidents, presenter, referenceNow, toolbar }: IncidentsTableProps) {
  return (
    <Card>
      <div className={styles.heading}>
        <div><h2>Incidencias</h2><p>Alarmero confirma, persiste y administra cada ciclo de vida.</p></div>
        {toolbar}
      </div>
      <div className={styles.tableWrap}>
        <table>
          <thead><tr><th>Estado</th><th>Alarma</th><th>Inicio</th><th>Antigüedad</th><th>Despeje esperado</th><th>Correo</th><th>Destinatarios</th></tr></thead>
          <tbody>
            {incidents.map((incident) => (
              <tr key={incident.incident_id}>
                <td><StatusBadge tone={presenter.statusTone(incident.status)}>{presenter.statusLabel(incident.status)}</StatusBadge></td>
                <td><strong>{incident.title}</strong><code>{incident.alarm_key}</code></td>
                <td>{presenter.date(incident.first_seen_at)}</td>
                <td>{presenter.age(incident.first_seen_at, incident.resolved_at, referenceNow)}</td>
                <td>{presenter.minutes(incident.expected_clearance_minutes)}</td>
                <td title={incident.dispatch_error ?? undefined}><StatusBadge tone={presenter.dispatchTone(incident.dispatch_status)}>{presenter.dispatchLabel(incident.dispatch_status, incident.notified)}</StatusBadge></td>
                <td>{incident.recipients.length > 0 ? incident.recipients.join(", ") : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {incidents.length === 0 && <p className={styles.empty}>No hay incidencias para este filtro.</p>}
      </div>
    </Card>
  );
}
