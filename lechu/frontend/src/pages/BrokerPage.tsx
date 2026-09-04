import {
  Card,
  StatusBadge,
  UtcMinusThreePresenter,
} from "@servicoop/frontend-foundation";
import { useState } from "react";

import { JsonContractReader } from "../contracts/JsonContractReader";
import { OperationalFormatter } from "../contracts/OperationalFormatter";
import { ToggleSwitch } from "../components/ToggleSwitch";
import type { LechuApiClient } from "../LechuApiClient";
import type { JsonRecord, JsonValue } from "../models";
import styles from "./Pages.module.css";

const reader = new JsonContractReader();
const formatter = new OperationalFormatter();
const time = new UtcMinusThreePresenter();

function OperationalTable({
  headers,
  rows,
}: {
  headers: string[];
  rows: JsonValue[][];
}) {
  if (rows.length === 0)
    return <p className={styles.muted}>Sin datos en memoria.</p>;
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {row.map((value, cell) => (
                <td key={`${index}-${cell}`}>{formatter.scalar(value)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Ranking({
  items,
  title,
  keyName,
  label,
  bytes = false,
}: {
  items: JsonRecord[];
  title: string;
  keyName: string;
  label: string;
  bytes?: boolean;
}) {
  return (
    <Card>
      <h2>{title}</h2>
      <OperationalTable
        headers={["Tópico", label]}
        rows={items
          .slice(0, 10)
          .map((item) => [
            item.topic ?? null,
            bytes
              ? formatter.bytes(item[keyName])
              : formatter.integer(item[keyName]),
          ])}
      />
    </Card>
  );
}

export function BrokerPage({
  client,
  data,
  onChanged,
}: {
  client: LechuApiClient;
  data: JsonRecord;
  onChanged: () => Promise<void>;
}) {
  const status = reader.string(data.status, "broker.status");
  const traffic = reader.record(data.traffic, "broker.traffic");
  const totals = reader.record(traffic.totals, "broker.traffic.totals");
  const topics = Array.isArray(traffic.active_topics)
    ? traffic.active_topics.map(String)
    : (() => {
        throw new Error(
          "Contrato inválido: broker.traffic.active_topics debe ser una lista",
        );
      })();
  const publishers = reader.records(
    traffic.publishers,
    "broker.traffic.publishers",
  );
  const subscriptions = reader.records(
    traffic.subscriptions,
    "broker.traffic.subscriptions",
  );
  const listeners = reader.records(
    traffic.listeners,
    "broker.traffic.listeners",
  );
  const recent = reader.records(traffic.recent, "broker.traffic.recent");
  const connected = status === "conectado" || status === "conectando";
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function toggle(): Promise<void> {
    setPending(true);
    try {
      await client.setBrokerConnection(!connected);
      await onChanged();
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPending(false);
    }
  }
  const subscriberRows: JsonValue[][] = [
    ...subscriptions.map((item) => [
      item.source ?? null,
      "suscripción",
      item.topic ?? null,
      `qos ${formatter.scalar(item.qos)}`,
    ]),
    ...listeners.map((item) => [
      item.source ?? null,
      "listener",
      item.prefix ?? null,
      "prefijo local",
    ]),
  ].slice(0, 16);
  return (
    <div className={styles.stack}>
      <Card className={styles.brokerCommandBar}>
        <div className={styles.brokerCommandMain}>
          <ToggleSwitch
            checked={connected}
            disabled={pending}
            onChange={() => void toggle()}
            rightLabel="conectar al broker"
          />
          <StatusBadge
            tone={
              status === "conectado"
                ? "success"
                : status === "conectando"
                  ? "warning"
                  : "danger"
            }
          >
            {status}
          </StatusBadge>
        </div>
        <span className={styles.muted}>
          observación local del tráfico mqtt de lechu
        </span>
        {error && <p className={styles.error}>{error}</p>}
      </Card>
      <div className={styles.gridThree}>
        {[
          ["Estado cliente", status],
          ["Publicaciones", formatter.integer(totals.published_count)],
          ["Bytes publicados", formatter.bytes(totals.published_bytes)],
          ["Recepciones", formatter.integer(totals.received_count)],
          ["Bytes recibidos", formatter.bytes(totals.received_bytes)],
          ["Tópicos activos", formatter.integer(topics.length)],
        ].map(([label, value]) => (
          <Card className={styles.metric} key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </Card>
        ))}
      </div>
      <Card>
        <h2>Tópicos activos</h2>
        <div className={styles.topicCloud}>
          {topics.length === 0 ? (
            <span className={styles.muted}>Sin tópicos observados.</span>
          ) : (
            topics.slice(0, 48).map((topic) => <code key={topic}>{topic}</code>)
          )}
        </div>
      </Card>
      <div className={styles.grid}>
        <Card>
          <h2>Publicadores locales</h2>
          <OperationalTable
            headers={["Publicador", "Cantidad", "Bytes", "Último"]}
            rows={publishers
              .slice(0, 12)
              .map((item) => [
                item.source ?? null,
                formatter.integer(item.published_count),
                formatter.bytes(item.published_bytes),
                typeof item.last_publish_ts === "string"
                  ? time.formatInstant(item.last_publish_ts)
                  : "-",
              ])}
          />
        </Card>
        <Card>
          <h2>Suscriptores locales</h2>
          <OperationalTable
            headers={["Origen", "Tipo", "Tópico", "Detalle"]}
            rows={subscriberRows}
          />
        </Card>
        <Ranking
          items={reader.records(
            traffic.rank_publicaciones,
            "broker.rank_publicaciones",
          )}
          keyName="published_count"
          label="Publicaciones"
          title="Ranking por cantidad publicada"
        />
        <Ranking
          bytes
          items={reader.records(
            traffic.rank_payload_acumulado,
            "broker.rank_payload_acumulado",
          )}
          keyName="published_bytes"
          label="Bytes"
          title="Ranking por payload acumulado"
        />
        <Ranking
          bytes
          items={reader.records(
            traffic.rank_payload_maximo,
            "broker.rank_payload_maximo",
          )}
          keyName="published_max_bytes"
          label="Máximo"
          title="Ranking por payload máximo"
        />
        <Ranking
          items={reader.records(
            traffic.rank_recepciones,
            "broker.rank_recepciones",
          )}
          keyName="received_count"
          label="Recepciones"
          title="Ranking por recepciones"
        />
      </div>
      <Card>
        <h2>Seguimiento reciente</h2>
        <OperationalTable
          headers={[
            "Fecha",
            "Sentido",
            "Origen",
            "Tópico",
            "Bytes",
            "QoS",
            "Retain",
          ]}
          rows={recent
            .slice(0, 14)
            .map((item) => [
              typeof item.ts === "string" ? time.formatInstant(item.ts) : "-",
              item.direction ?? null,
              item.source ?? null,
              item.topic ?? null,
              formatter.bytes(item.bytes),
              item.qos === null ? "-" : `qos ${formatter.scalar(item.qos)}`,
              item.retain === null
                ? "-"
                : item.retain === true
                  ? "retain"
                  : "no retain",
            ])}
        />
      </Card>
    </div>
  );
}
