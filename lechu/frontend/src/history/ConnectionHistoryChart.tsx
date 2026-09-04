import { Button, UtcMinusThreePresenter } from "@servicoop/frontend-foundation";
import {
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from "react";

import type { JsonRecord } from "../models";
import { HistoryContractParser } from "./HistoryContractParser";
import type { ConnectionHistory, ConnectionSegment } from "./HistoryModels";
import styles from "./ConnectionHistoryChart.module.css";

const WIDTH = 1_000;
const HEIGHT = 260;
const LEFT = 112;
const RIGHT = 24;
const TOP = 24;
const BOTTOM = 52;
const TOOLTIP_WIDTH = 286;
const MINIMUM_DRAG_PIXELS = 8;

type InteractionMode = "pan" | "zoom";

interface TimeWindow {
  end: number;
  start: number;
}

interface HoveredState {
  connected: 0 | 1;
  instant: Date;
  x: number;
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

function segments(history: ConnectionHistory): ConnectionSegment[] {
  const result: ConnectionSegment[] = [];
  let cursor = history.rangeStart;
  let connected = history.connectedBefore;
  for (const event of history.events) {
    if (event.instant < history.rangeStart || event.instant > history.rangeEnd) continue;
    if (event.instant > cursor && connected !== null)
      result.push({ connected, end: event.instant, start: cursor });
    cursor = event.instant;
    connected = event.connected;
  }
  if (cursor < history.rangeEnd && connected !== null)
    result.push({ connected, end: history.rangeEnd, start: cursor });
  return result;
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

export function ConnectionHistoryChart({ value }: { value: JsonRecord }) {
  const parser = useMemo(() => new HistoryContractParser(), []);
  const presenter = useMemo(() => new UtcMinusThreePresenter(), []);
  const exactFormatter = useMemo(() => new Intl.DateTimeFormat("es-AR", {
    day: "2-digit",
    hour: "2-digit",
    hour12: false,
    minute: "2-digit",
    month: "2-digit",
    second: "2-digit",
    timeZone: "Etc/GMT+3",
    year: "numeric",
  }), []);
  const [interactionMode, setInteractionMode] = useState<InteractionMode>("zoom");
  const [zoom, setZoom] = useState<TimeWindow | null>(null);
  const [hoveredState, setHoveredState] = useState<HoveredState | null>(null);
  const [dragSelection, setDragSelection] = useState<DragSelection | null>(null);
  const [dragging, setDragging] = useState(false);
  const dragState = useRef<DragState | null>(null);

  let history: ConnectionHistory;
  try {
    history = parser.parse(value);
  } catch (reason) {
    return <p className={styles.contractError} role="alert">{reason instanceof Error ? reason.message : String(reason)}</p>;
  }

  const fullStart = history.rangeStart.getTime();
  const fullWindow = {
    end: Math.max(fullStart + 1, history.rangeEnd.getTime()),
    start: fullStart,
  };
  const fullRange = Math.max(1, fullWindow.end - fullWindow.start);
  const minimumSpan = Math.min(60_000, fullRange);
  const viewWindow = zoom
    ? fitWindow(zoom, fullWindow, minimumSpan)
    : fullWindow;
  const range = viewWindow.end - viewWindow.start;
  let connectedBefore = history.connectedBefore;
  for (const event of history.events) {
    if (event.instant.getTime() >= viewWindow.start) break;
    connectedBefore = event.connected;
  }
  const visibleHistory: ConnectionHistory = {
    ...history,
    connectedBefore,
    events: history.events.filter((event) => {
      const instant = event.instant.getTime();
      return instant >= viewWindow.start && instant <= viewWindow.end;
    }),
    rangeEnd: new Date(viewWindow.end),
    rangeStart: new Date(viewWindow.start),
  };
  const plotWidth = WIDTH - LEFT - RIGHT;
  const plotHeight = HEIGHT - TOP - BOTTOM;
  const x = (instant: Date) => LEFT + (instant.getTime() - viewWindow.start) / range * plotWidth;
  const y = (connected: 0 | 1) => connected === 1
    ? TOP + plotHeight * 0.25
    : TOP + plotHeight * 0.75;
  const historySegments = segments(visibleHistory);
  const points: string[] = [];
  let state = visibleHistory.connectedBefore;
  if (state !== null) points.push(`${x(visibleHistory.rangeStart)},${y(state)}`);
  for (const event of visibleHistory.events) {
    if (state !== null) points.push(`${x(event.instant)},${y(state)}`);
    points.push(`${x(event.instant)},${y(event.connected)}`);
    state = event.connected;
  }
  if (state !== null) points.push(`${x(visibleHistory.rangeEnd)},${y(state)}`);
  const ticks = Array.from({ length: 5 }, (_, index) => {
    const instant = new Date(viewWindow.start + range * index / 4);
    return { instant, x: LEFT + plotWidth * index / 4 };
  });

  const eventSvgX = (event: ReactPointerEvent<SVGSVGElement> | ReactWheelEvent<SVGSVGElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return (event.clientX - bounds.left) / bounds.width * WIDTH;
  };
  const plotX = (value: number) => Math.max(LEFT, Math.min(WIDTH - RIGHT, value));
  const timestampAt = (value: number, window = viewWindow) =>
    window.start + (plotX(value) - LEFT) / plotWidth * (window.end - window.start);
  const applyWindow = (candidate: TimeWindow) => {
    const fitted = fitWindow(candidate, fullWindow, minimumSpan);
    const full = fitted.start <= fullWindow.start + 1 && fitted.end >= fullWindow.end - 1;
    setZoom(full ? null : fitted);
  };
  const stateAt = (timestamp: number): 0 | 1 | null => {
    let current = visibleHistory.connectedBefore;
    for (const event of visibleHistory.events) {
      if (event.instant.getTime() > timestamp) break;
      current = event.connected;
    }
    return current;
  };
  const updateHover = (value: number) => {
    if (value < LEFT || value > WIDTH - RIGHT) {
      setHoveredState(null);
      return;
    }
    const instant = timestampAt(value);
    const connected = stateAt(instant);
    setHoveredState(connected === null
      ? null
      : { connected, instant: new Date(instant), x: plotX(value) });
  };
  const startDrag = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    const startX = eventSvgX(event);
    if (startX < LEFT || startX > WIDTH - RIGHT) return;
    dragState.current = {
      initialWindow: viewWindow,
      mode: interactionMode,
      pointerId: event.pointerId,
      startX: plotX(startX),
    };
    setHoveredState(null);
    setDragSelection(interactionMode === "zoom"
      ? { currentX: plotX(startX), startX: plotX(startX) }
      : null);
    setDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  };
  const drag = (event: ReactPointerEvent<SVGSVGElement>) => {
    const currentX = eventSvgX(event);
    const current = dragState.current;
    if (!current || current.pointerId !== event.pointerId) {
      updateHover(currentX);
      return;
    }
    if (current.mode === "zoom") {
      setDragSelection({ currentX: plotX(currentX), startX: current.startX });
      return;
    }
    const span = current.initialWindow.end - current.initialWindow.start;
    const offset = (current.startX - plotX(currentX)) / plotWidth * span;
    applyWindow({ end: current.initialWindow.end + offset, start: current.initialWindow.start + offset });
  };
  const stopDrag = (event: ReactPointerEvent<SVGSVGElement>, cancelled = false) => {
    const current = dragState.current;
    if (!current || current.pointerId !== event.pointerId) return;
    if (!cancelled && current.mode === "zoom") {
      const currentX = plotX(eventSvgX(event));
      if (Math.abs(currentX - current.startX) >= MINIMUM_DRAG_PIXELS)
        applyWindow({ end: timestampAt(currentX, current.initialWindow), start: timestampAt(current.startX, current.initialWindow) });
    }
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
    dragState.current = null;
    setDragSelection(null);
    setDragging(false);
  };
  const wheel = (event: ReactWheelEvent<SVGSVGElement>) => {
    const valueX = eventSvgX(event);
    if (valueX < LEFT || valueX > WIDTH - RIGHT) return;
    event.preventDefault();
    const anchorRatio = (plotX(valueX) - LEFT) / plotWidth;
    const factor = Math.exp(Math.max(-200, Math.min(200, event.deltaY)) * 0.0015);
    const nextSpan = Math.max(minimumSpan, Math.min(fullRange, range * factor));
    const anchor = timestampAt(valueX);
    applyWindow({ end: anchor + (1 - anchorRatio) * nextSpan, start: anchor - anchorRatio * nextSpan });
    setHoveredState(null);
  };
  const tooltipLeft = hoveredState
    ? Math.max(LEFT, Math.min(hoveredState.x - TOOLTIP_WIDTH / 2, WIDTH - RIGHT - TOOLTIP_WIDTH))
    : LEFT;
  const tooltipTop = hoveredState
    ? hoveredState.connected === 1 ? y(1) + 14 : y(0) - 72
    : TOP;
  const selectionX = dragSelection ? Math.min(dragSelection.startX, dragSelection.currentX) : LEFT;
  const selectionWidth = dragSelection ? Math.abs(dragSelection.currentX - dragSelection.startX) : 0;
  const zoomFactor = fullRange / range;

  return (
    <div className={styles.viewport}>
      <div className={styles.zoomToolbar}>
        <div className={styles.rangeSummary}>
          <span>{presenter.formatInstant(visibleHistory.rangeStart.toISOString())} — {presenter.formatInstant(visibleHistory.rangeEnd.toISOString())}</span>
          <small>Pasá por cualquier punto para ver fecha, hora y estado. Arrastrá, usá la rueda o hacé doble clic para restablecer.</small>
        </div>
        <div aria-label="Modo de interacción" role="group">
          <Button aria-pressed={interactionMode === "zoom"} onClick={() => setInteractionMode("zoom")} variant={interactionMode === "zoom" ? "primary" : "ghost"}>Ampliar</Button>
          <Button aria-pressed={interactionMode === "pan"} onClick={() => setInteractionMode("pan")} variant={interactionMode === "pan" ? "primary" : "ghost"}>Mover</Button>
          <Button disabled={zoom === null} onClick={() => { setHoveredState(null); setZoom(null); }} variant="ghost">Restablecer</Button>
          <small>{zoomFactor > 1.005 ? `Zoom ×${zoomFactor.toFixed(1)}` : "Vista completa"}</small>
        </div>
      </div>
      <svg
        className={`${styles.chart} ${interactionMode === "zoom" ? styles.zoomMode : styles.pannable} ${dragging ? styles.dragging : ""}`}
        onDoubleClick={() => { setHoveredState(null); setZoom(null); }}
        onLostPointerCapture={() => { dragState.current = null; setDragSelection(null); setDragging(false); }}
        onPointerCancel={(event) => stopDrag(event, true)}
        onPointerDown={startDrag}
        onPointerLeave={() => { if (!dragState.current) setHoveredState(null); }}
        onPointerMove={drag}
        onPointerUp={stopDrag}
        onWheel={wheel}
        role="img"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      >
        <title>Histórico de conexión del GRD seleccionado</title>
        <desc>La posición horizontal permite consultar fecha, hora y estado. La vista admite ampliación y desplazamiento.</desc>
        <rect className={styles.plotBackground} height={plotHeight} width={plotWidth} x={LEFT} y={TOP} />
        {historySegments.map((segment, index) => <rect
          className={segment.connected === 1 ? styles.connectedBand : styles.disconnectedBand}
          height={plotHeight}
          key={`${segment.start.toISOString()}-${index}`}
          width={Math.max(1, x(segment.end) - x(segment.start))}
          x={x(segment.start)}
          y={TOP}
        />)}
        <line className={styles.stateLine} x1={LEFT} x2={WIDTH - RIGHT} y1={y(1)} y2={y(1)} />
        <line className={styles.stateLine} x1={LEFT} x2={WIDTH - RIGHT} y1={y(0)} y2={y(0)} />
        <text className={styles.stateLabel} textAnchor="end" x={LEFT - 12} y={y(1) + 5}>Conectado</text>
        <text className={styles.stateLabel} textAnchor="end" x={LEFT - 12} y={y(0) + 5}>Desconectado</text>
        <polyline className={styles.stepLine} points={points.join(" ")} />
        {visibleHistory.events.map((event, index) => {
          const eventX = x(event.instant);
          const description = `Cambio a ${event.connected === 1 ? "conectado" : "desconectado"} el ${exactFormatter.format(event.instant)}`;
          return <g
            aria-label={description}
            className={styles.changePoint}
            key={`${event.instant.toISOString()}-${index}`}
            onBlur={() => setHoveredState(null)}
            onFocus={() => setHoveredState({ connected: event.connected, instant: event.instant, x: eventX })}
            role="img"
            tabIndex={0}
          >
            <line className={styles.changeGuide} x1={eventX} x2={eventX} y1={TOP} y2={HEIGHT - BOTTOM} />
            <circle className={event.connected === 1 ? styles.connectedChange : styles.disconnectedChange} cx={eventX} cy={y(event.connected)} r="6" />
            <line className={styles.changeTarget} x1={eventX} x2={eventX} y1={TOP} y2={HEIGHT - BOTTOM} />
          </g>;
        })}
        {ticks.map((tick) => <g key={tick.instant.toISOString()}>
          <line className={styles.tick} x1={tick.x} x2={tick.x} y1={HEIGHT - BOTTOM} y2={HEIGHT - BOTTOM + 7} />
          <text className={styles.tickLabel} textAnchor="middle" x={tick.x} y={HEIGHT - 20}>{presenter.formatInstant(tick.instant.toISOString())}</text>
        </g>)}
        {dragSelection && <rect className={styles.zoomSelection} height={plotHeight} width={selectionWidth} x={selectionX} y={TOP} />}
        {hoveredState && <line className={styles.hoverGuide} x1={hoveredState.x} x2={hoveredState.x} y1={TOP} y2={HEIGHT - BOTTOM} />}
        {hoveredState && <g className={styles.changeTooltip} transform={`translate(${tooltipLeft} ${tooltipTop})`}>
          <rect height="58" rx="8" width={TOOLTIP_WIDTH} />
          <text x="12" y="23">Estado: {hoveredState.connected === 1 ? "conectado" : "desconectado"}</text>
          <text className={styles.tooltipInstant} x="12" y="44">{exactFormatter.format(hoveredState.instant)} (UTC-3)</text>
        </g>}
      </svg>
      <div className={styles.legend}>
        <span><i className={styles.connectedKey} />Conectado</span>
        <span><i className={styles.disconnectedKey} />Desconectado</span>
      </div>
    </div>
  );
}
