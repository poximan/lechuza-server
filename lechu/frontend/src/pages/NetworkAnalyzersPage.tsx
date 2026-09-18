import { Card, UtcMinusThreePresenter } from "@servicoop/frontend-foundation";
import { JsonContractReader } from "../contracts/JsonContractReader";
import { OperationalFormatter } from "../contracts/OperationalFormatter";
import type { JsonRecord } from "../models";
import styles from "./Pages.module.css";

const reader = new JsonContractReader();
const formatter = new OperationalFormatter();
const time = new UtcMinusThreePresenter();

function amperes(group: JsonRecord, key: string) {
  const raw = group[key];
  return typeof raw === "number" ? `${raw.toFixed(2)} A` : "N/D";
}

function kiloValue(
  group: JsonRecord,
  key: string,
  unit: string,
  fractionDigits: number,
) {
  const raw = group[key];
  return typeof raw === "number"
    ? `${(raw / 1_000).toFixed(fractionDigits)} ${unit}`
    : "N/D";
}

export function NetworkAnalyzersPage({ data }: { data: JsonRecord }) {
  const items = reader.records(data.items, "analizadores.items");
  return (
    <div className={styles.relayGrid}>
      {items.map((item, index) => {
        const context = `analizadores.items[${index}]`;
        const analyzerId = reader.number(item.id, `${context}.id`);
        const description = reader.string(item.name, `${context}.name`);
        const ln =
          reader.optionalRecord(item.voltage_ln_v, `${context}.voltage_ln_v`)
          ?? {};
        const ll =
          reader.optionalRecord(item.voltage_ll_v, `${context}.voltage_ll_v`)
          ?? {};
        const current =
          reader.optionalRecord(item.current_a, `${context}.current_a`) ?? {};
        const power =
          reader.optionalRecord(item.total_power, `${context}.total_power`)
          ?? {};
        const ratios =
          reader.optionalRecord(
            item.transformer_ratios,
            `${context}.transformer_ratios`,
          )
          ?? {};
        const measuredAt = typeof item.measured_at === "string"
          ? time.formatInstant(item.measured_at)
          : "N/D";
        return (
          <Card className={styles.card} key={String(analyzerId)}>
            <div className={styles.cardHeader}>
              <h3>Analizador Janitza · {analyzerId}</h3>
              <strong>{formatter.scalar(item.status)}</strong>
            </div>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr><th>Atributo</th><th>Valor</th></tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Descripción</td>
                    <td><strong>{description}</strong></td>
                  </tr>
                  <tr>
                    <td>Última lectura</td>
                    <td><strong>{measuredAt}</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
            {item.error
              ? <p className={styles.error}>{formatter.scalar(item.error)}</p>
              : null}
            <div className={`${styles.tableWrap} ${styles.analyzerMeasurements}`}>
              <table className={styles.table}>
                <thead>
                  <tr><th>Magnitud</th><th>L1</th><th>L2</th><th>L3</th></tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Tensión L-N</td>
                    <td>{kiloValue(ln, "l1", "kV", 3)}</td>
                    <td>{kiloValue(ln, "l2", "kV", 3)}</td>
                    <td>{kiloValue(ln, "l3", "kV", 3)}</td>
                  </tr>
                  <tr>
                    <td>Tensión L-L</td>
                    <td>{kiloValue(ll, "l1_l2", "kV", 3)}</td>
                    <td>{kiloValue(ll, "l2_l3", "kV", 3)}</td>
                    <td>{kiloValue(ll, "l3_l1", "kV", 3)}</td>
                  </tr>
                  <tr>
                    <td>Corriente</td>
                    <td>{amperes(current, "l1")}</td>
                    <td>{amperes(current, "l2")}</td>
                    <td>{amperes(current, "l3")}</td>
                  </tr>
                  <tr className={styles.measurementGroup}>
                    <th colSpan={4}>Potencias totales</th>
                  </tr>
                  <tr>
                    <td>Potencia activa</td>
                    <td colSpan={3}>
                      {kiloValue(power, "active_w", "kW", 2)}
                    </td>
                  </tr>
                  <tr>
                    <td>Potencia reactiva</td>
                    <td colSpan={3}>
                      {kiloValue(power, "reactive_var", "KVAr", 2)}
                    </td>
                  </tr>
                  <tr>
                    <td>Potencia aparente</td>
                    <td colSpan={3}>
                      {kiloValue(power, "apparent_va", "kVA", 2)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p>
              Relaciones aplicadas: TC {formatter.scalar(
                ratios.current_primary_a,
              )} / {formatter.scalar(ratios.current_secondary_a)} A;{" "}
              TP {formatter.scalar(ratios.voltage_primary_v)} / {formatter.scalar(
                ratios.voltage_secondary_v,
              )} V
            </p>
          </Card>
        );
      })}
    </div>
  );
}
