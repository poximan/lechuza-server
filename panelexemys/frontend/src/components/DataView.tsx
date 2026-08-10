import { Card } from "@servicoop/frontend-foundation";

import type { JsonRecord, JsonValue } from "../models";
import styles from "../App.module.css";

function isRecord(value: JsonValue): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function label(value: string): string {
  return value.replaceAll("_", " ");
}

function scalar(value: Exclude<JsonValue, JsonRecord | JsonValue[]>): string {
  if (value === null) return "N/D";
  if (typeof value === "boolean") return value ? "sí" : "no";
  return String(value);
}

export function DataView({ data }: { data: JsonRecord }) {
  return <div className={styles.dataGrid}>{Object.entries(data).map(([key, value]) => <ValueCard key={key} name={key} value={value} />)}</div>;
}

function ValueCard({ name, value }: { name: string; value: JsonValue }) {
  if (Array.isArray(value)) {
    return (
      <Card className={styles.dataCard}>
        <h2>{label(name)}</h2>
        {value.length === 0 ? <p className={styles.muted}>Sin datos</p> : (
          <div className={styles.list}>{value.map((item, index) => (
            <div className={styles.listItem} key={`${name}-${index}`}>
              {isRecord(item) ? <RecordTable data={item} /> : <span>{Array.isArray(item) ? item.map(String).join(", ") : scalar(item)}</span>}
            </div>
          ))}</div>
        )}
      </Card>
    );
  }
  if (isRecord(value)) {
    return <Card className={styles.dataCard}><h2>{label(name)}</h2><RecordTable data={value} /></Card>;
  }
  return <Card className={styles.metricCard}><span>{label(name)}</span><strong>{scalar(value)}</strong></Card>;
}

function RecordTable({ data }: { data: JsonRecord }) {
  return (
    <div className={styles.recordTable}>{Object.entries(data).map(([key, value]) => (
      <div className={styles.recordRow} key={key}>
        <span>{label(key)}</span>
        {isRecord(value) || Array.isArray(value)
          ? <code>{JSON.stringify(value)}</code>
          : <strong>{scalar(value)}</strong>}
      </div>
    ))}</div>
  );
}
