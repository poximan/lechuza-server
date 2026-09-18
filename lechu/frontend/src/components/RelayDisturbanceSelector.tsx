import { useEffect, useId, useState } from "react";
import type { LechuApiClient } from "../LechuApiClient";
import { formatRelayTimestamp } from "../relayTime";
import { RelayDisturbanceChart } from "./RelayDisturbanceChart";
import styles from "./RelayDisturbanceSelector.module.css";

interface RecordSummary { recordNumber: number; timestamp: string }
type InventoryStatus =
  | "available"
  | "collecting"
  | "confirmed_empty"
  | "error"
  | "partial"
  | "pending";

const inventoryStatuses = new Set<InventoryStatus>([
  "available",
  "collecting",
  "confirmed_empty",
  "error",
  "partial",
  "pending",
]);

export function RelayDisturbanceSelector({
  client,
  relayId,
  showStatusDetails,
  statusDetailsId,
}: {
  client: LechuApiClient;
  relayId: number;
  showStatusDetails: boolean;
  statusDetailsId: string;
}) {
  const inputId = useId();
  const [records, setRecords] = useState<RecordSummary[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [inventoryStatus, setInventoryStatus] =
    useState<InventoryStatus>("pending");
  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    setSelected("");
    setRecords([]);
    setLoaded(false);
    setInventoryStatus("pending");
    const refresh = async () => {
      try {
        const payload = await client.relayDisturbances(
          relayId,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        if (!Array.isArray(payload.items)) {
          throw new Error("Lista de osciloperturbogramas inválida");
        }
        const items = payload.items.map((item): RecordSummary => {
          if (
            !item
            || typeof item !== "object"
            || Array.isArray(item)
            || typeof item.record_number !== "number"
            || !Number.isInteger(item.record_number)
            || item.record_number < 1
            || item.record_number > 5
            || typeof item.timestamp !== "string"
            || !item.timestamp.endsWith("Z")
            || Number.isNaN(Date.parse(item.timestamp))
          ) {
            throw new Error("Metadatos de osciloperturbograma inválidos");
          }
          return { recordNumber: item.record_number, timestamp: item.timestamp };
        });
        setRecords(items);
        setSelected((previous) => items.some(
          (item) => `${item.recordNumber}:${item.timestamp}` === previous,
        ) ? previous : "");
        const state = payload.refresh;
        const rawInventoryStatus = payload.inventory_status;
        if (
          typeof rawInventoryStatus !== "string"
          || !inventoryStatuses.has(rawInventoryStatus as InventoryStatus)
        ) {
          throw new Error("Estado de inventario de osciloperturbogramas inválido");
        }
        setInventoryStatus(rawInventoryStatus as InventoryStatus);
        setRefreshError(
          state
          && typeof state === "object"
          && !Array.isArray(state)
          && typeof state.error === "string"
            ? state.error
            : null,
        );
        setLoaded(true);
        setError(null);
      } catch (reason) {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      } finally {
        if (!controller.signal.aborted) {
          timer = window.setTimeout(() => void refresh(), 30_000);
        }
      }
    };
    void refresh();
    return () => {
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [client, relayId]);
  const record = records.find(
    (item) => `${item.recordNumber}:${item.timestamp}` === selected,
  );
  let statusMessage = `${String(records.length)} osciloperturbograma${
    records.length === 1 ? "" : "s"
  } disponible${records.length === 1 ? "" : "s"}.`;
  let statusIsError = false;
  if (error !== null) {
    statusMessage = error;
    statusIsError = true;
  } else if (!loaded) {
    statusMessage = "Consultando capturas guardadas…";
  } else if (inventoryStatus === "partial") {
    statusMessage = refreshError
      ? `Descarga parcial: ${refreshError}. Se muestran y conservan las capturas disponibles.`
      : "La descarga es parcial. Se muestran y conservan las capturas disponibles.";
  } else if (inventoryStatus === "pending") {
    statusMessage =
      "La recolección inicial de perturbaciones todavía está pendiente.";
  } else if (inventoryStatus === "collecting") {
    statusMessage =
      "La recolección inicial está en curso. Las capturas aparecen a medida que se validan.";
  } else if (inventoryStatus === "confirmed_empty") {
    statusMessage =
      "Sin gráfico: el relé respondió correctamente e informó que actualmente no conserva registros de perturbación en SRAM.";
  } else if (inventoryStatus === "error") {
    statusMessage = `Sin gráfico: no fue posible completar el inventario del relé${
      refreshError ? `: ${refreshError}` : "."
    }`;
    statusIsError = true;
  }
  return <section aria-label="Osciloperturbogramas del relé">
    <label htmlFor={inputId}>Evento registrado</label>{" "}
    <select
      id={inputId}
      onChange={(event) => setSelected(event.target.value)}
      value={selected}
    >
      <option value="">Seleccionar osciloperturbograma</option>
      {records.map((item) => (
        <option
          key={`${item.recordNumber}:${item.timestamp}`}
          value={`${item.recordNumber}:${item.timestamp}`}
        >
          {formatRelayTimestamp(item.timestamp)} · registro {item.recordNumber}
        </option>
      ))}
    </select>
    <div
      className={styles.statusDetails}
      hidden={!showStatusDetails}
      id={statusDetailsId}
      role={statusIsError ? "alert" : "status"}
    >
      <strong>Estado de recolección</strong>
      <p>{statusMessage}</p>
    </div>
    {record && (
      <RelayDisturbanceChart
        client={client}
        eventTimestamp={record.timestamp}
        recordNumber={record.recordNumber}
        relayId={relayId}
      />
    )}
  </section>;
}
