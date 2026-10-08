import { useMemo, useState } from "react";
import type { PointerEvent } from "react";
import { localTime, streams } from "./FlowContract";
import type { Measurement } from "./FlowContract";
import styles from "./FlowMetersPage.module.css";

export function FlowChart({ items, start, end, overview = false, onPan }: {
  items: Measurement[]; start: number; end: number; overview?: boolean;
  onPan?: (fraction: number) => void;
}) {
  const [hover, setHover] = useState<Measurement | null>(null);
  const sorted = useMemo(() => [...items].sort((a, b) => a.time - b.time), [items]);
  const visible = sorted.filter(point => point.time >= start && point.time <= end);
  const values = visible.map(point => point.value);
  const low = Math.min(0, ...values);
  const high = Math.max(low + 1, ...values);
  const x = (time: number) => 60 + (time - start) / Math.max(1, end - start) * 890;
  const y = (value: number) => 170 - (value - low) / (high - low) * 140;
  let previous: Measurement | undefined;
  const path = visible.map(point => {
    const gap = point.stream.endsWith("voltage") ? 7_200_000 : 1_800_000;
    const command = previous && point.time - previous.time <= gap ? "L" : "M";
    previous = point;
    return `${command}${x(point.time).toFixed(2)},${y(point.value).toFixed(2)}`;
  }).join(" ");
  const pointer = (event: PointerEvent<SVGSVGElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const fraction = Math.max(0, Math.min(1, ((event.clientX - bounds.left) / bounds.width * 1000 - 60) / 890));
    if (onPan && event.buttons === 1) { onPan(fraction); return; }
    const instant = start + fraction * (end - start);
    let nearest: Measurement | null = null;
    for (const point of visible) {
      if (!nearest || Math.abs(point.time - instant) < Math.abs(nearest.time - instant)) nearest = point;
    }
    setHover(nearest);
  };
  const first = items[0];
  return <div className={styles.chartWrap}>
    <svg className={overview ? styles.overview : styles.chart} viewBox="0 0 1000 220"
      preserveAspectRatio={overview ? "none" : "xMidYMid meet"}
      role="img" aria-label={overview ? "Navegador del histórico completo" : `${first ? streams[first.stream] : "Mediciones"} (${first?.unit ?? ""})`}
      onPointerDown={event => { if (onPan) event.currentTarget.setPointerCapture(event.pointerId); pointer(event); }}
      onPointerMove={pointer} onPointerLeave={() => setHover(null)}>
      {[0, 1, 2, 3, 4].map(i => <g key={i}>
        <line x1="60" x2="950" y1={30 + i * 35} y2={30 + i * 35} className={styles.gridLine} />
        <text x="52" y={35 + i * 35} textAnchor="end">{(high - (high - low) * i / 4).toLocaleString("es-AR", { maximumFractionDigits: 2 })}</text>
        <text x={60 + i * 222.5} y="200" textAnchor={i === 0 ? "start" : i === 4 ? "end" : "middle"}>
          {new Date(start + (end - start) * i / 4).toLocaleString("es-AR", { timeZone: "Etc/GMT+3", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false })}
        </text>
      </g>)}
      <path d={path} className={styles.line} />
      {visible.length === 1 && visible[0] && <circle cx={x(visible[0].time)} cy={y(visible[0].value)} r="4" className={styles.point} />}
      {hover && !overview && <><line x1={x(hover.time)} x2={x(hover.time)} y1="30" y2="170" className={styles.cursor} /><circle cx={x(hover.time)} cy={y(hover.value)} r="4" className={styles.point} /></>}
    </svg>
    {!overview && <p className={styles.readout} aria-live="off">{hover ? `${localTime(hover.timestamp)} · ${hover.value.toLocaleString("es-AR", { maximumFractionDigits: 3 })} ${hover.unit}` : visible.length ? "Pasá el puntero por la gráfica para ver una medición." : "No hay mediciones en esta ventana."}</p>}
  </div>;
}
