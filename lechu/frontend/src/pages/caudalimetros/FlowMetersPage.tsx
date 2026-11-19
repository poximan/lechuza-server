import { Button, Card } from "@servicoop/frontend-foundation";
import { useEffect, useMemo, useState } from "react";
import type { LechuApiClient } from "../../LechuApiClient";
import { JsonContractReader } from "../../contracts/JsonContractReader";
import type { JsonRecord } from "../../models";
import { FlowChart } from "./FlowChart";
import { integrateFlow, sampleSeries } from "./FlowSeries";
import { FlowWindowNavigator } from "./FlowWindowNavigator";
import { useFlowPreferences } from "./useFlowPreferences";
import { FLOW_RATE_STREAM, FLOW_VOLUME_STREAM, FLOW_WINDOWS, inputTime, localTime, measurements, monthsBefore, parseInput, streams } from "./FlowContract";
import type { Measurement } from "./FlowContract";
import { FlowUnitControls } from "./FlowUnitControls";
import { formatMeasurementValue, presentFlowMeasurements } from "./FlowUnits";
import styles from "./FlowMetersPage.module.css";

const reader = new JsonContractReader();
const outcomes: Record<string, string> = { new_data: "Se importaron mediciones nuevas", no_new_data: "Consulta completa sin registros nuevos", error: "Error al consultar GWF", running: "Sincronizando con GWF…" };
const states: Record<string, string> = { waiting: "Esperando el intento diario", retrying: "Esperando el próximo reintento", complete: "Ciclo diario completado", suspended: "Intentos suspendidos hasta mañana" };

export function FlowMetersPage({ client, data, onChanged }: { client: LechuApiClient; data: JsonRecord; onChanged: () => Promise<void> }) {
  const locations = reader.records(data.locations, "locations");
  const catalog = reader.record(data.catalog, "catalog");
  const catalogState = reader.string(catalog.state, "catalog.state");
  if (catalogState !== "pending" && catalogState !== "available") throw new Error("Estado del catálogo de caudalímetros inválido");
  const sync = reader.record(data.sync, "sync");
  const cycle = reader.record(sync.cycle, "cycle");
  const attempt = reader.optionalRecord(sync.last_attempt, "last_attempt");
  const delays = Array.isArray(sync.retry_hours) ? sync.retry_hours.map(value => reader.number(value, "retry_hours")) : [];
  const [scheduledHour, scheduledMinute] = reader.string(sync.daily_time, "daily_time").split(":").map(Number);
  let scheduled = (scheduledHour ?? 0) * 60 + (scheduledMinute ?? 0);
  const schedule = [scheduled, ...delays.map(delay => (scheduled += delay * 60))]
    .map(minutes => `${String(Math.floor(minutes / 60) % 24).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`).join(", ");
  const { preferences, updatePreferences, preferenceError } = useFlowPreferences();
  const location = locations.find(item => item.id === preferences.locationId) ?? locations[0];
  const selected = String(location?.id ?? "");
  const first = reader.optionalString(location?.first, "first");
  const last = reader.optionalString(location?.last, "last");
  const [items, setItems] = useState<Measurement[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const windowName = preferences.windowName;
  const view = selected === preferences.locationId ? preferences.view : null;
  const setView = (next: { start: number; end: number } | null) => updatePreferences({ view: next });
  const [tablePage, setTablePage] = useState(0);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const flowVolume = preferences.volume;
  const flowPeriod = preferences.period;
  const presentation = useMemo(() => {
    try {
      return { items: presentFlowMeasurements(items, flowVolume, flowPeriod), error: null };
    } catch (reason) {
      return { items: [], error: reason instanceof Error ? reason.message : String(reason) };
    }
  }, [items, flowVolume, flowPeriod]);
  const displayItems = presentation.items;

  useEffect(() => {
    if (catalogState === "available" && selected && selected !== preferences.locationId) {
      updatePreferences({ locationId: selected, view: null });
    }
  }, [catalogState, selected, preferences.locationId, updatePreferences]);
  useEffect(() => {
    const controller = new AbortController();
    setItems([]); setError(null); setLoading(false); setTablePage(0);
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
  const defaultStart = windowName === "all" ? fullStart : windowName.endsWith("m")
    ? monthsBefore(fullEnd, Number(windowName.slice(0, -1))) : fullEnd - Number(windowName.slice(0, -1)) * 86_400_000;
  const activeView = view && view.end > fullStart && view.start < fullEnd ? view : null;
  const end = Math.max(fullStart + 1, Math.min(fullEnd, activeView?.end ?? fullEnd));
  const start = Math.max(fullStart, Math.min(end - 1, activeView?.start ?? defaultStart));
  useEffect(() => {
    if (!first || !last || !view) return;
    const next = view.end <= fullStart || view.start >= fullEnd ? null
      : { start: Math.max(fullStart, view.start), end: Math.min(fullEnd, view.end) };
    if (next === null || next.start !== view.start || next.end !== view.end) updatePreferences({ view: next });
  }, [first, last, fullStart, fullEnd, view, updatePreferences]);
  const available = useMemo(() => Object.keys(streams).filter(stream => displayItems.some(item => item.stream === stream)), [displayItems]);
  const rawFlow = useMemo(() => sampleSeries(items, FLOW_RATE_STREAM), [items]);
  const sampleCharts = useMemo(() => new Map(Object.keys(streams)
    .filter(stream => stream !== FLOW_VOLUME_STREAM && displayItems.some(item => item.stream === stream))
    .map(stream => [stream, sampleSeries(displayItems, stream)])), [displayItems]);
  const volumeChart = useMemo(() => {
    try {
      return { series: rawFlow.items.length ? integrateFlow(rawFlow.items, start, end, flowVolume, flowPeriod) : null, error: null };
    } catch (reason) {
      return { series: null, error: reason instanceof Error ? reason.message : String(reason) };
    }
  }, [rawFlow, start, end, flowVolume, flowPeriod]);
  const chartStreams = Object.keys(streams).filter(stream => sampleCharts.has(stream) || stream === FLOW_VOLUME_STREAM && volumeChart.series);
  const overviewSeries = sampleCharts.get(FLOW_RATE_STREAM) ?? sampleCharts.values().next().value;
  const rows = useMemo(() => {
    const grouped = new Map<string, Map<string, Measurement>>();
    for (const point of displayItems) if (point.time >= start && point.time <= end) {
      if (!grouped.has(point.timestamp)) grouped.set(point.timestamp, new Map());
      grouped.get(point.timestamp)?.set(point.stream, point);
    }
    return [...grouped].sort(([a], [b]) => b.localeCompare(a));
  }, [displayItems, start, end]);
  useEffect(() => setTablePage(0), [start, end]);

  const synchronize = async () => {
    setRequesting(true); setError(null);
    try { await client.synchronizeFlowMeters(); await onChanged(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setRequesting(false); }
  };
  const lastOutcome = String(attempt?.outcome ?? "");
  return <div className={styles.stack}>
    <Card>
      <div className={styles.header}><h2>Equipo y período</h2><label>Caudalímetro <select disabled={locations.length === 0} value={selected} onChange={event => updatePreferences({ locationId: event.target.value, view: null })}>
        {locations.length === 0 && <option value="">{catalogState === "pending" ? "Catálogo pendiente" : "Sin equipos disponibles"}</option>}
        {locations.map(item => <option key={String(item.id)} value={String(item.id)}>{String(item.name)}</option>)}
      </select></label></div>
      {catalogState === "pending" && <p role="status" className={styles.muted}>El catálogo de equipos está pendiente. Sincronizá GWF para consultar todos los logs disponibles.</p>}
      {catalogState === "available" && locations.length === 0 && <p role="status" className={styles.muted}>GWF no devolvió equipos disponibles para estas credenciales.</p>}
      <div className={styles.controls}>{FLOW_WINDOWS.map(([value, label]) => <Button key={value} variant={windowName === value && !activeView ? "primary" : "ghost"} aria-pressed={windowName === value && !activeView} onClick={() => updatePreferences({ windowName: value, view: null })}>{label}</Button>)}</div>
      <div className={styles.controls}>
        <label>Inicio (UTC−3)<input type="datetime-local" value={inputTime(start)} min={inputTime(fullStart)} max={inputTime(end)} onChange={event => { const next = parseInput(event.target.value); if (Number.isFinite(next) && next < end) setView({ start: Math.max(fullStart, next), end }); }} /></label>
        <label>Fin (UTC−3)<input type="datetime-local" value={inputTime(end)} min={inputTime(start)} max={inputTime(fullEnd)} onChange={event => { const next = parseInput(event.target.value); if (Number.isFinite(next) && next > start) setView({ start, end: Math.min(fullEnd, next) }); }} /></label>
        <span>Resolución: {data.resolution === "PT15M" ? "15 minutos" : "Sin procesar"}</span>
      </div>
      <FlowUnitControls volume={flowVolume} period={flowPeriod} disabled={!items.some(item => item.stream === FLOW_RATE_STREAM)} onVolumeChange={volume => updatePreferences({ volume })} onPeriodChange={period => updatePreferences({ period })} />
      {preferenceError && <p role="status" className={styles.error}>{preferenceError}</p>}
      {loading && <p role="status">Cargando histórico local…</p>}
      {error && <p role="alert" className={styles.error}>{error}</p>}
      {presentation.error && <p role="alert" className={styles.error}>{presentation.error}</p>}
      {!loading && !error && selected && items.length === 0 && <p>No hay mediciones importadas para {String(location?.name ?? "este equipo")}. Consultá el estado de sincronización.</p>}
    </Card>
    {displayItems.length > 0 && <>
      <Card><h2>Gráficas</h2>
        {available.includes(FLOW_VOLUME_STREAM) && rawFlow.items.length === 0 && <p className={styles.muted}>Se necesita caudal para calcular su integral. El volumen reportado por GWF está disponible en la tabla de datos.</p>}
        <div className={styles.controls}>{chartStreams.map(stream => <label key={stream}><input type="checkbox" checked={!hidden.has(stream)} onChange={() => setHidden(current => { const next = new Set(current); if (next.has(stream)) next.delete(stream); else next.add(stream); return next; })} />{streams[stream]}</label>)}</div>
        {volumeChart.error && <p role="alert" className={styles.error}>{volumeChart.error}</p>}
        {chartStreams.filter(stream => !hidden.has(stream)).map(stream => {
          const series = stream === FLOW_VOLUME_STREAM ? volumeChart.series : sampleCharts.get(stream);
          return series ? <section key={stream}><h3>{series.label} ({series.unit})</h3><FlowChart series={series} start={start} end={end} period={flowPeriod} /></section> : null;
        })}
        <div className={styles.navigator}><strong>Histórico completo · desplazá la ventana para ver el detalle</strong>
          {overviewSeries && <FlowChart series={overviewSeries} start={fullStart} end={fullEnd} period={flowPeriod} overview />}
          <FlowWindowNavigator fullStart={fullStart} fullEnd={fullEnd} start={start} end={end} onChange={setView} />
          <p className={styles.muted}>Arrastrá la franja seleccionada para desplazar la ventana. También podés usar las flechas del teclado.</p>
          <div className={styles.controls}><label>Ampliar inicio<input type="range" aria-label="Inicio de la ventana" min="0" max="1000" value={Math.round((start - fullStart) / Math.max(1, fullEnd - fullStart) * 1000)} onChange={event => { const next = fullStart + (fullEnd - fullStart) * Number(event.target.value) / 1000; if (next < end) setView({ start: next, end }); }} /></label>
            <label>Ampliar fin<input type="range" aria-label="Fin de la ventana" min="0" max="1000" value={Math.round((end - fullStart) / Math.max(1, fullEnd - fullStart) * 1000)} onChange={event => { const next = fullStart + (fullEnd - fullStart) * Number(event.target.value) / 1000; if (next > start) setView({ start, end: next }); }} /></label></div>
        </div>
      </Card>
      <Card><h2>Datos</h2><p className={styles.muted}>Mediciones recibidas de GWF. La unidad seleccionada convierte el caudal y sus estadísticas. El volumen de esta tabla es el reportado por GWF; la gráfica muestra la integral calculada entre muestras de caudal. Los datos originales se conservan y los campos ausentes se muestran como —.</p>
        <div className={styles.tableWrap}><table><thead><tr><th>Registrado el (UTC−3)</th>{available.map(stream => <th key={stream}>{streams[stream]} ({displayItems.find(item => item.stream === stream)?.unit})</th>)}</tr></thead>
          <tbody>{rows.slice(tablePage * 100, (tablePage + 1) * 100).map(([timestamp, values]) => <tr key={timestamp}><td>{localTime(timestamp)}</td>{available.map(stream => { const point = values.get(stream); const statistic = (value: number | null) => value === null ? "—" : `${formatMeasurementValue(value)} ${point?.unit ?? ""}`; return <td key={stream} title={point ? `Mín: ${statistic(point.min)} · Máx: ${statistic(point.max)} · Desvío: ${statistic(point.sd)}` : undefined}>{point ? formatMeasurementValue(point.value) : "—"}</td>; })}</tr>)}</tbody></table></div>
        {rows.length === 0 && <p>Sin mediciones en esta ventana.</p>}
        <div className={styles.controls}><Button variant="ghost" disabled={tablePage === 0} onClick={() => setTablePage(p => p - 1)}>Anterior</Button><span>{rows.length} filas · página {tablePage + 1} de {Math.max(1, Math.ceil(rows.length / 100))}</span><Button variant="ghost" disabled={(tablePage + 1) * 100 >= rows.length} onClick={() => setTablePage(p => p + 1)}>Siguiente</Button></div>
      </Card>
    </>}
    <Card>
      <div className={styles.header}><div><h2>Sincronización GWF</h2><p>Datos registrados cada 15 minutos. Reporte del logger a las 00:00, hora argentina.</p></div>
        <Button disabled={requesting || sync.running === true} onClick={() => void synchronize()}>{requesting || sync.running === true ? "Sincronizando…" : "Sincronizar GWF"}</Button>
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
  </div>;
}
