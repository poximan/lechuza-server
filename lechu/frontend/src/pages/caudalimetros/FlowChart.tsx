import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent } from "react";
import { localTime } from "./FlowContract";
import { formatMeasurementValue, periodLabels, periodStart, secondsPerPeriod } from "./FlowUnits";
import type { FlowTimeUnit } from "./FlowUnits";
import type { ChartSeries } from "./FlowSeries";
import { tickLabels, timeTicks } from "./FlowTimeAxis";
import styles from "./FlowMetersPage.module.css";

const LEFT = 60;
const RIGHT = 950;
const TOP = 25;
const BOTTOM = 165;

export function FlowChart({ series, start, end, period, overview = false }: {
  series: ChartSeries; start: number; end: number; period: FlowTimeUnit; overview?: boolean;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const [viewport, setViewport] = useState({ width: 1000, height: 112 });
  const { width, height } = viewport;
  const [hoverTime, setHoverTime] = useState<number | null>(null);
  useEffect(() => {
    const element = svg.current;
    if (!element) return;
    const observer = new ResizeObserver(entries => {
      const entry = entries[0];
      if (!entry || entry.contentRect.width <= 0 || entry.contentRect.height <= 0) return;
      const { width, height } = entry.contentRect;
      setViewport(current => current.width === width && current.height === height ? current : { width, height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => setHoverTime(null), [start, end, series]);
  const volume = series.kind === "volume" ? series : null;
  const visible = useMemo(() => series.kind === "volume" ? [] : series.items.filter(point => point.time >= start && point.time <= end), [series, start, end]);
  const values = volume ? volume.bins.map(bin => bin.value) : visible.map(point => point.value);
  const low = values.reduce((minimum, value) => Math.min(minimum, value), 0);
  const measuredHigh = values.reduce((maximum, value) => Math.max(maximum, value), 0);
  const high = measuredHigh === low ? low + 1 : measuredHigh;
  const left = LEFT;
  const right = overview ? Math.max(left + 1, width - 24) : RIGHT;
  const top = overview ? 8 : TOP;
  const bottom = overview ? Math.max(top + 1, height - 58) : BOTTOM;
  const x = (time: number) => left + (time - start) / Math.max(1, end - start) * (right - left);
  const y = (value: number) => bottom - (value - low) / (high - low) * (bottom - top);
  const plotWidth = overview ? right - left : width * (RIGHT - LEFT) / 1000;
  const ticks = timeTicks(start, end, period, Math.max(2, Math.min(10, Math.floor(plotWidth / 110))));
  const marks = useMemo(() => {
    const path = series.kind !== "volume" ? visible.map((point, index) => {
      const previous = visible[index - 1];
      const command = previous && point.time - previous.time <= series.maxGapMilliseconds ? "L" : "M";
      return `${command}${x(point.time).toFixed(2)},${y(point.value).toFixed(2)}`;
    }).join(" ") : "";
    return volume ? volume.bins.map(bin => {
      const left = x(Math.max(start, bin.start));
      const right = x(Math.min(end, bin.end));
      return <rect key={bin.start} x={left} width={Math.max(0, right - left) * 0.94}
        y={Math.min(y(0), y(bin.value)) - (bin.value === 0 ? 0.5 : 0)} height={Math.max(1, Math.abs(y(bin.value) - y(0)))}
        className={bin.coveredMilliseconds < bin.end - bin.start - 1 ? styles.partialBar : styles.volumeBar} />;
    }) : series.kind !== "volume" && <><path d={path} className={styles.line} />{visible.map((point, index) => series.kind === "points-line" || !visible[index - 1] || point.time - (visible[index - 1]?.time ?? point.time) > series.maxGapMilliseconds
      ? <circle key={point.id} cx={x(point.time)} cy={y(point.value)} r={overview ? 1.4 : 2.4} className={styles.point} /> : null)}</>;
  }, [series, volume, visible, start, end, low, high, overview, left, right, top, bottom]);
  const hover = hoverTime === null ? null : visible.reduce<typeof visible[number] | null>((nearest, point) =>
    !nearest || Math.abs(point.time - hoverTime) < Math.abs(nearest.time - hoverTime) ? point : nearest, null);
  const hoverBin = hoverTime === null ? null : volume?.bins.find(bin => hoverTime >= bin.start && hoverTime < bin.end) ?? null;
  const segmentDuration = volume && period !== "s" ? secondsPerPeriod[period] * 1000 * volume.periodsPerBar : null;
  const segmentStart = hoverTime !== null && segmentDuration !== null ? periodStart(hoverTime, segmentDuration) : null;
  const hoverSegment = segmentStart !== null && segmentDuration !== null ? { start: segmentStart, end: segmentStart + segmentDuration } : null;
  const cursorTime = hoverSegment ? null : hover?.time ?? (hoverBin ? Math.max(start, hoverBin.start) : null);
  const pointer = (event: PointerEvent<SVGSVGElement>) => {
    if (overview) return;
    const element = event.currentTarget;
    const matrix = element.getScreenCTM();
    if (!matrix) return;
    const local = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    const instant = start + Math.max(0, Math.min(1, (local.x - left) / (right - left))) * (end - start);
    setHoverTime(segmentDuration === null ? instant : periodStart(Math.min(instant, Math.max(start, end - 1)), segmentDuration));
  };
  const coverage = volume ? volume.coveredMilliseconds / Math.max(1, end - start) * 100 : 0;
  const readout = hoverBin
    ? `${hoverSegment ? "Intervalo: " : ""}${localTime(hoverBin.start)} – ${localTime(hoverBin.end)} · ${formatMeasurementValue(hoverBin.value)} ${series.unit} · cobertura ${formatMeasurementValue(hoverBin.coveredMilliseconds / (hoverBin.end - hoverBin.start) * 100)} %`
    : hover ? `${localTime(hover.timestamp)} · ${formatMeasurementValue(hover.value)} ${hover.unit}`
    : hoverTime !== null && volume ? `${hoverSegment ? `Intervalo: ${localTime(hoverSegment.start)} – ${localTime(hoverSegment.end)} · ` : ""}Sin muestras suficientes para integrar este intervalo.`
    : values.length ? "Pasá el puntero por la gráfica para ver el detalle." : "No hay muestras suficientes en esta ventana.";
  return <div className={styles.chartWrap}>
    {!overview && <p className={styles.chartNote}>{volume
      ? volume.coveredMilliseconds > 0
        ? `Volumen por ${periodLabels[period]} · estimación por integral trapezoidal entre muestras. Total de la ventana: ${formatMeasurementValue(volume.total)} ${volume.unit} · cobertura ${formatMeasurementValue(coverage)} %.`
        : "No hay muestras consecutivas suficientes para calcular volumen en esta ventana."
      : series.kind === "points-line" ? "Caudal instantáneo: cada punto es una muestra y las líneas unen muestras consecutivas; la unidad elegida convierte su valor, sin promediarlo." : "Mediciones registradas por el logger."}
      {volume && volume.periodsPerBar > 1 && ` Agrupación visual: cada barra suma ${volume.periodsPerBar} ${period === "s" ? "segundos" : period === "h" ? "horas" : "días"}. Acercá la ventana para ver cada ${periodLabels[period]}.`}
      {volume && volume.bins.some(bin => bin.coveredMilliseconds < bin.end - bin.start - 1) && " Las barras tenues tienen cobertura parcial."}
    </p>}
    <svg ref={svg} className={overview ? styles.overview : styles.chart} viewBox={overview ? `0 0 ${width} ${height}` : "0 0 1000 230"}
      preserveAspectRatio="xMidYMid meet"
      role="img" aria-label={overview ? "Histórico completo de caudal" : `${series.label} (${series.unit}), base ${periodLabels[period]}, UTC−3`}
      onPointerDown={pointer} onPointerMove={pointer} onPointerLeave={() => setHoverTime(null)}>
      {!overview && hoverSegment && <rect
        x={x(Math.max(start, hoverSegment.start))} y={top}
        width={Math.max(0, x(Math.min(end, hoverSegment.end)) - x(Math.max(start, hoverSegment.start)))}
        height={bottom - top} className={styles.intervalFocus} />}
      {(overview ? [0, 0.5, 1] : [0, 0.25, 0.5, 0.75, 1]).map(fraction => <g key={fraction}>
        <line x1={left} x2={right} y1={top + fraction * (bottom - top)} y2={top + fraction * (bottom - top)} className={styles.gridLine} />
        <text x={left - 8} y={top + 5 + fraction * (bottom - top)} textAnchor="end">{(high - (high - low) * fraction).toLocaleString("es-AR", { maximumSignificantDigits: 3, notation: overview ? "compact" : "standard" })}</text>
      </g>)}
      {ticks.map(time => {
        const label = tickLabels(time, period);
        return <g key={time}>
          <line x1={x(time)} x2={x(time)} y1={top} y2={bottom + 4} className={styles.gridLine} />
          <text x={x(time)} y={bottom + 21} textAnchor={x(time) < left + 35 ? "start" : x(time) > right - 35 ? "end" : "middle"}>
            <tspan x={x(time)}>{label.date}</tspan>{label.time && <tspan x={x(time)} dy="15">{label.time}</tspan>}
          </text>
        </g>;
      })}
      <line x1={left} x2={right} y1={y(0)} y2={y(0)} className={styles.gridLine} />
      {marks}
      {!overview && cursorTime !== null && <>
        <line x1={x(cursorTime)} x2={x(cursorTime)} y1={top} y2={bottom} className={styles.cursor} />
        {hover && <circle cx={x(hover.time)} cy={y(hover.value)} r="4" className={styles.point} />}
      </>}
      <text x={right} y={overview ? height - 6 : 224} textAnchor="end">UTC−3 · {periodLabels[period]}</text>
    </svg>
    {!overview && <p className={styles.readout} aria-live="off">{readout}</p>}
  </div>;
}
