import { JsonContractReader } from "../../contracts/JsonContractReader";
import type { JsonRecord } from "../../models";

const reader = new JsonContractReader();
export const streams: Record<string, string> = {
  "urn:mwp:datastream:flow-rate": "Caudal",
  "urn:mwp:datastream:flow-volume": "Volumen de caudal",
  "urn:mwp:datastream:battery-voltage": "Voltaje de batería",
  "urn:mwp:datastream:external-voltage": "Voltaje externo",
};
export interface Measurement {
  id: string; timestamp: string; time: number; stream: string; unit: string;
  value: number; min: number | null; max: number | null; sd: number | null;
}
export function measurements(payload: JsonRecord): Measurement[] {
  return reader.records(payload.items, "mediciones").map(item => {
    const timestamp = reader.string(item.timestamp, "timestamp");
    const time = Date.parse(timestamp);
    if (!Number.isFinite(time)) throw new Error("Fecha de medición inválida");
    const stream = reader.record(item.dataStream, "dataStream");
    return { id: reader.string(item.id, "id"), timestamp, time,
      stream: reader.string(stream.id, "stream.id"), unit: reader.string(stream.unit, "unit"),
      value: reader.number(item.value, "value"), min: reader.optionalNumber(item.min, "min"),
      max: reader.optionalNumber(item.max, "max"), sd: reader.optionalNumber(item.sd, "sd") };
  });
}
export function localTime(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "Sin datos";
  return new Date(value).toLocaleString("es-AR", { timeZone: "Etc/GMT+3", hour12: false });
}
export function inputTime(time: number): string {
  return new Date(time - 3 * 3_600_000).toISOString().slice(0, 16);
}
export function parseInput(value: string): number { return Date.parse(`${value}:00-03:00`); }
export function monthsBefore(time: number, months: number): number {
  const local = new Date(time - 3 * 3_600_000);
  const day = local.getUTCDate();
  local.setUTCDate(1);
  local.setUTCMonth(local.getUTCMonth() - months);
  const last = new Date(Date.UTC(local.getUTCFullYear(), local.getUTCMonth() + 1, 0)).getUTCDate();
  local.setUTCDate(Math.min(day, last));
  return local.getTime() + 3 * 3_600_000;
}
