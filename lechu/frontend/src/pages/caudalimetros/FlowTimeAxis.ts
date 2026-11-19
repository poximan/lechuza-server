import { LOCAL_TIME_ZONE } from "./FlowContract";
import { periodStart, secondsPerPeriod } from "./FlowUnits";
import type { FlowTimeUnit } from "./FlowUnits";

export function timeTicks(start: number, end: number, period: FlowTimeUnit, limit: number): number[] {
  const base = secondsPerPeriod[period] * 1000;
  const minimum = Math.max(base, (end - start) / Math.max(1, limit - 1));
  const choices = period === "s"
    ? [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800, 604800]
    : period === "h" ? [1, 2, 3, 6, 12, 24, 48, 72, 168] : [1, 2, 3, 5, 7, 10, 14, 21, 28];
  const step = choices.map(value => value * base).find(value => value >= minimum)
    ?? Math.ceil(minimum / base) * base;
  const first = periodStart(start, step);
  const ticks: number[] = [];
  for (let time = first < start ? first + step : first; time <= end; time += step) ticks.push(time);
  return ticks;
}

export function tickLabels(time: number, period: FlowTimeUnit): { date: string; time: string } {
  const date = new Date(time);
  return {
    date: date.toLocaleDateString("es-AR", { timeZone: LOCAL_TIME_ZONE, day: "2-digit", month: "2-digit" }),
    time: period === "d" ? "" : date.toLocaleTimeString("es-AR", {
      timeZone: LOCAL_TIME_ZONE, hour: "2-digit", minute: "2-digit",
      ...(period === "s" ? { second: "2-digit" as const } : {}), hourCycle: "h23",
    }),
  };
}
