import { useEffect, useMemo, useState } from "react";

import type { PanelexemysApiClient } from "../PanelexemysApiClient";
import type { JsonRecord, JsonValue } from "../models";
import styles from "./RelayDisturbanceChart.module.css";

interface Waveform {
  recordNumber: number;
  preSeconds: number;
  postSeconds: number;
  sampleRateHz: number;
  origin: string;
  channels: Record<ChannelName, number[]>;
}

type ChannelName = "phase_a" | "phase_b" | "phase_c" | "earth";

const channelDefinitions: Array<{
  key: ChannelName;
  label: string;
  color: string;
}> = [
  { key: "phase_a", label: "IA", color: "#e74c3c" },
  { key: "phase_b", label: "IB", color: "#f1c40f" },
  { key: "phase_c", label: "IC", color: "#3498db" },
  { key: "earth", label: "IE", color: "#2ecc71" },
];

function numericArray(value: JsonValue | undefined, context: string): number[] {
  if (!Array.isArray(value)) {
    throw new Error(`${context} debe ser una lista`);
  }
  return value.map((item, index) => {
    if (typeof item !== "number" || !Number.isFinite(item)) {
      throw new Error(`${context}[${index}] debe ser numérico`);
    }
    return item;
  });
}

function requiredNumber(value: JsonValue | undefined, context: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${context} debe ser numérico`);
  }
  return value;
}

function requiredRecord(value: JsonValue | undefined, context: string): JsonRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${context} debe ser un objeto`);
  }
  return value;
}

function parseWaveform(payload: JsonRecord): Waveform {
  const channels = requiredRecord(payload.channels, "perturbación.channels");
  const metadata = requiredRecord(payload.metadata, "perturbación.metadata");
  const origin = metadata.start_origin;
  if (typeof origin !== "string") {
    throw new Error("perturbación.metadata.start_origin debe ser texto");
  }
  const parsed: Waveform = {
    recordNumber: requiredNumber(
      payload.record_number,
      "perturbación.record_number",
    ),
    preSeconds: requiredNumber(payload.pre_seconds, "perturbación.pre_seconds"),
    postSeconds: requiredNumber(payload.post_seconds, "perturbación.post_seconds"),
    sampleRateHz: requiredNumber(
      payload.sample_rate_hz,
      "perturbación.sample_rate_hz",
    ),
    origin,
    channels: {
      phase_a: numericArray(channels.phase_a, "perturbación.channels.phase_a"),
      phase_b: numericArray(channels.phase_b, "perturbación.channels.phase_b"),
      phase_c: numericArray(channels.phase_c, "perturbación.channels.phase_c"),
      earth: numericArray(channels.earth, "perturbación.channels.earth"),
    },
  };
  if (
    !Number.isInteger(parsed.recordNumber)
    || parsed.recordNumber < 1
    || parsed.recordNumber > 5
  ) {
    throw new Error("perturbación.record_number debe estar entre 1 y 5");
  }
  const lengths = Object.values(parsed.channels).map((values) => values.length);
  if (lengths.some((length) => length === 0 || length !== lengths[0])) {
    throw new Error("Los canales de la perturbación no tienen la misma longitud");
  }
  return parsed;
}

function envelope(values: number[], pointCount = 700): Array<[number, number]> {
  if (values.length <= pointCount) {
    return values.map((value, index) => [index, value]);
  }
  const result: Array<[number, number]> = [];
  const bucketSize = values.length / pointCount;
  for (let bucket = 0; bucket < pointCount; bucket += 1) {
    const start = Math.floor(bucket * bucketSize);
    const end = Math.min(values.length, Math.floor((bucket + 1) * bucketSize));
    let minimumIndex = start;
    let maximumIndex = start;
    for (let index = start + 1; index < end; index += 1) {
      if ((values[index] ?? 0) < (values[minimumIndex] ?? 0)) minimumIndex = index;
      if ((values[index] ?? 0) > (values[maximumIndex] ?? 0)) maximumIndex = index;
    }
    const indexes = minimumIndex < maximumIndex
      ? [minimumIndex, maximumIndex]
      : [maximumIndex, minimumIndex];
    for (const index of indexes) result.push([index, values[index] ?? 0]);
  }
  return result;
}

export function RelayDisturbanceChart({
  client,
  relayId,
}: {
  client: PanelexemysApiClient;
  relayId: number;
}) {
  const [waveform, setWaveform] = useState<Waveform | null>(null);
  const [message, setMessage] = useState("Leyendo la perturbación más reciente…");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let retryTimer: number | null = null;
    setMessage("Leyendo la perturbación más reciente…");
    void client
      .relayLatestDisturbance(relayId, controller.signal)
      .then((payload) => {
        const status = payload.status;
        if (
          status !== "available"
          && status !== "pending"
          && status !== "unavailable"
        ) {
          throw new Error(
            `Contrato inválido: estado de perturbación desconocido ${String(status)}`,
          );
        }
        if (status !== "available") {
          setWaveform(null);
          setMessage(
            typeof payload.message === "string"
              ? payload.message
              : "La perturbación todavía no está disponible.",
          );
          retryTimer = window.setTimeout(
            () => setRetry((value) => value + 1),
            5000,
          );
          return;
        }
        setWaveform(parseWaveform(payload));
        setMessage("");
        retryTimer = window.setTimeout(
          () => setRetry((value) => value + 1),
          10000,
        );
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setWaveform(null);
          setMessage(reason instanceof Error ? reason.message : String(reason));
          retryTimer = window.setTimeout(
            () => setRetry((value) => value + 1),
            5000,
          );
        }
      });
    return () => {
      controller.abort();
      if (retryTimer !== null) window.clearTimeout(retryTimer);
    };
  }, [client, relayId, retry]);

  const drawing = useMemo(() => {
    if (waveform === null) return null;
    let maximum = 1;
    for (const values of Object.values(waveform.channels)) {
      for (const value of values) maximum = Math.max(maximum, Math.abs(value));
    }
    const width = 1000;
    const height = 330;
    const left = 56;
    const right = 16;
    const top = 18;
    const bottom = 34;
    const plotWidth = width - left - right;
    const plotHeight = height - top - bottom;
    const sampleCount = waveform.channels.phase_a.length;
    const x = (index: number) => left + (index / (sampleCount - 1)) * plotWidth;
    const y = (value: number) => top + ((maximum - value) / (2 * maximum)) * plotHeight;
    return {
      width,
      height,
      left,
      right,
      top,
      bottom,
      plotWidth,
      plotHeight,
      maximum,
      zeroX:
        left
        + (waveform.preSeconds / (waveform.preSeconds + waveform.postSeconds))
          * plotWidth,
      paths: channelDefinitions.map((channel) => ({
        ...channel,
        points: envelope(waveform.channels[channel.key])
          .map(([index, value]) => `${x(index).toFixed(2)},${y(value).toFixed(2)}`)
          .join(" "),
      })),
    };
  }, [waveform]);

  if (waveform === null || drawing === null) {
    return (
      <section className={styles.container} aria-label="Osciloperturbograma">
        <div className={styles.header}>
          <strong>Osciloperturbograma</strong>
        </div>
        <p className={styles.message}>{message}</p>
      </section>
    );
  }

  return (
    <section className={styles.container} aria-label="Osciloperturbograma">
      <div className={styles.header}>
        <strong>
          Osciloperturbograma · registro {waveform.recordNumber} · −
          {waveform.preSeconds.toFixed(1)} s / +
          {waveform.postSeconds.toFixed(1)} s
        </strong>
        <span>{waveform.sampleRateHz} muestras/s · t=0: {waveform.origin}</span>
      </div>
      <div className={styles.legend}>
        {drawing.paths.map((channel) => (
          <span key={channel.key} style={{ color: channel.color }}>
            <i style={{ backgroundColor: channel.color }} />{channel.label}
          </span>
        ))}
      </div>
      <svg
        className={styles.chart}
        viewBox={`0 0 ${drawing.width} ${drawing.height}`}
        role="img"
        aria-label="Corrientes de fase y tierra alrededor de la falla"
      >
        <line
          className={styles.axis}
          x1={drawing.left}
          x2={drawing.width - drawing.right}
          y1={drawing.top + drawing.plotHeight / 2}
          y2={drawing.top + drawing.plotHeight / 2}
        />
        <line
          className={styles.trigger}
          x1={drawing.zeroX}
          x2={drawing.zeroX}
          y1={drawing.top}
          y2={drawing.height - drawing.bottom}
        />
        {drawing.paths.map((channel) => (
          <polyline
            key={channel.key}
            fill="none"
            points={channel.points}
            stroke={channel.color}
            strokeWidth="1.4"
            vectorEffect="non-scaling-stroke"
          />
        ))}
        <text className={styles.label} x={drawing.left} y={drawing.height - 8}>
          −{waveform.preSeconds.toFixed(1)} s
        </text>
        <text className={styles.label} x={drawing.zeroX} y={drawing.height - 8} textAnchor="middle">0</text>
        <text className={styles.label} x={drawing.width - drawing.right} y={drawing.height - 8} textAnchor="end">
          +{waveform.postSeconds.toFixed(1)} s
        </text>
        <text className={styles.label} x={drawing.left - 8} y={drawing.top + 8} textAnchor="end">{drawing.maximum.toFixed(1)} A</text>
        <text className={styles.label} x={drawing.left - 8} y={drawing.height - drawing.bottom} textAnchor="end">−{drawing.maximum.toFixed(1)} A</text>
      </svg>
    </section>
  );
}
