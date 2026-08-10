import { useEffect, useMemo, useState } from "react";

import { AlarmeroApiClient } from "./AlarmeroApiClient";
import type { AlarmeroSnapshot, IncidentFilter } from "./AlarmModels";

export interface AlarmeroDataState {
  error: string | null;
  loading: boolean;
  snapshot: AlarmeroSnapshot | null;
}

const REFRESH_MILLISECONDS = 20_000;

export function useAlarmeroData(filter: IncidentFilter): AlarmeroDataState {
  const client = useMemo(() => new AlarmeroApiClient(new URL("./", document.baseURI)), []);
  const [state, setState] = useState<AlarmeroDataState>({ error: null, loading: true, snapshot: null });

  useEffect(() => {
    let active = true;
    let timer: number | null = null;
    const controller = new AbortController();

    const refresh = async () => {
      try {
        const [incidents, dashboard, health] = await Promise.all([
          client.getIncidents(filter, controller.signal),
          client.getDashboard(controller.signal),
          client.getHealth(controller.signal),
        ]);
        if (active) {
          setState({ error: null, loading: false, snapshot: { incidents, dashboard, health } });
        }
      } catch (error) {
        if (active) {
          const message = error instanceof Error ? error.message : "Error desconocido al actualizar Alarmero";
          setState((current) => ({ ...current, error: message, loading: false }));
        }
      } finally {
        if (active) {
          timer = window.setTimeout(() => void refresh(), REFRESH_MILLISECONDS);
        }
      }
    };

    void refresh();
    return () => {
      active = false;
      controller.abort();
      if (timer !== null) {
        window.clearTimeout(timer);
      }
    };
  }, [client, filter]);

  return state;
}
