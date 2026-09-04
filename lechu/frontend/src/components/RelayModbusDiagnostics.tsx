import { UtcMinusThreePresenter } from "@servicoop/frontend-foundation";
import { useEffect, useMemo, useState } from "react";

import { JsonContractReader } from "../contracts/JsonContractReader";
import type { JsonRecord } from "../models";
import styles from "./RelayModbusDiagnostics.module.css";

const reader = new JsonContractReader();

const statusLabels: Record<string, string> = {
  cantidad_invalida: "Cantidad inválida",
  datos_invalidos: "Datos inválidos",
  ok: "OK",
  sin_respuesta: "Sin respuesta",
};

export function RelayPollCountdown({
  enabled,
  nextPollTimestamp,
  pollInProgress,
}: {
  enabled: boolean;
  nextPollTimestamp: string | null;
  pollInProgress: boolean;
}) {
  const [now, setNow] = useState(() => Date.now());
  const deadline = useMemo(() => {
    if (nextPollTimestamp === null) return null;
    const value = new Date(nextPollTimestamp).getTime();
    if (!Number.isFinite(value)) {
      throw new Error(
        `Contrato inválido: fecha de próxima encuesta ${nextPollTimestamp}`,
      );
    }
    return value;
  }, [nextPollTimestamp]);

  useEffect(() => {
    if (!enabled || pollInProgress || deadline === null) return undefined;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [deadline, enabled, pollInProgress]);

  let label = "Observador pausado";
  if (enabled && pollInProgress) label = "Encuesta Modbus en curso";
  else if (enabled && deadline === null) label = "Programando próxima encuesta…";
  else if (enabled && deadline !== null) {
    const remainingSeconds = Math.max(0, Math.ceil((deadline - now) / 1000));
    label = remainingSeconds > 0
      ? `Próxima encuesta Modbus en ${remainingSeconds} s`
      : "Esperando el inicio de la próxima encuesta…";
  }

  return (
    <div className={styles.countdown} aria-live="polite">
      <span className={styles.pulse} />
      <strong>{label}</strong>
    </div>
  );
}

export function RelayModbusQueries({
  queries,
}: {
  queries: JsonRecord[];
}) {
  const time = useMemo(() => new UtcMinusThreePresenter(), []);
  if (queries.length === 0) {
    return (
      <section className={styles.queries}>
        <strong>Últimas consultas Modbus</strong>
        <p>Todavía no salió ninguna consulta para este relé.</p>
      </section>
    );
  }

  return (
    <section className={styles.queries}>
      <strong>Últimas consultas Modbus</strong>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Hora</th>
              <th>Dirección</th>
              <th>Palabras</th>
              <th>Resultado</th>
              <th>Duración</th>
            </tr>
          </thead>
          <tbody>
            {queries.map((query, index) => {
              const context = `reles.modbus_queries[${index}]`;
              const timestamp = reader.string(query.timestamp, `${context}.timestamp`);
              const address = reader.string(query.address, `${context}.address`);
              const count = reader.number(query.count, `${context}.count`);
              const receivedCount = reader.optionalNumber(
                query.received_count,
                `${context}.received_count`,
              );
              const physicalRequests = reader.optionalNumber(
                query.physical_requests,
                `${context}.physical_requests`,
              );
              const status = reader.string(query.status, `${context}.status`);
              const durationMs = reader.number(
                query.duration_ms,
                `${context}.duration_ms`,
              );
              const statusLabel = statusLabels[status];
              if (statusLabel === undefined) {
                throw new Error(`Contrato inválido: estado Modbus desconocido ${status}`);
              }
              return (
                <tr key={`${timestamp}:${address}:${index}`}>
                  <td>{time.formatInstant(timestamp)}</td>
                  <td><code>{address}</code></td>
                  <td>
                    {receivedCount === null
                      ? String(count)
                      : `${String(receivedCount)}/${String(count)}`}
                    {physicalRequests === null
                      ? ""
                      : ` (${String(physicalRequests)} ${physicalRequests === 1 ? "trama" : "tramas"})`}
                  </td>
                  <td
                    className={
                      status === "ok" ? styles.statusOk : styles.statusError
                    }
                  >
                    {statusLabel}
                  </td>
                  <td>{durationMs.toFixed(1)} ms</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
