import { useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import { localTime } from "./FlowContract";
import styles from "./FlowMetersPage.module.css";

export function FlowWindowNavigator({ fullStart, fullEnd, start, end, onChange }: {
  fullStart: number; fullEnd: number; start: number; end: number;
  onChange: (view: { start: number; end: number }) => void;
}) {
  const drag = useRef<{ pointerId: number; x: number; start: number; width: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const total = fullEnd - fullStart;
  const span = end - start;
  const disabled = total <= span;
  const clamp = (time: number) => Math.max(fullStart, Math.min(fullEnd - span, time));
  const move = (time: number) => {
    const next = clamp(time);
    onChange({ start: next, end: next + span });
  };
  const begin = (event: PointerEvent<HTMLDivElement>) => {
    if (disabled || !event.isPrimary || event.button !== 0 || drag.current) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (bounds.width <= 0) return;
    const position = fullStart + (event.clientX - bounds.left) / bounds.width * total;
    const next = position >= start && position <= end ? start : clamp(position - span / 2);
    event.preventDefault();
    event.currentTarget.focus();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { pointerId: event.pointerId, x: event.clientX, start: next, width: bounds.width };
    setDragging(true);
    move(next);
  };
  const slide = (event: PointerEvent<HTMLDivElement>) => {
    const active = drag.current;
    if (active?.pointerId === event.pointerId) move(active.start + (event.clientX - active.x) / active.width * total);
  };
  const finish = (event: PointerEvent<HTMLDivElement>) => {
    if (drag.current?.pointerId !== event.pointerId) return;
    if (event.type === "pointerup") slide(event);
    drag.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const keyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    const step = Math.max(1000, span / 10);
    const positions: Record<string, number> = { ArrowLeft: start - step, ArrowRight: start + step, PageUp: start - span,
      PageDown: start + span, Home: fullStart, End: fullEnd - span };
    const next = positions[event.key];
    if (next === undefined) return;
    event.preventDefault();
    move(next);
  };
  return <div className={styles.selectionTrack} role="slider" tabIndex={disabled ? -1 : 0}
    aria-label="Desplazar ventana del histórico" aria-orientation="horizontal" aria-disabled={disabled}
    aria-valuemin={0} aria-valuemax={100}
    aria-valuenow={disabled ? 0 : Math.round((start - fullStart) / (total - span) * 100)}
    aria-valuetext={`${localTime(start)} – ${localTime(end)}`}
    data-dragging={dragging} onKeyDown={keyboard} onPointerDown={begin} onPointerMove={slide}
    onPointerUp={finish} onPointerCancel={finish} onLostPointerCapture={() => { drag.current = null; setDragging(false); }}>
    <div className={styles.selectionWindow} style={{ left: `${(start - fullStart) / total * 100}%`, width: `${span / total * 100}%` }} />
  </div>;
}
