import { FLOW_WINDOWS } from "./FlowContract";
import type { FlowWindow } from "./FlowContract";
import { flowTimeUnit, flowVolumeUnit } from "./FlowUnits";
import type { FlowTimeUnit, FlowVolumeUnit } from "./FlowUnits";

const STORAGE_KEY = "lechu:caudalimetros:preferences";

export interface FlowPreferences {
  locationId: string | null;
  windowName: FlowWindow;
  volume: FlowVolumeUnit;
  period: FlowTimeUnit;
  view: { start: number; end: number } | null;
}

export const DEFAULT_FLOW_PREFERENCES: Readonly<FlowPreferences> = {
  locationId: null, windowName: "2d", volume: "l", period: "s", view: null,
};

function record(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Preferencias de caudalímetros inválidas");
  }
  return value as Record<string, unknown>;
}

export function readFlowPreferences(): FlowPreferences {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === null) return { ...DEFAULT_FLOW_PREFERENCES };
  const data = record(JSON.parse(stored));
  const windowName = FLOW_WINDOWS.find(([name]) => name === data.windowName)?.[0];
  if (data.version !== 1 || !windowName
    || !(data.locationId === null || typeof data.locationId === "string" && data.locationId.trim().length > 0)
    || typeof data.volume !== "string" || typeof data.period !== "string") {
    throw new Error("Preferencias de caudalímetros inválidas");
  }
  let view: FlowPreferences["view"] = null;
  if (data.view !== null) {
    const candidate = record(data.view);
    if (data.locationId === null || typeof candidate.start !== "number" || typeof candidate.end !== "number"
      || !Number.isFinite(candidate.start) || !Number.isFinite(candidate.end) || candidate.start >= candidate.end
      || Math.abs(candidate.start) > 8.64e15 || Math.abs(candidate.end) > 8.64e15) {
      throw new Error("Ventana guardada de caudalímetros inválida");
    }
    view = { start: candidate.start, end: candidate.end };
  }
  return { locationId: data.locationId, windowName, volume: flowVolumeUnit(data.volume), period: flowTimeUnit(data.period), view };
}

export function writeFlowPreferences(preferences: FlowPreferences): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, ...preferences }));
}
