import { FLOW_RATE_STREAM } from "./FlowContract";
import type { Measurement } from "./FlowContract";

export type FlowVolumeUnit = "l" | "m3";
export type FlowTimeUnit = "s" | "h" | "d";

const litresPerVolume: Record<FlowVolumeUnit, number> = { l: 1, m3: 1000 };
const secondsPerPeriod: Record<FlowTimeUnit, number> = { s: 1, h: 3600, d: 86400 };

export function flowVolumeUnit(value: string): FlowVolumeUnit {
  if (value !== "l" && value !== "m3") throw new Error("Unidad de volumen inválida");
  return value;
}

export function flowTimeUnit(value: string): FlowTimeUnit {
  if (value !== "s" && value !== "h" && value !== "d") throw new Error("Unidad de tiempo inválida");
  return value;
}

export function flowUnitLabel(volume: FlowVolumeUnit, period: FlowTimeUnit): string {
  return `${volume === "m3" ? "m³" : "l"}/${period}`;
}

export function presentFlowMeasurements(
  items: Measurement[],
  volume: FlowVolumeUnit,
  period: FlowTimeUnit,
): Measurement[] {
  const factor = secondsPerPeriod[period] / litresPerVolume[volume];
  const unit = flowUnitLabel(volume, period);
  const scale = (value: number): number => {
    const converted = value * factor;
    if (!Number.isFinite(converted)) throw new Error("El caudal convertido está fuera de rango");
    return converted;
  };
  const statistic = (value: number | null): number | null => value === null ? null : scale(value);
  return items.map(item => {
    if (item.stream !== FLOW_RATE_STREAM) return item;
    if (item.unit !== "l/s" && item.unit !== "L/s") {
      throw new Error(`La conversión de caudal requiere datos en l/s; GWF informó ${item.unit}`);
    }
    return {
      ...item,
      unit,
      value: scale(item.value),
      min: statistic(item.min),
      max: statistic(item.max),
      sd: statistic(item.sd),
    };
  });
}

export function formatMeasurementValue(value: number): string {
  return Math.abs(value) > 0 && Math.abs(value) < 1
    ? value.toLocaleString("es-AR", { maximumSignificantDigits: 3 })
    : value.toLocaleString("es-AR", { maximumFractionDigits: 3 });
}
