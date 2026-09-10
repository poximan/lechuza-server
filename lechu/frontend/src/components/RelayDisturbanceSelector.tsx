import { useEffect, useId, useState } from "react";
import type { LechuApiClient } from "../LechuApiClient";
import { formatRelayTimestamp } from "../relayTime";
import { RelayDisturbanceChart } from "./RelayDisturbanceChart";

interface RecordSummary { recordNumber: number; timestamp: string }

export function RelayDisturbanceSelector({ client, relayId }: { client: LechuApiClient; relayId: number }) {
  const inputId = useId();
  const [records, setRecords] = useState<RecordSummary[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    setSelected("");
    setRecords([]);
    setLoaded(false);
    const refresh = async () => {
      try {
        const payload = await client.relayDisturbances(relayId, controller.signal);
        if (controller.signal.aborted) return;
        if (!Array.isArray(payload.items)) throw new Error("Lista de osciloperturbogramas inválida");
        const items = payload.items.map((item): RecordSummary => {
          if (!item || typeof item !== "object" || Array.isArray(item)
              || typeof item.record_number !== "number" || !Number.isInteger(item.record_number)
              || item.record_number < 1 || item.record_number > 5
              || typeof item.timestamp !== "string" || !item.timestamp.endsWith("Z")
              || Number.isNaN(Date.parse(item.timestamp)))
            throw new Error("Metadatos de osciloperturbograma inválidos");
          return { recordNumber: item.record_number, timestamp: item.timestamp };
        });
        setRecords(items);
        setSelected((previous) => items.some((item) => `${item.recordNumber}:${item.timestamp}` === previous) ? previous : "");
        const state = payload.refresh;
        setRefreshError(state && typeof state === "object" && !Array.isArray(state) && typeof state.error === "string" ? state.error : null);
        setLoaded(true);
        setError(null);
      } catch (reason) {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : String(reason));
      } finally {
        if (!controller.signal.aborted) timer = window.setTimeout(() => void refresh(), 30_000);
      }
    };
    void refresh();
    return () => {
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [client, relayId]);
  const record = records.find((item) => `${item.recordNumber}:${item.timestamp}` === selected);
  return <section aria-label="Osciloperturbogramas del relé">
    <label htmlFor={inputId}>Evento registrado</label>{" "}
    <select id={inputId} value={selected} onChange={(event) => setSelected(event.target.value)}>
      <option value="">Seleccionar osciloperturbograma</option>
      {records.map((item) => <option key={`${item.recordNumber}:${item.timestamp}`} value={`${item.recordNumber}:${item.timestamp}`}>
        {formatRelayTimestamp(item.timestamp)} · registro {item.recordNumber}
      </option>)}
    </select>
    {error && <p role="alert">{error}</p>}
    {refreshError && <p role="status">Descarga incompleta: {refreshError}. Se conservan las capturas disponibles.</p>}
    {!loaded && !error && <p>Consultando capturas guardadas…</p>}
    {loaded && records.length === 0 && <p>No hay osciloperturbogramas descargados.</p>}
    {record && <RelayDisturbanceChart client={client} relayId={relayId} recordNumber={record.recordNumber} eventTimestamp={record.timestamp} />}
  </section>;
}
