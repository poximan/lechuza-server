import { Button } from "@servicoop/frontend-foundation";
import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from "react";

import type { LechuApiClient } from "../LechuApiClient";
import type { JsonRecord, JsonValue } from "../models";
import styles from "./RelayDisturbanceChart.module.css";

interface Waveform {
  faultNumber: number;
  faultTimestamp: string;
  recordNumber: number;
  preSeconds: number;
  postSeconds: number;
  sampleRateHz: number;
  origin: string;
  channels: Record<ChannelName, number[]>;
}

type ChannelName = "phase_a" | "phase_b" | "phase_c" | "earth";
type InteractionMode = "pan" | "zoom";

interface TimeWindow {
  end: number;
  start: number;
}

interface DragState {
  initialWindow: TimeWindow;
  mode: InteractionMode;
  pointerId: number;
  startX: number;
}

interface DragSelection {
  currentX: number;
  startX: number;
}

const WIDTH = 1_000;
const HEIGHT = 360;
const LEFT = 64;
const RIGHT = 18;
const TOP = 18;
const BOTTOM = 42;
const TOOLTIP_WIDTH = 380;
const TOOLTIP_HEIGHT = 180;
const MINIMUM_DRAG_PIXELS = 8;

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
  if (!Array.isArray(value)) throw new Error(`${context} debe ser una lista`);
  return value.map((item, index) => {
    if (typeof item !== "number" || !Number.isFinite(item))
      throw new Error(`${context}[${index}] debe ser numérico`);
    return item;
  });
}

function requiredNumber(value: JsonValue | undefined, context: string): number {
  if (typeof value !== "number" || !Number.isFinite(value))
    throw new Error(`${context} debe ser numérico`);
  return value;
}

function requiredRecord(value: JsonValue | undefined, context: string): JsonRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    throw new Error(`${context} debe ser un objeto`);
  return value;
}

function parseWaveform(payload: JsonRecord): Waveform {
  const channels = requiredRecord(payload.channels, "perturbación.channels");
  const metadata = requiredRecord(payload.metadata, "perturbación.metadata");
  if (typeof metadata.start_origin !== "string")
    throw new Error("perturbación.metadata.start_origin debe ser texto");
  if (typeof metadata.fault_timestamp !== "string")
    throw new Error("perturbación.metadata.fault_timestamp debe ser texto");
  const parsed: Waveform = {
    faultNumber: requiredNumber(payload.fault_number, "perturbación.fault_number"),
    faultTimestamp: metadata.fault_timestamp,
    recordNumber: requiredNumber(payload.record_number, "perturbación.record_number"),
    preSeconds: requiredNumber(payload.pre_seconds, "perturbación.pre_seconds"),
    postSeconds: requiredNumber(payload.post_seconds, "perturbación.post_seconds"),
    sampleRateHz: requiredNumber(payload.sample_rate_hz, "perturbación.sample_rate_hz"),
    origin: metadata.start_origin,
    channels: {
      phase_a: numericArray(channels.phase_a, "perturbación.channels.phase_a"),
      phase_b: numericArray(channels.phase_b, "perturbación.channels.phase_b"),
      phase_c: numericArray(channels.phase_c, "perturbación.channels.phase_c"),
      earth: numericArray(channels.earth, "perturbación.channels.earth"),
    },
  };
  if (!Number.isInteger(parsed.faultNumber) || parsed.faultNumber < 0)
    throw new Error("perturbación.fault_number debe ser un entero no negativo");
  if (!Number.isInteger(parsed.recordNumber) || parsed.recordNumber < 1 || parsed.recordNumber > 5)
    throw new Error("perturbación.record_number debe estar entre 1 y 5");
  const lengths = Object.values(parsed.channels).map((values) => values.length);
  if (lengths.some((length) => length < 2 || length !== lengths[0]))
    throw new Error("Los canales de la perturbación no tienen la misma longitud");
  return parsed;
}

function fitWindow(candidate: TimeWindow, bounds: TimeWindow, minimumSpan: number): TimeWindow {
  const boundsSpan = bounds.end - bounds.start;
  const orderedStart = Math.min(candidate.start, candidate.end);
  const orderedEnd = Math.max(candidate.start, candidate.end);
  const span = Math.min(boundsSpan, Math.max(minimumSpan, orderedEnd - orderedStart));
  let start = (orderedStart + orderedEnd - span) / 2;
  let end = start + span;
  if (start < bounds.start) {
    start = bounds.start;
    end = start + span;
  }
  if (end > bounds.end) {
    end = bounds.end;
    start = end - span;
  }
  return { end, start };
}

function isFullWindow(candidate: TimeWindow, bounds: TimeWindow): boolean {
  const tolerance = Math.max((bounds.end - bounds.start) / 10_000, 0.000001);
  return candidate.start <= bounds.start + tolerance && candidate.end >= bounds.end - tolerance;
}

function envelope(
  values: number[],
  firstIndex: number,
  lastIndex: number,
  pointCount = 800,
): Array<[number, number]> {
  const count = lastIndex - firstIndex + 1;
  if (count <= pointCount)
    return Array.from({ length: count }, (_, offset) => {
      const index = firstIndex + offset;
      return [index, values[index] ?? 0];
    });
  const result: Array<[number, number]> = [];
  const bucketSize = count / pointCount;
  for (let bucket = 0; bucket < pointCount; bucket += 1) {
    const start = firstIndex + Math.floor(bucket * bucketSize);
    const end = Math.min(lastIndex + 1, firstIndex + Math.floor((bucket + 1) * bucketSize));
    let minimumIndex = start;
    let maximumIndex = start;
    for (let index = start + 1; index < end; index += 1) {
      if ((values[index] ?? 0) < (values[minimumIndex] ?? 0)) minimumIndex = index;
      if ((values[index] ?? 0) > (values[maximumIndex] ?? 0)) maximumIndex = index;
    }
    for (const index of minimumIndex < maximumIndex
      ? [minimumIndex, maximumIndex]
      : [maximumIndex, minimumIndex])
      result.push([index, values[index] ?? 0]);
  }
  return result;
}

function formatRelativeTime(value: number): string {
  if (Math.abs(value) < 0.0005) return "0.000 s";
  return `${value > 0 ? "+" : "−"}${Math.abs(value).toFixed(3)} s`;
}

export function RelayDisturbanceChart({
  client,
  faultNumber,
  faultTimestamp,
  relayId,
}: {
  client: LechuApiClient;
  faultNumber: number | null;
  faultTimestamp: string | null;
  relayId: number;
}) {
  const clipId = `relay-disturbance-${useId().replace(/:/g, "")}`;
  const [waveform, setWaveform] = useState<Waveform | null>(null);
  const [message, setMessage] = useState("Leyendo la perturbación más reciente…");
  const [warning, setWarning] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [interactionMode, setInteractionMode] = useState<InteractionMode>("zoom");
  const [selectedWindow, setSelectedWindow] = useState<TimeWindow | null>(null);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [pinnedIndex, setPinnedIndex] = useState<number | null>(null);
  const [dragSelection, setDragSelection] = useState<DragSelection | null>(null);
  const [dragging, setDragging] = useState(false);
  const dragState = useRef<DragState | null>(null);
  const waveformRef = useRef<Waveform | null>(null);

  useEffect(() => {
    waveformRef.current = null;
    setWaveform(null);
    setWarning(null);
    setPinnedIndex(null);
  }, [relayId]);

  useEffect(() => {
    const controller = new AbortController();
    let retryTimer: number | null = null;
    setMessage("Leyendo la perturbación más reciente…");
    void client.relayLatestDisturbance(relayId, controller.signal).then((payload) => {
      const status = payload.status;
      if (status !== "available" && status !== "pending" && status !== "unavailable")
        throw new Error(`Contrato inválido: estado de perturbación desconocido ${String(status)}`);
      if (status !== "available") {
        const unavailableMessage = typeof payload.message === "string"
          ? payload.message
          : "La perturbación todavía no está disponible.";
        if (waveformRef.current === null) {
          setMessage(unavailableMessage);
          setWarning(null);
        } else {
          setMessage("");
          setWarning(`No se pudo refrescar la captura: ${unavailableMessage}`);
        }
        retryTimer = window.setTimeout(() => setRetry((value) => value + 1), 5_000);
        return;
      }
      const parsed = parseWaveform(payload);
      waveformRef.current = parsed;
      setWaveform(parsed);
      setMessage("");
      const previousFaultWarning = faultNumber !== null && (
        parsed.faultNumber !== faultNumber
        || parsed.faultTimestamp !== faultTimestamp
      )
        ? `Mostrando la última perturbación disponible, correspondiente a la falla ${parsed.faultNumber}; la falla actual es ${faultNumber}.`
        : null;
      const refreshWarning = typeof payload.refresh_error === "string"
        ? `No se pudo refrescar la captura: ${payload.refresh_error}`
        : null;
      const associationWarning = typeof payload.association_warning === "string"
        ? payload.association_warning
        : null;
      setWarning(
        [previousFaultWarning, associationWarning, refreshWarning]
          .filter(Boolean)
          .join(" ") || null,
      );
      retryTimer = window.setTimeout(() => setRetry((value) => value + 1), 30_000);
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) {
        const errorMessage = reason instanceof Error ? reason.message : String(reason);
        if (waveformRef.current === null) {
          setMessage(errorMessage);
          setWarning(null);
        } else {
          setMessage("");
          setWarning(`No se pudo refrescar la captura: ${errorMessage}`);
        }
        retryTimer = window.setTimeout(() => setRetry((value) => value + 1), 5_000);
      }
    });
    return () => {
      controller.abort();
      if (retryTimer !== null) window.clearTimeout(retryTimer);
    };
  }, [client, faultNumber, faultTimestamp, relayId, retry]);

  const fullWindow = useMemo<TimeWindow | null>(() => waveform
    ? { end: waveform.postSeconds, start: -waveform.preSeconds }
    : null, [waveform]);

  useEffect(() => {
    setSelectedWindow(null);
    setHoveredIndex(null);
    setPinnedIndex(null);
  }, [faultNumber, faultTimestamp, relayId, waveform?.recordNumber, waveform?.preSeconds, waveform?.postSeconds]);

  const drawing = useMemo(() => {
    if (!waveform || !fullWindow) return null;
    const sampleCount = waveform.channels.phase_a.length;
    const fullSpan = fullWindow.end - fullWindow.start;
    const minimumSpan = Math.min(fullSpan, Math.max(fullSpan / (sampleCount - 1) * 8, 0.001));
    const viewWindow = selectedWindow
      ? fitWindow(selectedWindow, fullWindow, minimumSpan)
      : fullWindow;
    const viewSpan = viewWindow.end - viewWindow.start;
    const plotWidth = WIDTH - LEFT - RIGHT;
    const plotHeight = HEIGHT - TOP - BOTTOM;
    const timeAt = (index: number) => fullWindow.start + index / (sampleCount - 1) * fullSpan;
    const indexAt = (time: number) => (time - fullWindow.start) / fullSpan * (sampleCount - 1);
    const firstIndex = Math.max(0, Math.floor(indexAt(viewWindow.start)));
    const lastIndex = Math.min(sampleCount - 1, Math.ceil(indexAt(viewWindow.end)));
    let maximum = 1;
    for (const values of Object.values(waveform.channels))
      for (let index = firstIndex; index <= lastIndex; index += 1)
        maximum = Math.max(maximum, Math.abs(values[index] ?? 0));
    const xForTime = (time: number) => LEFT + (time - viewWindow.start) / viewSpan * plotWidth;
    const x = (index: number) => xForTime(timeAt(index));
    const y = (value: number) => TOP + (maximum - value) / (2 * maximum) * plotHeight;
    return {
      firstIndex,
      fullSpan,
      lastIndex,
      maximum,
      minimumSpan,
      paths: channelDefinitions.map((channel) => ({
        ...channel,
        points: envelope(waveform.channels[channel.key], firstIndex, lastIndex)
          .map(([index, value]) => `${x(index).toFixed(2)},${y(value).toFixed(2)}`)
          .join(" "),
      })),
      plotHeight,
      plotWidth,
      sampleCount,
      timeAt,
      viewSpan,
      viewWindow,
      x,
      xForTime,
      y,
    };
  }, [fullWindow, selectedWindow, waveform]);

  if (!waveform || !drawing || !fullWindow) {
    return (
      <section className={styles.container} aria-label="Osciloperturbograma">
        <div className={styles.header}><strong>Osciloperturbograma</strong></div>
        <p className={styles.message}>{message}</p>
      </section>
    );
  }

  const applyWindow = (candidate: TimeWindow) => {
    const fitted = fitWindow(candidate, fullWindow, drawing.minimumSpan);
    setSelectedWindow(isFullWindow(fitted, fullWindow) ? null : fitted);
  };
  const svgX = (event: ReactPointerEvent<SVGSVGElement> | ReactWheelEvent<SVGSVGElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return (event.clientX - bounds.left) / bounds.width * WIDTH;
  };
  const plotX = (value: number) => Math.max(LEFT, Math.min(WIDTH - RIGHT, value));
  const timeAtX = (value: number, window = drawing.viewWindow) =>
    window.start + (plotX(value) - LEFT) / drawing.plotWidth * (window.end - window.start);
  const updateHover = (value: number) => {
    if (value < LEFT || value > WIDTH - RIGHT) {
      setHoveredIndex(null);
      return;
    }
    const ratio = (timeAtX(value) - fullWindow.start) / drawing.fullSpan;
    setHoveredIndex(Math.max(drawing.firstIndex, Math.min(drawing.lastIndex, Math.round(ratio * (drawing.sampleCount - 1)))));
  };
  const indexAtX = (value: number) => {
    const ratio = (timeAtX(value) - fullWindow.start) / drawing.fullSpan;
    return Math.max(
      drawing.firstIndex,
      Math.min(drawing.lastIndex, Math.round(ratio * (drawing.sampleCount - 1))),
    );
  };
  const finishDrag = (event: ReactPointerEvent<SVGSVGElement>, cancelled: boolean) => {
    const drag = dragState.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (!cancelled) {
      const currentX = plotX(svgX(event));
      const movement = Math.abs(currentX - drag.startX);
      if (movement < MINIMUM_DRAG_PIXELS) {
        const selectedIndex = indexAtX(currentX);
        setPinnedIndex((current) => current === selectedIndex ? null : selectedIndex);
      } else if (drag.mode === "zoom") {
        applyWindow({ end: timeAtX(currentX, drag.initialWindow), start: timeAtX(drag.startX, drag.initialWindow) });
      }
    }
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
    dragState.current = null;
    setDragSelection(null);
    setDragging(false);
  };
  const handlePointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    const startX = svgX(event);
    if (startX < LEFT || startX > WIDTH - RIGHT) return;
    dragState.current = {
      initialWindow: drawing.viewWindow,
      mode: interactionMode,
      pointerId: event.pointerId,
      startX: plotX(startX),
    };
    setDragSelection(interactionMode === "zoom" ? { currentX: plotX(startX), startX: plotX(startX) } : null);
    setHoveredIndex(null);
    setDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  };
  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const currentX = svgX(event);
    const drag = dragState.current;
    if (!drag || drag.pointerId !== event.pointerId) {
      updateHover(currentX);
      return;
    }
    if (drag.mode === "zoom") {
      setDragSelection({ currentX: plotX(currentX), startX: drag.startX });
      return;
    }
    const offset = (drag.startX - plotX(currentX)) / drawing.plotWidth
      * (drag.initialWindow.end - drag.initialWindow.start);
    applyWindow({ end: drag.initialWindow.end + offset, start: drag.initialWindow.start + offset });
  };
  const handleWheel = (event: ReactWheelEvent<SVGSVGElement>) => {
    const currentX = svgX(event);
    if (currentX < LEFT || currentX > WIDTH - RIGHT) return;
    event.preventDefault();
    const anchorRatio = (plotX(currentX) - LEFT) / drawing.plotWidth;
    const factor = Math.exp(Math.max(-200, Math.min(200, event.deltaY)) * 0.0015);
    const nextSpan = Math.max(drawing.minimumSpan, Math.min(drawing.fullSpan, drawing.viewSpan * factor));
    const anchor = timeAtX(currentX);
    applyWindow({ end: anchor + (1 - anchorRatio) * nextSpan, start: anchor - anchorRatio * nextSpan });
    setHoveredIndex(null);
  };
  const detailIndex = pinnedIndex ?? hoveredIndex;
  const hoverDetail = detailIndex === null ? null : {
    index: detailIndex,
    time: drawing.timeAt(detailIndex),
    x: drawing.x(detailIndex),
  };
  const tooltipX = hoverDetail === null
    ? LEFT
    : Math.max(LEFT, Math.min(WIDTH - RIGHT - TOOLTIP_WIDTH, hoverDetail.x + 12));
  const tooltipY = TOP + 10;
  const selectionX = dragSelection ? Math.min(dragSelection.startX, dragSelection.currentX) : LEFT;
  const selectionWidth = dragSelection ? Math.abs(dragSelection.currentX - dragSelection.startX) : 0;
  const zoomFactor = drawing.fullSpan / drawing.viewSpan;
  const ticks = Array.from({ length: 5 }, (_, index) => {
    const time = drawing.viewWindow.start + drawing.viewSpan * index / 4;
    return { time, x: drawing.xForTime(time) };
  });

  return (
    <section className={styles.container} aria-label="Osciloperturbograma">
      <div className={styles.header}>
        <strong>Osciloperturbograma · falla {waveform.faultNumber} · registro {waveform.recordNumber}</strong>
        <span>{waveform.sampleRateHz} muestras/s · t=0: {waveform.origin}</span>
      </div>
      <div className={styles.interactionBar}>
        <div className={styles.modeControls} role="group" aria-label="Modo de interacción">
          <Button aria-pressed={interactionMode === "zoom"} onClick={() => setInteractionMode("zoom")} variant={interactionMode === "zoom" ? "primary" : "ghost"}>Ampliar</Button>
          <Button aria-pressed={interactionMode === "pan"} onClick={() => setInteractionMode("pan")} variant={interactionMode === "pan" ? "primary" : "ghost"}>Mover</Button>
          <Button disabled={selectedWindow === null && pinnedIndex === null} onClick={() => { setSelectedWindow(null); setPinnedIndex(null); }} variant="ghost">Restablecer</Button>
        </div>
        <span>Arrastrá para {interactionMode === "zoom" ? "ampliar" : "desplazar"}; clic o toque para fijar una muestra; doble clic para restablecer · {zoomFactor > 1.005 ? `Zoom ×${zoomFactor.toFixed(1)}` : "Vista completa"}</span>
      </div>
      <div className={styles.legend}>
        {drawing.paths.map((channel) => <span key={channel.key} style={{ color: channel.color }}><i style={{ backgroundColor: channel.color }} />{channel.label}</span>)}
      </div>
      {warning && <p className={styles.warning}>{warning}</p>}
      <svg
        className={`${styles.chart} ${interactionMode === "zoom" ? styles.zoomMode : styles.panMode} ${dragging ? styles.dragging : ""}`}
        onDoubleClick={() => { setSelectedWindow(null); setPinnedIndex(null); }}
        onPointerCancel={(event) => finishDrag(event, true)}
        onPointerDown={handlePointerDown}
        onPointerLeave={() => { if (!dragState.current) setHoveredIndex(null); }}
        onPointerMove={handlePointerMove}
        onPointerUp={(event) => finishDrag(event, false)}
        onWheel={handleWheel}
        role="img"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      >
        <defs><clipPath id={clipId}><rect height={drawing.plotHeight} width={drawing.plotWidth} x={LEFT} y={TOP} /></clipPath></defs>
        <rect className={styles.hitArea} height={drawing.plotHeight} width={drawing.plotWidth} x={LEFT} y={TOP} />
        <line className={styles.axis} x1={LEFT} x2={WIDTH - RIGHT} y1={TOP + drawing.plotHeight / 2} y2={TOP + drawing.plotHeight / 2} />
        <g clipPath={`url(#${clipId})`}>
          {drawing.viewWindow.start <= 0 && drawing.viewWindow.end >= 0 && <line className={styles.trigger} x1={drawing.xForTime(0)} x2={drawing.xForTime(0)} y1={TOP} y2={HEIGHT - BOTTOM} />}
          {drawing.paths.map((channel) => <polyline key={channel.key} fill="none" points={channel.points} stroke={channel.color} strokeWidth="1.4" vectorEffect="non-scaling-stroke" />)}
          {hoverDetail !== null && <line className={styles.hoverGuide} x1={hoverDetail.x} x2={hoverDetail.x} y1={TOP} y2={HEIGHT - BOTTOM} />}
          {hoverDetail !== null && channelDefinitions.map((channel) => <circle className={styles.hoverPoint} cx={hoverDetail.x} cy={drawing.y(waveform.channels[channel.key][hoverDetail.index] ?? 0)} fill={channel.color} key={channel.key} r="4" />)}
          {dragSelection && <rect className={styles.zoomSelection} height={drawing.plotHeight} width={selectionWidth} x={selectionX} y={TOP} />}
        </g>
        {ticks.map((tick) => <text className={styles.label} key={tick.time} textAnchor={tick.x === LEFT ? "start" : tick.x === WIDTH - RIGHT ? "end" : "middle"} x={tick.x} y={HEIGHT - 10}>{formatRelativeTime(tick.time)}</text>)}
        <text className={styles.label} textAnchor="end" x={LEFT - 8} y={TOP + 8}>{drawing.maximum.toFixed(1)} A</text>
        <text className={styles.label} textAnchor="end" x={LEFT - 8} y={HEIGHT - BOTTOM}>−{drawing.maximum.toFixed(1)} A</text>
        {hoverDetail !== null && <g className={styles.tooltip} transform={`translate(${tooltipX} ${tooltipY})`}>
          <rect height={TOOLTIP_HEIGHT} rx="7" width={TOOLTIP_WIDTH} />
          <text x="18" y="32"><tspan className={styles.tooltipTime}>{formatRelativeTime(hoverDetail.time)}{pinnedIndex !== null ? " · fijada" : ""}</tspan>{channelDefinitions.map((channel, index) => <tspan dy={index === 0 ? 34 : 30} key={channel.key} x="18" fill={channel.color}>{channel.label}: {(waveform.channels[channel.key][hoverDetail.index] ?? 0).toFixed(3)} A</tspan>)}</text>
        </g>}
      </svg>
    </section>
  );
}
