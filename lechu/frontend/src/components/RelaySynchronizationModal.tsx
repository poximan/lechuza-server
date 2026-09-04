import { Button } from "@servicoop/frontend-foundation";
import { useEffect, useState } from "react";

import { JsonContractReader } from "../contracts/JsonContractReader";
import type { JsonRecord } from "../models";
import { formatRelayTimestamp, relayTimestampFormat } from "../relayTime";
import styles from "./RelaySynchronizationModal.module.css";

const reader = new JsonContractReader();

function calculationSummary(payload: JsonRecord): string {
  const calculation = reader.record(
    payload.current_calculation,
    "sincro.current_calculation",
  );
  if (calculation.status !== "available") {
    return typeof calculation.message === "string"
      ? calculation.message
      : "Escala no disponible";
  }
  return [
    `Fase ${reader.number(calculation.phase_primary_ct, "sincro.phase_primary_ct")}/${reader.number(calculation.phase_internal_ratio, "sincro.phase_internal_ratio")}`,
    `Tierra ${reader.number(calculation.earth_primary_ct, "sincro.earth_primary_ct")}/${reader.number(calculation.earth_internal_ratio, "sincro.earth_internal_ratio")}`,
  ].join(" · ");
}

export function RelaySynchronizationModal({
  description,
  onClose,
  relayId,
  request,
}: {
  description: string;
  onClose: () => void;
  relayId: number;
  request: Promise<JsonRecord>;
}) {
  const [snapshot, setSnapshot] = useState<JsonRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void request.then((payload) => {
      if (!active) return;
      setSnapshot(payload);
      setError(null);
    }).catch((reason: unknown) => {
      if (!active) return;
      setError(reason instanceof Error ? reason.message : String(reason));
    });
    return () => { active = false; };
  }, [request]);

  const rows = snapshot === null ? [] : [
    ["ID Modbus", reader.number(snapshot.id_modbus, "sincro.id_modbus")],
    ["Descripción", reader.string(snapshot.description, "sincro.description")],
    ["Equipo", reader.optionalString(snapshot.product, "sincro.product") ?? "N/D"],
    [
      "TS del relé",
      formatRelayTimestamp(reader.string(snapshot.timestamp, "sincro.timestamp")),
    ],
    ["Formato", relayTimestampFormat(snapshot.timestamp_format)],
    [
      "Frecuencia",
      snapshot.nominal_frequency_hz === null
        ? "N/D"
        : `${reader.number(snapshot.nominal_frequency_hz, "sincro.nominal_frequency_hz")} Hz`,
    ],
    ["Escala de corriente", calculationSummary(snapshot)],
  ];

  return (
    <div
      className={styles.backdrop}
      onPointerDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
    >
      <section
        aria-labelledby="relay-synchronization-title"
        aria-modal="true"
        className={styles.modal}
        role="dialog"
      >
        <header className={styles.header}>
          <div>
            <h2 id="relay-synchronization-title">Sincro · relé {relayId}</h2>
            <span>{description}</span>
          </div>
          <Button onClick={onClose} variant="ghost">Cerrar</Button>
        </header>
        {snapshot === null && error === null && (
          <p className={styles.message}>
            Leyendo <code>0x0800–0x0803</code>…
          </p>
        )}
        {error !== null && <p className={styles.error}>{error}</p>}
        {snapshot !== null && (
          <table className={styles.table}>
            <tbody>
              {rows.map(([label, value]) => (
                <tr key={String(label)}>
                  <th>{label}</th>
                  <td className={label === "TS del relé" ? styles.timestamp : undefined}>
                    <strong>{value}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
