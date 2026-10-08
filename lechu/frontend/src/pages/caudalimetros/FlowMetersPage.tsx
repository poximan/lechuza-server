import { Button, Card } from "@servicoop/frontend-foundation";
import { useEffect, useMemo, useState } from "react";
import type { LechuApiClient } from "../../LechuApiClient";
import { JsonContractReader } from "../../contracts/JsonContractReader";
import type { JsonRecord } from "../../models";
import { FlowChart } from "./FlowChart";
import { inputTime, localTime, measurements, monthsBefore, parseInput, streams } from "./FlowContract";
import type { Measurement } from "./FlowContract";
import styles from "./FlowMetersPage.module.css";

const reader = new JsonContractReader();
const outcomes: Record<string, string> = { new_data: "Se importaron mediciones nuevas", no_new_data: "Consulta completa sin registros nuevos", error: "Error al consultar Sentryx", running: "Sincronizando con Sentryx…" };
const states: Record<string, string> = { waiting: "Esperando el intento diario", retrying: "Esperando el próximo reintento", complete: "Ciclo diario completado", suspended: "Intentos suspendidos hasta mañana" };
const windows = [["1d", "1 día"], ["2d", "2 días"], ["7d", "7 días"], ["1m", "1 mes"], ["2m", "2 meses"], ["all", "Todo"]] as const;

export function FlowMetersPage({ client, data, onChanged }: { client: LechuApiClient; data: JsonRecord; onChanged: () => Promise<void> }) {
  const locations = reader.records(data.locations, "locations");
  const sync = reader.record(data.sync, "sync");
  const cycle = reader.record(sync.cycle, "cycle");
  const attempt = reader.optionalRecord(sync.last_attempt, "last_attempt");
  const delays = Array.isArray(sync.retry_hours) ? sync.retry_hours.map(value => reader.number(value, "retry_hours")) : [];
  const [scheduledHour, scheduledMinute] = reader.string(sync.daily_time, "daily_time").split(":").map(Number);
  let scheduled = (scheduledHour ?? 0) * 60 + (scheduledMinute ?? 0);
  const schedule = [scheduled, ...delays.map(delay => (scheduled += delay * 60))]
    .map(minutes => `${String(Math.floor(minutes / 60) % 24).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`).join(", ");
  const [selected, setSelected] = useState(String(locations[0]?.id ?? ""));
  const location = locations.find(item => item.id === selected);
  const first = reader.optionalString(location?.first, "first");
  const last = reader.optionalString(location?.last, "last");
  const [items, setItems] = useState<Measurement[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const [windowName, setWindowName] = useState("2d");
  const [view, setView] = useState<{ start: number; end: number } | null>(null);
  const [tablePage, setTablePage] = useState(0);
  const [hidden, setHidden] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!locations.some(item => item.id === selected)) setSelected(String(locations[0]?.id ?? ""));
  }, [locations, selected]);
  useEffect(() => {
    const controller = new AbortController();
    setItems([]); setError(null); setLoading(false); setView(null); setTablePage(0);
    if (!selected || !first || !last) return;
    setLoading(true);
    const end = new Date(Date.parse(last) + 1000).toISOString();
    void client.flowMeasurements(selected, first, end, controller.signal).then(payload => {
      if (!controller.signal.aborted) setItems(measurements(payload));
    }).catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : String(reason)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [client, selected, first, last]);

  const fullStart = first ? Date.parse(first) : Date.now() - 2 * 86_400_000;
  const fullEnd = last ? Math.max(fullStart + 900_000, Date.parse(last)) : Date.now();
  const totalSpan = Math.max(1, fullEnd - fullStart);
  const defaultStart = windowName === "all" ? fullStart : windowName.endsWith("m")
    ? monthsBefore(fullEnd, Number(windowName.slice(0, -1))) : fullEnd - Number(windowName.slice(0, -1)) * 86_400_000;
  const start = Math.max(fullStart, view?.start ?? defaultStart);
  const end = Math.min(fullEnd, view?.end ?? fullEnd);
  const span = Math.max(1, end - start);
  const available = useMemo(() => Object.keys(streams).filter(stream => items.some(item => item.stream === stream)), [items]);
  const overviewItems = items.filter(item => item.stream === "urn:mwp:datastream:flow-rate");
  const rows = useMemo(() => {
    const grouped = new Map<string, Map<string, Measurement>>();
    for (const point of items) if (point.time >= start && point.time <= end) {
      if (!grouped.has(point.timestamp)) grouped.set(point.timestamp, new Map());
      grouped.get(point.timestamp)?.set(point.stream, point);
    }
    return [...grouped].sort(([a], [b]) => b.localeCompare(a));
  }, [items, start, end]);
  useEffect(() => setTablePage(0), [start, end]);

  const pan = (fraction: number) => {
    const nextStart = fullStart + Math.max(0, Math.min(1, fraction)) * Math.max(0, totalSpan - span);
    setView({ start: nextStart, end: nextStart + span });
  };
  const synchronize = async () => {
    setRequesting(true); setError(null);
    try { await client.synchronizeFlowMeters(); await onChanged(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setRequesting(false); }
  };
  const lastOutcome = String(attempt?.outcome ?? "");
  return <div className={styles.stack}>
    <Card>
      <div className={styles.header}><div><h2>Sincronización Sentryx</h2><p>Datos registrados cada 15 minutos. Reporte del logger a las 00:00, hora argentina.</p></div>
        <Button disabled={requesting || sync.running === true} onClick={() => void synchronize()}>{requesting || sync.running === true ? "Sincronizando…" : "Sincronizar Sentryx"}</Button>
      </div>
      <div role="status" className={styles.status}>
        <strong>{sync.running === true ? "Sincronización en curso" : states[String(cycle.state)]}</strong>
        <span>Intentos automáticos: {String(cycle.attempts)} / {1 + delays.length} · {schedule} UTC−3.</span>
        <span>Próximo intento automático: {localTime(String(sync.next_attempt_at))}</span>
        <span>Último intento: {localTime(attempt ? String(attempt.started_at) : null)}{attempt ? ` · ${attempt.source === "manual" ? "Manual" : "Automático"} · ${outcomes[lastOutcome] ?? lastOutcome}` : ""}</span>
        {attempt && <span>Registros nuevos: {String(attempt.new_records)}</span>}
        <span>Última consulta exitosa: {localTime(reader.optionalString(sync.last_success_at, "last_success_at"))}</span>
        {attempt?.error && <span className={styles.error}>{String(attempt.error)}</span>}
      </div>
      <p className={styles.muted}>Se conservan los últimos {String(data.retention_months)} meses. La sincronización manual puede ejecutarse aunque los intentos automáticos estén suspendidos.</p>
    </Card>
    <Card>
      <div className={styles.header}><h2>Equipo y período</h2><label>Caudalímetro <select value={selected} onChange={event => setSelected(event.target.value)}>
        {locations.map(item => <option key={String(item.id)} value={String(item.id)}>{String(item.name)}</option>)}
      </select></label></div>
      <div className={styles.controls}>{windows.map(([value, label]) => <Button key={value} variant={windowName === value && !view ? "primary" : "ghost"} aria-pressed={windowName === value && !view} onClick={() => { setWindowName(value); setView(null); }}>{label}</Button>)}</div>
      <div className={styles.controls}>
        <label>Inicio (UTC−3)<input type="datetime-local" value={inputTime(start)} min={inputTime(fullStart)} max={inputTime(end)} onChange={event => { const next = parseInput(event.target.value); if (Number.isFinite(next) && next < end) setView({ start: Math.max(fullStart, next), end }); }} /></label>
        <label>Fin (UTC−3)<input type="datetime-local" value={inputTime(end)} min={inputTime(start)} max={inputTime(fullEnd)} onChange={event => { const next = parseInput(event.target.value); if (Number.isFinite(next) && next > start) setView({ start, end: Math.min(fullEnd, next) }); }} /></label>
        <span>Resolución: {data.resolution === "PT15M" ? "15 minutos" : "Sin procesar"}</span>
      </div>
      {loading && <p role="status">Cargando histórico local…</p>}
      {error && <p role="alert" className={styles.error}>{error}</p>}
      {!loading && items.length === 0 && <p>No hay mediciones importadas para este equipo. Consultá el estado de sincronización.</p>}
    </Card>
    {items.length > 0 && <>
      <Card><h2>Gráficas</h2>
        <div className={styles.controls}>{available.map(stream => <label key={stream}><input type="checkbox" checked={!hidden.has(stream)} onChange={() => setHidden(current => { const next = new Set(current); if (next.has(stream)) next.delete(stream); else next.add(stream); return next; })} />{streams[stream]}</label>)}</div>
        {available.filter(stream => !hidden.has(stream)).map(stream => <section key={stream}><h3>{streams[stream]} ({items.find(item => item.stream === stream)?.unit})</h3><FlowChart items={items.filter(item => item.stream === stream)} start={start} end={end} /></section>)}
        <div className={styles.navigator}><strong>Histórico completo · desplazá la ventana para ver el detalle</strong>
          <FlowChart items={overviewItems.length ? overviewItems : items.filter(item => item.stream === available[0])} start={fullStart} end={fullEnd} overview onPan={fraction => pan((fraction * totalSpan - span / 2) / Math.max(1, totalSpan - span))} />
          <div className={styles.selectionTrack}><div style={{ left: `${(start - fullStart) / totalSpan * 100}%`, width: `${span / totalSpan * 100}%` }} /></div>
          <label>Desplazar ventana<input type="range" min="0" max="1000" step="1" disabled={span >= totalSpan} value={Math.round((start - fullStart) / Math.max(1, totalSpan - span) * 1000)} onChange={event => pan(Number(event.target.value) / 1000)} /></label>
          <div className={styles.controls}><label>Ampliar inicio<input type="range" aria-label="Inicio de la ventana" min="0" max="1000" value={Math.round((start - fullStart) / totalSpan * 1000)} onChange={event => { const next = fullStart + totalSpan * Number(event.target.value) / 1000; if (next < end) setView({ start: next, end }); }} /></label>
            <label>Ampliar fin<input type="range" aria-label="Fin de la ventana" min="0" max="1000" value={Math.round((end - fullStart) / totalSpan * 1000)} onChange={event => { const next = fullStart + totalSpan * Number(event.target.value) / 1000; if (next > start) setView({ start, end: next }); }} /></label></div>
        </div>
      </Card>
      <Card><h2>Datos</h2><p className={styles.muted}>Valores recibidos de Sentryx, sin cálculos propios. Los campos ausentes se muestran como —.</p>
        <div className={styles.tableWrap}><table><thead><tr><th>Registrado el (UTC−3)</th>{available.map(stream => <th key={stream}>{streams[stream]} ({items.find(item => item.stream === stream)?.unit})</th>)}</tr></thead>
          <tbody>{rows.slice(tablePage * 100, (tablePage + 1) * 100).map(([timestamp, values]) => <tr key={timestamp}><td>{localTime(timestamp)}</td>{available.map(stream => { const point = values.get(stream); return <td key={stream} title={point ? `Mín: ${point.min ?? "—"} · Máx: ${point.max ?? "—"} · Desvío: ${point.sd ?? "—"}` : undefined}>{point ? point.value.toLocaleString("es-AR", { maximumFractionDigits: 3 }) : "—"}</td>; })}</tr>)}</tbody></table></div>
        {rows.length === 0 && <p>Sin mediciones en esta ventana.</p>}
        <div className={styles.controls}><Button variant="ghost" disabled={tablePage === 0} onClick={() => setTablePage(p => p - 1)}>Anterior</Button><span>{rows.length} filas · página {tablePage + 1} de {Math.max(1, Math.ceil(rows.length / 100))}</span><Button variant="ghost" disabled={(tablePage + 1) * 100 >= rows.length} onClick={() => setTablePage(p => p + 1)}>Siguiente</Button></div>
      </Card>
    </>}
  </div>;
}
