import { Button, UtcMinusThreePresenter } from "@servicoop/frontend-foundation";
import {
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
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

interface HoveredChange {
  connected: 0 | 1;
  instant: Date;
  x: number;
}

interface DragState {
  pointerId: number;
  span: number;
  startClientX: number;
  viewStart: number;
}

function segments(history: ConnectionHistory): ConnectionSegment[] {
  const result: ConnectionSegment[] = [];
  let cursor = history.rangeStart;
  let connected = history.connectedBefore;
  for (const event of history.events) {
    if (event.instant < history.rangeStart || event.instant > history.rangeEnd)
      continue;
    if (event.instant > cursor && connected !== null)
      result.push({ connected, end: event.instant, start: cursor });
    cursor = event.instant;
    connected = event.connected;
  }
  if (cursor < history.rangeEnd && connected !== null)
    result.push({ connected, end: history.rangeEnd, start: cursor });
  return result;
}

export function ConnectionHistoryChart({ value }: { value: JsonRecord }) {
  const parser = useMemo(() => new HistoryContractParser(), []);
  const presenter = useMemo(() => new UtcMinusThreePresenter(), []);
  const changeInstantFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat("es-AR", {
        day: "2-digit",
        hour: "2-digit",
        hour12: false,
        minute: "2-digit",
        month: "2-digit",
        second: "2-digit",
        timeZone: "Etc/GMT+3",
        year: "numeric",
      }),
    [],
  );
  const [zoom, setZoom] = useState<{ end: number; start: number } | null>(null);
  const [hoveredChange, setHoveredChange] = useState<HoveredChange | null>(null);
  const [dragging, setDragging] = useState(false);
  const dragState = useRef<DragState | null>(null);
  let history: ConnectionHistory;
  try {
    history = parser.parse(value);
  } catch (reason) {
    return (
      <p className={styles.contractError} role="alert">
        {reason instanceof Error ? reason.message : String(reason)}
      </p>
    );
  }
  const fullStart = history.rangeStart.getTime();
  const fullEnd = history.rangeEnd.getTime();
  const viewStartMs = Math.max(
    fullStart,
    Math.min(zoom?.start ?? fullStart, fullEnd - 1),
  );
  const viewEndMs = Math.min(
    fullEnd,
    Math.max(zoom?.end ?? fullEnd, viewStartMs + 1),
  );
  let connectedBefore = history.connectedBefore;
  for (const event of history.events) {
    if (event.instant.getTime() >= viewStartMs) break;
    connectedBefore = event.connected;
  }
  const viewHistory: ConnectionHistory = {
    ...history,
    connectedBefore,
    events: history.events.filter(
      (event) =>
        event.instant.getTime() >= viewStartMs &&
        event.instant.getTime() <= viewEndMs,
    ),
    rangeEnd: new Date(viewEndMs),
    rangeStart: new Date(viewStartMs),
  };
  const rangeMs = viewEndMs - viewStartMs;
  const fullRangeMs = fullEnd - fullStart;
  const canPan = rangeMs < fullRangeMs;
  const plotWidth = WIDTH - LEFT - RIGHT;
  const plotHeight = HEIGHT - TOP - BOTTOM;
  const x = (instant: Date) =>
    LEFT + ((instant.getTime() - viewStartMs) / rangeMs) * plotWidth;
  const y = (connected: 0 | 1) =>
    connected === 1 ? TOP + plotHeight * 0.25 : TOP + plotHeight * 0.75;
  const historySegments = segments(viewHistory);
  const points: string[] = [];
  let state = viewHistory.connectedBefore;
  if (state !== null)
    points.push(`${x(viewHistory.rangeStart)},${y(state)}`);
  for (const event of viewHistory.events) {
    if (state !== null)
      points.push(`${x(event.instant)},${y(state)}`);
    points.push(`${x(event.instant)},${y(event.connected)}`);
    state = event.connected;
  }
  if (state !== null)
    points.push(`${x(viewHistory.rangeEnd)},${y(state)}`);
  const ticks = Array.from({ length: 5 }, (_, index) => {
    const ratio = index / 4;
    const instant = new Date(viewStartMs + rangeMs * ratio);
    return { instant, x: LEFT + plotWidth * ratio };
  });

  function zoomBy(factor: number): void {
    const currentSpan = viewEndMs - viewStartMs;
    const minimumSpan = Math.min(60_000, fullRangeMs);
    const nextSpan = Math.max(
      minimumSpan,
      Math.min(fullRangeMs, currentSpan * factor),
    );
    const center = viewStartMs + currentSpan / 2;
    const start = Math.max(
      fullStart,
      Math.min(center - nextSpan / 2, fullEnd - nextSpan),
    );
    setHoveredChange(null);
    setZoom(nextSpan >= fullRangeMs ? null : { end: start + nextSpan, start });
  }

  function pan(direction: -1 | 1): void {
    const span = viewEndMs - viewStartMs;
    const start = Math.max(
      fullStart,
      Math.min(viewStartMs + span * 0.4 * direction, fullEnd - span),
    );
    setHoveredChange(null);
    setZoom({ end: start + span, start });
  }

  function startDrag(event: ReactPointerEvent<SVGSVGElement>): void {
    if (!canPan || event.button !== 0) return;
    dragState.current = {
      pointerId: event.pointerId,
      span: rangeMs,
      startClientX: event.clientX,
      viewStart: viewStartMs,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setHoveredChange(null);
    setDragging(true);
  }

  function drag(event: ReactPointerEvent<SVGSVGElement>): void {
    const current = dragState.current;
    if (current === null || current.pointerId !== event.pointerId) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const renderedPlotWidth = bounds.width * (plotWidth / WIDTH);
    if (renderedPlotWidth <= 0) return;
    const deltaMs =
      ((event.clientX - current.startClientX) / renderedPlotWidth) * current.span;
    const start = Math.max(
      fullStart,
      Math.min(current.viewStart - deltaMs, fullEnd - current.span),
    );
    setZoom({ end: start + current.span, start });
  }

  function stopDrag(event: ReactPointerEvent<SVGSVGElement>): void {
    if (dragState.current?.pointerId !== event.pointerId) return;
    dragState.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
    setDragging(false);
  }

  const tooltipLeft = hoveredChange
    ? Math.max(
        LEFT,
        Math.min(
          hoveredChange.x - TOOLTIP_WIDTH / 2,
          WIDTH - RIGHT - TOOLTIP_WIDTH,
        ),
      )
    : 0;
  const tooltipTop = hoveredChange
    ? hoveredChange.connected === 1
      ? y(hoveredChange.connected) + 14
      : y(hoveredChange.connected) - 72
    : 0;

  return (
    <div className={styles.viewport}>
      <div className={styles.zoomToolbar}>
        <div className={styles.rangeSummary}>
          <span>
            {presenter.formatInstant(viewHistory.rangeStart.toISOString())} —{" "}
            {presenter.formatInstant(viewHistory.rangeEnd.toISOString())}
          </span>
          <small>
            Pasá sobre un cambio para ver su instante exacto. Acercá y arrastrá
            para recorrer el período.
          </small>
        </div>
        <div>
          <Button
            disabled={zoom === null || viewStartMs <= fullStart}
            onClick={() => pan(-1)}
            variant="ghost"
          >
            Desplazar atrás
          </Button>
          <Button onClick={() => zoomBy(0.5)} variant="ghost">
            Acercar
          </Button>
          <Button
            disabled={zoom === null}
            onClick={() => zoomBy(2)}
            variant="ghost"
          >
            Alejar
          </Button>
          <Button
            disabled={zoom === null || viewEndMs >= fullEnd}
            onClick={() => pan(1)}
            variant="ghost"
          >
            Desplazar adelante
          </Button>
          <Button
            disabled={zoom === null}
            onClick={() => {
              setHoveredChange(null);
              setZoom(null);
            }}
            variant="ghost"
          >
            Restablecer
          </Button>
        </div>
      </div>
      <svg
        className={`${styles.chart} ${canPan ? styles.pannable : ""} ${
          dragging ? styles.dragging : ""
        }`}
        onLostPointerCapture={() => {
          dragState.current = null;
          setDragging(false);
        }}
        onPointerCancel={stopDrag}
        onPointerDown={startDrag}
        onPointerMove={drag}
        onPointerUp={stopDrag}
        role="img"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      >
        <title>Histórico de conexión del GRD seleccionado</title>
        <desc>
          Los puntos señalan cambios de estado. Al acercar la vista, se puede
          arrastrar horizontalmente sin salir del período consultado.
        </desc>
        <rect
          className={styles.plotBackground}
          height={plotHeight}
          width={plotWidth}
          x={LEFT}
          y={TOP}
        />
        {historySegments.map((segment, index) => (
          <rect
            className={
              segment.connected === 1
                ? styles.connectedBand
                : styles.disconnectedBand
            }
            height={plotHeight}
            key={`${segment.start.toISOString()}-${index}`}
            width={Math.max(1, x(segment.end) - x(segment.start))}
            x={x(segment.start)}
            y={TOP}
          >
            <title>{`${presenter.formatInstant(segment.start.toISOString())} – ${presenter.formatInstant(segment.end.toISOString())}: ${segment.connected === 1 ? "Conectado" : "Desconectado"}`}</title>
          </rect>
        ))}
        <line
          className={styles.stateLine}
          x1={LEFT}
          x2={WIDTH - RIGHT}
          y1={y(1)}
          y2={y(1)}
        />
        <line
          className={styles.stateLine}
          x1={LEFT}
          x2={WIDTH - RIGHT}
          y1={y(0)}
          y2={y(0)}
        />
        <text
          className={styles.stateLabel}
          textAnchor="end"
          x={LEFT - 12}
          y={y(1) + 5}
        >
          Conectado
        </text>
        <text
          className={styles.stateLabel}
          textAnchor="end"
          x={LEFT - 12}
          y={y(0) + 5}
        >
          Desconectado
        </text>
        <polyline className={styles.stepLine} points={points.join(" ")} />
        {viewHistory.events.map((event, index) => {
          const eventX = x(event.instant);
          const description = `Cambio a ${
            event.connected === 1 ? "conectado" : "desconectado"
          } el ${changeInstantFormatter.format(event.instant)}`;
          const showChange = () =>
            setHoveredChange({
              connected: event.connected,
              instant: event.instant,
              x: eventX,
            });
          return (
            <g
              aria-label={description}
              className={styles.changePoint}
              key={`${event.instant.toISOString()}-${index}`}
              onBlur={() => setHoveredChange(null)}
              onFocus={showChange}
              onPointerEnter={showChange}
              onPointerLeave={() => setHoveredChange(null)}
              role="img"
              tabIndex={0}
            >
              <line
                className={styles.changeGuide}
                x1={eventX}
                x2={eventX}
                y1={TOP}
                y2={HEIGHT - BOTTOM}
              />
              <circle
                className={
                  event.connected === 1
                    ? styles.connectedChange
                    : styles.disconnectedChange
                }
                cx={eventX}
                cy={y(event.connected)}
                r="6"
              />
              <line
                className={styles.changeTarget}
                x1={eventX}
                x2={eventX}
                y1={TOP}
                y2={HEIGHT - BOTTOM}
              />
            </g>
          );
        })}
        {ticks.map((tick) => (
          <g key={tick.instant.toISOString()}>
            <line
              className={styles.tick}
              x1={tick.x}
              x2={tick.x}
              y1={HEIGHT - BOTTOM}
              y2={HEIGHT - BOTTOM + 7}
            />
            <text
              className={styles.tickLabel}
              textAnchor="middle"
              x={tick.x}
              y={HEIGHT - 20}
            >
              {presenter.formatInstant(tick.instant.toISOString())}
            </text>
          </g>
        ))}
        {hoveredChange ? (
          <g
            className={styles.changeTooltip}
            transform={`translate(${tooltipLeft} ${tooltipTop})`}
          >
            <rect height="58" rx="8" width={TOOLTIP_WIDTH} />
            <text x="12" y="23">
              Cambio a{" "}
              {hoveredChange.connected === 1 ? "conectado" : "desconectado"}
            </text>
            <text className={styles.tooltipInstant} x="12" y="44">
              {changeInstantFormatter.format(hoveredChange.instant)} (UTC-3)
            </text>
          </g>
        ) : null}
      </svg>
      <div className={styles.legend}>
        <span>
          <i className={styles.connectedKey} />
          Conectado
        </span>
        <span>
          <i className={styles.disconnectedKey} />
          Desconectado
        </span>
      </div>
    </div>
  );
}
