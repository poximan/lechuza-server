import { Button } from "@servicoop/frontend-foundation";
import { useMemo, useState } from "react";

import { JsonContractReader } from "../contracts/JsonContractReader";
import type { JsonRecord } from "../models";
import styles from "../pages/Pages.module.css";

const reader = new JsonContractReader();

interface Point {
  timestamp: number;
  iso: string;
  value: number;
}

export function MetricHistoryChart({
  history,
  metric,
  label,
}: {
  history: JsonRecord;
  metric: string;
  label: string;
}) {
  const [hours, setHours] = useState<number | null>(null);
  const allPoints = useMemo(
    () =>
      reader
        .records(history[metric] ?? [], `proxmox.history.${metric}`)
        .map((item, index) => {
          const iso = reader.string(
            item.ts,
            `proxmox.history.${metric}[${index}].ts`,
          );
          const timestamp = new Date(iso).getTime();
          if (!Number.isFinite(timestamp))
            throw new Error(
              `Contrato inválido: ${metric}[${index}].ts no es ISO-8601`,
            );
          return {
            iso,
            timestamp,
            value: reader.number(
              item.value,
              `proxmox.history.${metric}[${index}].value`,
            ),
          };
        })
        .sort((left, right) => left.timestamp - right.timestamp),
    [history, metric],
  );
  const points = useMemo(() => {
    if (hours === null || allPoints.length === 0) return allPoints;
    const lastPoint = allPoints.at(-1);
    if (!lastPoint) return allPoints;
    return allPoints.filter(
      (point) => point.timestamp >= lastPoint.timestamp - hours * 3_600_000,
    );
  }, [allPoints, hours]);
  if (points.length === 0)
    return <p className={styles.muted}>Sin datos históricos de {label}.</p>;
  const firstPoint = points[0];
  const lastPoint = points.at(-1);
  if (!firstPoint || !lastPoint)
    throw new Error(`Contrato inválido: histórico ${metric} vacío`);
  const minTime = firstPoint.timestamp;
  const maxTime = Math.max(minTime + 1, lastPoint.timestamp);
  const coordinates = points.map((point) => ({
    ...point,
    x: 45 + ((point.timestamp - minTime) / (maxTime - minTime)) * 530,
    y: 155 - Math.max(0, Math.min(100, point.value)) * 1.25,
  }));
  const polyline = coordinates
    .map((point) => `${point.x},${point.y}`)
    .join(" ");
  const firstCoordinate = coordinates[0];
  const lastCoordinate = coordinates.at(-1);
  if (!firstCoordinate || !lastCoordinate)
    throw new Error(`Contrato inválido: coordenadas ${metric} vacías`);
  const area = `M ${firstCoordinate.x} 155 L ${coordinates.map((point) => `${point.x} ${point.y}`).join(" L ")} L ${lastCoordinate.x} 155 Z`;
  return (
    <div className={styles.stack}>
      <div className={styles.toolbar}>
        <strong>{label}</strong>
        <div>
          {([6, 24, 168, null] as const).map((value) => (
            <Button
              key={value ?? "all"}
              onClick={() => setHours(value)}
              variant={hours === value ? "primary" : "ghost"}
            >
              {value === null ? "Todo" : value === 168 ? "7 d" : `${value} h`}
            </Button>
          ))}
        </div>
      </div>
      <svg
        aria-label={`Histórico de ${label}`}
        className={styles.chart}
        role="img"
        viewBox="0 0 600 180"
      >
        <line className={styles.chartGrid} x1="45" x2="575" y1="30" y2="30" />
        <line
          className={styles.chartGrid}
          x1="45"
          x2="575"
          y1="92.5"
          y2="92.5"
        />
        <line className={styles.chartGrid} x1="45" x2="575" y1="155" y2="155" />
        <text className={styles.chartLabel} x="8" y="34">
          100%
        </text>
        <text className={styles.chartLabel} x="14" y="96">
          50%
        </text>
        <text className={styles.chartLabel} x="25" y="159">
          0%
        </text>
        <path className={styles.chartArea} d={area} />
        <polyline points={polyline} />
        {coordinates.map((point, index) => (
          <circle
            cx={point.x}
            cy={point.y}
            fill="var(--sc-color-primary)"
            key={`${point.iso}-${index}`}
            r="3"
          >
            <title>
              {new Date(point.iso).toLocaleString("es-AR", {
                timeZone: "Etc/GMT+3",
              })}
              : {point.value.toFixed(2)}%
            </title>
          </circle>
        ))}
      </svg>
    </div>
  );
}
