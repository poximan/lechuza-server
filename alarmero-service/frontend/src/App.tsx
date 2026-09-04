import { AppShell, StatusBadge } from "@servicoop/frontend-foundation";
import { useMemo, useState } from "react";

import { AlarmPresenter } from "./AlarmPresenter";
import type { IncidentFilter } from "./AlarmModels";
import styles from "./App.module.css";
import { ClearanceTable } from "./components/ClearanceTable";
import { FilterBar } from "./components/FilterBar";
import { FrequencyPanel } from "./components/FrequencyPanel";
import { IncidentsTable } from "./components/IncidentsTable";
import { NotificationSettings } from "./components/NotificationSettings";
import { SummaryGrid } from "./components/SummaryGrid";
import { useAlarmeroData } from "./useAlarmeroData";

export function App() {
  const [filter, setFilter] = useState<IncidentFilter>("active");
  const presenter = useMemo(() => new AlarmPresenter(), []);
  const { error, loading, snapshot } = useAlarmeroData(filter);

  return (
    <AppShell productName="lechuza-server" sectionName="Alarmero">
      <main className={styles.main}>
        <header className={styles.introduction}>
          <div><p>lechuza-server</p><h1>Seguimiento de alarmas</h1><span>Incidencias, despachos y tiempos de despeje</span></div>
          <StatusBadge tone={snapshot?.health.sync.state === "ok" ? "success" : "warning"}>
            {snapshot?.health.sync.state === "ok" ? "Fuentes sincronizadas" : "Sincronización pendiente"}
          </StatusBadge>
        </header>

        {error && <div className={styles.error} role="alert"><strong>No se pudo actualizar Alarmero.</strong><span>{error}</span></div>}
        {loading && snapshot === null && <p className={styles.loading}>Cargando información operativa…</p>}

        {snapshot && (
          <>
            <SummaryGrid
              conditions={snapshot.dashboard.conditions}
              counts={snapshot.dashboard.counts}
            />
            <IncidentsTable
              incidents={snapshot.incidents}
              presenter={presenter}
              referenceNow={snapshot.health.generated_at}
              toolbar={<FilterBar onSelect={setFilter} selected={filter} />}
            />
            <NotificationSettings />
            <div className={styles.dashboardGrid}>
              <FrequencyPanel items={snapshot.dashboard.frequent} />
              <ClearanceTable items={snapshot.dashboard.clearance} presenter={presenter} />
            </div>
          </>
        )}
      </main>
    </AppShell>
  );
}
