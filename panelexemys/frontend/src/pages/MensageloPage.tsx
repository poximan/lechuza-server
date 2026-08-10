import { Card, UtcMinusThreePresenter } from "@servicoop/frontend-foundation";

import { JsonContractReader } from "../contracts/JsonContractReader";
import { OperationalFormatter } from "../contracts/OperationalFormatter";
import type { JsonRecord } from "../models";
import styles from "./Pages.module.css";

const reader = new JsonContractReader();
const formatter = new OperationalFormatter();
const time = new UtcMinusThreePresenter();

export function MensageloPage({ data }: { data: JsonRecord }) {
  const items = reader.records(data.items, "mensagelo.items");
  return (
    <Card>
      <div className={styles.cardHeader}>
        <h2>Últimos intentos de envío</h2>
      </div>
      {items.length === 0 ? (
        <p>Sin intentos registrados desde el último reinicio.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Éxito</th>
                <th>Destinatarios</th>
                <th>Tipo</th>
                <th>Asunto</th>
                <th>Mensaje</th>
                <th>Detalle</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={`${String(item.ts)}-${index}`}>
                  <td>
                    {typeof item.ts === "string"
                      ? time.formatInstant(item.ts)
                      : "N/D"}
                  </td>
                  <td>{item.ok === true ? "si" : "no"}</td>
                  <td>
                    {Array.isArray(item.recipients)
                      ? item.recipients.map(String).join(", ")
                      : "N/D"}
                  </td>
                  <td>{formatter.scalar(item.message_type)}</td>
                  <td>{formatter.scalar(item.subject)}</td>
                  <td className={styles.preWrap}>
                    {formatter.scalar(item.body)}
                  </td>
                  <td className={styles.preWrap}>
                    {formatter.scalar(item.detail)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
