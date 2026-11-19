import { FLOW_RATE_STREAM, FLOW_VOLUME_STREAM, streams } from "./FlowContract";
import type { Measurement } from "./FlowContract";
import { flowInLitresPerSecond, litresPerVolume, periodStart, secondsPerPeriod, volumeUnitLabel } from "./FlowUnits";
import type { FlowTimeUnit, FlowVolumeUnit } from "./FlowUnits";

// Contrato del logger: una muestra cada quince minutos. No integrar muestras ausentes.
const MAX_SAMPLE_GAP_MS = 900_000 * 1.5;
const MAX_VOLUME_BARS = 2048;

export interface VolumeBin {
  start: number;
  end: number;
  value: number;
  coveredMilliseconds: number;
}

export interface SampleSeries {
  kind: "points-line" | "line";
  label: string;
  unit: string;
  items: Measurement[];
  maxGapMilliseconds: number;
}

export interface VolumeSeries {
  kind: "volume";
  label: string;
  unit: string;
  bins: VolumeBin[];
  periodsPerBar: number;
  total: number;
  coveredMilliseconds: number;
}

export type ChartSeries = SampleSeries | VolumeSeries;

export function sampleSeries(items: Measurement[], stream: string): SampleSeries {
  const selected = items.filter(item => item.stream === stream).sort((a, b) => a.time - b.time);
  return {
    kind: stream === FLOW_RATE_STREAM ? "points-line" : "line",
    label: streams[stream] ?? stream,
    unit: selected[0]?.unit ?? "",
    items: selected,
    maxGapMilliseconds: stream === FLOW_RATE_STREAM ? MAX_SAMPLE_GAP_MS : 7_200_000,
  };
}

export function integrateFlow(
  samples: Measurement[], start: number, end: number, volume: FlowVolumeUnit, period: FlowTimeUnit,
): VolumeSeries {
  const base = secondsPerPeriod[period] * 1000;
  // La aditividad de la integral permite agrupar sin crear millones de intervalos de un segundo.
  const periodsPerBar = Math.max(1, Math.ceil((end - start) / base / (MAX_VOLUME_BARS - 1)));
  const duration = base * periodsPerBar;
  const bins = new Map<number, VolumeBin>();
  let total = 0;
  let coveredMilliseconds = 0;
  for (let index = 1; index < samples.length; index++) {
    const before = samples[index - 1];
    const after = samples[index];
    if (!before || !after) continue;
    const elapsed = after.time - before.time;
    if (elapsed <= 0 || elapsed > MAX_SAMPLE_GAP_MS || after.time <= start || before.time >= end) continue;
    const firstValue = flowInLitresPerSecond(before);
    const lastValue = flowInLitresPerSecond(after);
    const valueAt = (time: number) => firstValue + (lastValue - firstValue) * ((time - before.time) / elapsed);
    const stop = Math.min(after.time, end);
    for (let cursor = Math.max(before.time, start); cursor < stop;) {
      const bucket = periodStart(cursor, duration);
      const next = Math.min(stop, bucket + duration);
      const amount = (valueAt(cursor) + valueAt(next)) / 2 * ((next - cursor) / 1000) / litresPerVolume[volume];
      if (!Number.isFinite(amount)) throw new Error("El volumen integrado está fuera de rango");
      const bin = bins.get(bucket) ?? { start: bucket, end: bucket + duration, value: 0, coveredMilliseconds: 0 };
      bin.value += amount;
      bin.coveredMilliseconds += next - cursor;
      bins.set(bucket, bin);
      total += amount;
      coveredMilliseconds += next - cursor;
      cursor = next;
    }
  }
  if (!Number.isFinite(total)) throw new Error("El volumen integrado está fuera de rango");
  return {
    kind: "volume", label: `${streams[FLOW_VOLUME_STREAM]} integrado`, unit: volumeUnitLabel(volume),
    bins: [...bins.values()].sort((a, b) => a.start - b.start), periodsPerBar, total, coveredMilliseconds,
  };
}
