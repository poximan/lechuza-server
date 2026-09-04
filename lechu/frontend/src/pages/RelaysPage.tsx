import { Button, Card } from "@servicoop/frontend-foundation";
import { useState } from "react";

import { JsonContractReader } from "../contracts/JsonContractReader";
import { OperationalFormatter } from "../contracts/OperationalFormatter";
import { ToggleSwitch } from "../components/ToggleSwitch";
import { RelayDisturbanceChart } from "../components/RelayDisturbanceChart";
import { RelaySynchronizationModal } from "../components/RelaySynchronizationModal";
import {
  RelayModbusQueries,
  RelayPollCountdown,
} from "../components/RelayModbusDiagnostics";
import type { LechuApiClient } from "../LechuApiClient";
import type { JsonRecord } from "../models";
import { formatRelayTimestamp, relayTimestampFormat } from "../relayTime";
import styles from "./Pages.module.css";

const reader = new JsonContractReader();
const formatter = new OperationalFormatter();

function current(
  rawValue: unknown,
  primaryCt: number | null,
  internalRatio: number | null,
  unavailableLabel: string,
): string {
  if (typeof rawValue !== "number" || !Number.isFinite(rawValue)) return "N/D";
  if (primaryCt === null || internalRatio === null) return unavailableLabel;
  return `${(rawValue * primaryCt / internalRatio).toFixed(2)} A`;
}

function positiveNumber(value: number, context: string): number {
  if (value <= 0) throw new Error(`Contrato inválido: ${context} debe ser positivo`);
  return value;
}

export function RelaysPage({
  client,
  data,
  onChanged,
  protectedMode,
}: {
  client: LechuApiClient;
  data: JsonRecord;
  onChanged: () => Promise<void>;
  protectedMode: boolean;
}) {
  const enabled = reader.boolean(
    data.observer_enabled,
    "reles.observer_enabled",
  );
  const faults = reader.record(data.faults, "reles.faults");
  const items = reader.records(faults.items, "reles.faults.items");
  const observerRuntime = reader.record(
    faults.observer_runtime,
    "reles.faults.observer_runtime",
  );
  const runtimeEnabled = reader.boolean(
    observerRuntime.enabled,
    "reles.faults.observer_runtime.enabled",
  );
  const pollInProgress = reader.boolean(
    observerRuntime.poll_in_progress,
    "reles.faults.observer_runtime.poll_in_progress",
  );
  const nextPollTimestamp = reader.optionalString(
    observerRuntime.next_poll_timestamp,
    "reles.faults.observer_runtime.next_poll_timestamp",
  );
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [synchronizingRelay, setSynchronizingRelay] = useState<{
    description: string;
    id: number;
    request: Promise<JsonRecord>;
  } | null>(null);
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
          disabled={pending || !protectedMode}
          onChange={() => void toggle()}
          rightLabel="Observar Reles MiCOM"
        />
        {!protectedMode && (
          <span className={styles.muted}>
            El estado puede consultarse en modo seguro; cambiar el observador
            requiere modo protegido.
          </span>
        )}
        <RelayPollCountdown
          enabled={runtimeEnabled}
          nextPollTimestamp={nextPollTimestamp}
          pollInProgress={pollInProgress}
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
            const relayId = reader.number(
              item.id_modbus,
              `reles.faults.items[${index}].id_modbus`,
            );
            const description = reader.string(
              item.description,
              `reles.faults.items[${index}].description`,
            );
            const queries = reader.records(
              item.modbus_queries,
              `reles.faults.items[${index}].modbus_queries`,
            );
            const latest = reader.record(
              item.latest ?? {},
              `reles.faults.items[${index}].latest`,
            );
            const faultNumber = reader.optionalNumber(
              latest.numero_falla,
              `reles.faults.items[${index}].latest.numero_falla`,
            );
            const faultTimestamp = reader.optionalString(
              latest.timestamp,
              `reles.faults.items[${index}].latest.timestamp`,
            );
            const calculation = reader.optionalRecord(
              latest.current_calculation,
              `reles.faults.items[${index}].latest.current_calculation`,
            );
            const calculationAvailable = calculation?.status === "available";
            const phasePrimaryCt = calculationAvailable
              ? positiveNumber(
                  reader.number(
                    calculation.phase_primary_ct,
                    `reles.faults.items[${index}].latest.current_calculation.phase_primary_ct`,
                  ),
                  `reles.faults.items[${index}].latest.current_calculation.phase_primary_ct`,
                )
              : null;
            const phaseInternalRatio = calculationAvailable
              ? positiveNumber(
                  reader.number(
                    calculation.phase_internal_ratio,
                    `reles.faults.items[${index}].latest.current_calculation.phase_internal_ratio`,
                  ),
                  `reles.faults.items[${index}].latest.current_calculation.phase_internal_ratio`,
                )
              : null;
            const earthPrimaryCt = calculationAvailable
              ? positiveNumber(
                  reader.number(
                    calculation.earth_primary_ct,
                    `reles.faults.items[${index}].latest.current_calculation.earth_primary_ct`,
                  ),
                  `reles.faults.items[${index}].latest.current_calculation.earth_primary_ct`,
                )
              : null;
            const earthInternalRatio = calculationAvailable
              ? positiveNumber(
                  reader.number(
                    calculation.earth_internal_ratio,
                    `reles.faults.items[${index}].latest.current_calculation.earth_internal_ratio`,
                  ),
                  `reles.faults.items[${index}].latest.current_calculation.earth_internal_ratio`,
                )
              : null;
            const calculationUnavailableLabel =
              calculation?.status === "unavailable"
                ? "Escala no disponible"
                : "Escala pendiente";
            const calculationDescription = calculationAvailable
              ? `Fase ${String(phasePrimaryCt)}/${String(phaseInternalRatio)} · Tierra ${String(earthPrimaryCt)}/${String(earthInternalRatio)}`
              : typeof calculation?.message === "string"
                ? calculation.message
                : calculationUnavailableLabel;
            const rows = [
              ["ID Modbus", item.id_modbus],
              ["Descripción", item.description],
              ["Número de falla", latest.numero_falla],
              [
                "TS",
                faultTimestamp !== null
                  ? `${formatRelayTimestamp(faultTimestamp)} (${relayTimestampFormat(
                      latest.timestamp_format,
                    )})`
                  : "N/D",
              ],
              ["Escala de corriente", calculationDescription],
              [
                "Corriente Fase A",
                current(
                  latest.phase_a_raw,
                  phasePrimaryCt,
                  phaseInternalRatio,
                  calculationUnavailableLabel,
                ),
              ],
              [
                "Corriente Fase B",
                current(
                  latest.phase_b_raw,
                  phasePrimaryCt,
                  phaseInternalRatio,
                  calculationUnavailableLabel,
                ),
              ],
              [
                "Corriente Fase C",
                current(
                  latest.phase_c_raw,
                  phasePrimaryCt,
                  phaseInternalRatio,
                  calculationUnavailableLabel,
                ),
              ],
              [
                "Corriente Tierra",
                current(
                  latest.earth_raw,
                  earthPrimaryCt,
                  earthInternalRatio,
                  calculationUnavailableLabel,
                ),
              ],
            ];
            return (
              <Card
                className={styles.card}
                key={String(relayId)}
              >
                <div className={styles.cardHeader}>
                  <h3>Relé MiCOM · {relayId}</h3>
                  <Button
                    onClick={() => setSynchronizingRelay({
                      description,
                      id: relayId,
                      request: client.readRelayClock(relayId),
                    })}
                    variant="ghost"
                  >
                    Sincro
                  </Button>
                </div>
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
                <RelayModbusQueries queries={queries} />
                <RelayDisturbanceChart
                  client={client}
                  faultNumber={faultNumber}
                  faultTimestamp={faultTimestamp}
                  relayId={relayId}
                />
              </Card>
            );
          })}
        </div>
      )}
      {synchronizingRelay !== null && (
        <RelaySynchronizationModal
          description={synchronizingRelay.description}
          onClose={() => setSynchronizingRelay(null)}
          relayId={synchronizingRelay.id}
          request={synchronizingRelay.request}
        />
      )}
    </div>
  );
}
