import { UtcMinusThreePresenter } from "@servicoop/frontend-foundation";
import { useMemo } from "react";

import type { JsonRecord, JsonValue } from "../models";
import styles from "./OperationalTable.module.css";

export interface DisconnectedEquipmentTableProps {
  descriptions: JsonRecord;
  items: JsonValue[];
  referenceNow: string;
}

export function DisconnectedEquipmentTable({
  descriptions,
  items,
  referenceNow,
}: DisconnectedEquipmentTableProps) {
  const presenter = useMemo(() => new UtcMinusThreePresenter(), []);
  try {
    const rows = items.map((value, index) => {
      if (typeof value !== "object" || value === null || Array.isArray(value))
        throw new Error(`disconnected[${index}] debe ser un objeto`);
      const id = value.id_grd;
      const timestamp = value.last_disconnected_timestamp;
      if (
        typeof id !== "number" ||
        typeof timestamp !== "string" ||
        timestamp.length === 0
      )
        throw new Error(`disconnected[${index}] incompleto`);
      const description =
        typeof value.description === "string"
          ? value.description
          : String(descriptions[String(id)] ?? "");
      return { description, id, timestamp };
    });
    return (
      <div className={styles.wrapper}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Equipo</th>
              <th>Última caída</th>
              <th>Tiempo desconectado</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>
                  GRD {row.id}
                  {row.description ? ` · ${row.description}` : ""}
                </td>
                <td>{presenter.formatInstant(row.timestamp)}</td>
                <td>
                  {presenter.formatAge(row.timestamp, null, referenceNow)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  } catch (reason) {
    return (
      <p className={styles.error} role="alert">
        Contrato inválido:{" "}
        {reason instanceof Error ? reason.message : String(reason)}
      </p>
    );
  }
}
