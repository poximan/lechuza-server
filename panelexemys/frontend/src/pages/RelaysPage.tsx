import { Card, UtcMinusThreePresenter } from "@servicoop/frontend-foundation";
import { useState } from "react";

import { JsonContractReader } from "../contracts/JsonContractReader";
import { OperationalFormatter } from "../contracts/OperationalFormatter";
import { ToggleSwitch } from "../components/ToggleSwitch";
import type { PanelexemysApiClient } from "../PanelexemysApiClient";
import type { JsonRecord } from "../models";
import styles from "./Pages.module.css";

const reader = new JsonContractReader();
const formatter = new OperationalFormatter();
const time = new UtcMinusThreePresenter();

export function RelaysPage({
  client,
  data,
  onChanged,
}: {
  client: PanelexemysApiClient;
  data: JsonRecord;
  onChanged: () => Promise<void>;
}) {
  const enabled = reader.boolean(
    data.observer_enabled,
    "reles.observer_enabled",
  );
  const faults = reader.record(data.faults, "reles.faults");
  const items = reader.records(faults.items, "reles.faults.items");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function toggle(): Promise<void> {
    setPending(true);
    try {
      await client.setRelesObserver(!enabled);
      await onChanged();
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPending(false);
    }
  }
  return (
    <div className={styles.stack}>
      <div className={styles.relayControls}>
        <ToggleSwitch
          checked={enabled}
          disabled={pending}
          onChange={() => void toggle()}
          rightLabel="Observar Reles MiCOM"
        />
        {error && <p className={styles.error}>{error}</p>}
      </div>
      {items.length === 0 ? (
        <Card>
          <p>
            No hay relés activos configurados o con descripción 'NO APLICA'.
          </p>
        </Card>
      ) : (
        <div className={styles.relayGrid}>
          {items.map((item, index) => {
            const latest = reader.record(
              item.latest ?? {},
              `reles.faults.items[${index}].latest`,
            );
            const rows = [
              ["ID Modbus", item.id_modbus],
              ["Descripción", item.description],
              ["Número de falla", latest.numero_falla],
              [
                "Fecha/Hora",
                typeof latest.timestamp === "string"
                  ? time.formatInstant(latest.timestamp)
                  : "N/D",
              ],
              ["Corriente Fase A", latest.fasea_corr],
              ["Corriente Fase B", latest.faseb_corr],
              ["Corriente Fase C", latest.fasec_corr],
              ["Corriente Tierra", latest.tierra_corr],
            ];
            return (
              <Card
                className={styles.card}
                key={String(item.id_modbus ?? index)}
              >
                <div className={styles.tableWrap}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>Atributo</th>
                        <th>Valor</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map(([label, value]) => (
                        <tr key={String(label)}>
                          <td>{formatter.scalar(label)}</td>
                          <td>
                            <strong>{formatter.scalar(value)}</strong>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
