import { Card } from "@servicoop/frontend-foundation";

import type { JsonRecord, JsonValue } from "../models";
import styles from "./ModemDiagnostics.module.css";

function record(value: JsonValue | undefined): JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value
    : {};
}

function records(value: JsonValue | undefined): JsonRecord[] {
  return Array.isArray(value) ? value.map((item) => record(item)) : [];
}

function timestamp(value: JsonValue | undefined): string | null {
  if (typeof value !== "string") return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return `${new Intl.DateTimeFormat("es-AR", {
    timeZone: "Etc/GMT+3",
    dateStyle: "short",
    timeStyle: "medium",
  }).format(parsed)} UTC−3`;
}

function nodeStatus(value: JsonValue | undefined): string {
  if (value === "conectado") return "Conectó";
  if (value === "desconectado") return "No conectó";
  if (value === "error_nodo") return "Falla de la sonda";
  if (value === "sin_resultado") return "Sonda sin respuesta";
  if (value === "no_esperado") return "No se esperó: conexión ya confirmada";
  return "Consulta pendiente";
}

function StatusIcon({ state, label, large = false }: {
  state: string;
  label: string;
  large?: boolean;
}) {
  const connected = state === "abierto" || state === "conectado";
  const disconnected = state === "cerrado" || state === "desconectado";
  return (
    <svg
      aria-label={label}
      className={`${styles.statusIcon} ${large ? styles.mainIcon : ""} ${connected
        ? styles.connected : disconnected ? styles.disconnected : styles.pending}`}
      fill="none"
      role="img"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
      viewBox="0 0 24 24"
    >
      <title>{label}</title>
      <circle cx="12" cy="12" r="10" />
      {connected ? <path d="m7 12 3 3 7-7" />
        : disconnected ? <path d="m8 8 8 8M16 8l-8 8" />
          : <><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3" /><path d="M12 17h.01" /></>}
    </svg>
  );
}

function ProbeNodes({ nodes }: { nodes: JsonRecord[] }) {
  return (
    <ol className={styles.nodes}>
      {nodes.map((node) => {
        const status = String(node.status ?? "pendiente");
        const place = [node.city, node.country]
          .filter((part) => typeof part === "string" && part.length > 0).join(", ");
        const probeIp = typeof node.probe_ip === "string" ? node.probe_ip : "";
        const error = typeof node.error === "string" ? node.error : "";
        const latency = typeof node.latency_seconds === "number"
          ? `${(node.latency_seconds * 1000).toFixed(0)} ms` : "";
        return (
          <li className={styles.node} key={String(node.id)}>
            <div className={styles.nodeHeading}>
              <strong>{String(node.id)}</strong>
              <span className={styles.nodeResult}>
                <StatusIcon state={status} label={nodeStatus(node.status)} />
                {latency && <span>{latency}</span>}
              </span>
            </div>
            {(place || probeIp) && <small>{place}{place && probeIp ? " · " : ""}{probeIp}</small>}
            {error && <small className={status === "desconectado" ? styles.error : styles.muted}>{error}</small>}
          </li>
        );
      })}
    </ol>
  );
}

type RouteSegment =
  | { kind: "reply"; number: number; hop: JsonRecord }
  | { kind: "gap"; from: number; to: number };

function routeSegments(hops: JsonRecord[], attempted: number): RouteSegment[] {
  const replies = hops
    .filter((hop) => hop.status === "respuesta" && typeof hop.number === "number")
    .sort((left, right) => Number(left.number) - Number(right.number));
  const segments: RouteSegment[] = [];
  let next = 1;
  for (const hop of replies) {
    const number = Number(hop.number);
    if (number < next) continue;
    if (number > next) segments.push({ kind: "gap", from: next, to: number - 1 });
    segments.push({ kind: "reply", number, hop });
    next = number + 1;
  }
  if (attempted >= next) segments.push({ kind: "gap", from: next, to: attempted });
  return segments;
}

export function ModemDiagnostics({
  modem,
  externalCheckUrl,
}: {
  modem: JsonRecord;
  externalCheckUrl: string | null;
}) {
  const endpoint =
    modem.ip == null || modem.port == null
      ? "sin datos"
      : `${String(modem.ip)}:${String(modem.port)}`;
  const nodes = records(modem.nodes);
  const attempts = records(modem.attempts);
  const lastConfirmed = record(modem.last_confirmed);
  const lastConfirmedAt = timestamp(lastConfirmed.ts);
  const state = String(modem.state ?? "desconocido");
  const stateLabel = state === "abierto" ? "Conectado"
    : state === "cerrado" ? "Sin conexión" : "Sin confirmar";
  const connectedNodes = nodes.filter((node) => node.status === "conectado").length;
  const answeredNodes = nodes.filter((node) => node.status === "conectado" || node.status === "desconectado").length;
  const trace = record(modem.route_trace);
  const hops = records(trace.hops);
  const checkedAt = timestamp(modem.ts);
  const tracedAt = timestamp(trace.updated_at);
  const attempted =
    typeof trace.probed_hops === "number"
      ? trace.probed_hops
      : Math.max(0, ...hops.map((hop) => Number(hop.number) || 0));
  const segments = routeSegments(hops, attempted);
  const tcp = record(trace.tcp);
  const tcpStatus = String(tcp.status ?? "sin_datos");
  const lanState = ["rechazado", "sin_respuesta", "error"].includes(tcpStatus)
    ? "desconectado" : tcpStatus;
  const destinationObserved =
    trace.reached === true || tcpStatus === "conectado" || tcpStatus === "rechazado";
  const tcpDescription =
    tcpStatus === "conectado"
      ? `TCP conectado desde Lechu${typeof tcp.latency_ms === "number" ? ` · ${tcp.latency_ms.toFixed(2)} ms` : ""}`
      : tcpStatus === "rechazado"
        ? "El destino respondió, pero rechazó la conexión TCP"
        : tcpStatus === "sin_respuesta"
          ? "El puerto no respondió al TCP desde Lechu"
          : tcpStatus === "error"
            ? `Prueba TCP fallida: ${String(tcp.error ?? "error de red")}`
            : "Prueba TCP local pendiente";
  return (
    <Card className={styles.card}>
      <div className={styles.header}>
        <div>
          <h2>Verificación TCP</h2>
          <p><strong>Módem · {endpoint}</strong></p>
        </div>
        <div className={styles.links}>
          {externalCheckUrl && <a href={externalCheckUrl} rel="noreferrer" target="_blank">
            Check desde afuera
          </a>}
        </div>
      </div>
      <div className={styles.details}>
        <section aria-label="Nodos del chequeo externo">
          <h3 className={styles.resultHeading}>
            <StatusIcon state={state} label={stateLabel} large />
            <span>{String(modem.provider ?? "Internet")}</span>
          </h3>
          <p className={styles.muted}>{checkedAt ? `Último chequeo: ${checkedAt}` : "Sin chequeo confirmado"}</p>
          <p className={styles.muted}>
            {connectedNodes > 0 ? `${connectedNodes} sonda${connectedNodes === 1 ? " confirmó" : "s confirmaron"} conexión.`
              : `${answeredNodes} de ${nodes.length} sondas entregaron un resultado TCP.`}
            {typeof modem.elapsed_seconds === "number" ? ` Duración: ${modem.elapsed_seconds.toFixed(1)} s.` : ""}
          </p>
          {state === "desconocido" && (
            <p className={styles.notice}>Faltan respuestas concluyentes de las sondas; este chequeo no confirma una caída del módem.</p>
          )}
          {state === "desconocido" && lastConfirmedAt && (
            <p>Última confirmación: {lastConfirmed.state === "abierto" ? "accesible" : "sin conexión"} · {lastConfirmedAt}</p>
          )}
          <details className={styles.routeDetails}>
            <summary>Diagnóstico de ruta</summary>
            <p className={styles.muted}>
              Verificación TCP desde sondas externas hacia el módem.
            </p>
          {attempts.length > 0 ? attempts.map((attempt, index) => (
            <div className={styles.attempt} key={index}>
              <h4>Intento {String(attempt.number ?? index + 1)} · {String(attempt.provider ?? "Check-Host")}{index > 0 ? " · otras sondas" : ""}</h4>
              <ProbeNodes nodes={records(attempt.nodes)} />
              {typeof attempt.error === "string" && attempt.error && <p className={styles.muted}>{attempt.error}</p>}
            </div>
          )) : nodes.length > 0 ? <ProbeNodes nodes={nodes} /> : (
            <p className={styles.muted}>Todavía no hay resultados por sonda.</p>
          )}
          {typeof modem.error === "string" && modem.error && (
            <p className={styles.error}>{modem.error}</p>
          )}
          </details>
        </section>
        <section aria-label="Verificación TCP desde la red LAN">
          <h3 className={styles.resultHeading}>
            <StatusIcon state={lanState} label={tcpDescription} large />
            <span>Red LAN</span>
          </h3>
          <p className={styles.muted}>
            {tracedAt ? `Último chequeo: ${tracedAt}` : "Sin chequeo confirmado"}
            {trace.running === true ? " · Actualizando…" : ""}
          </p>
          {typeof tcp.latency_ms === "number" && (
            <p>{tcp.latency_ms.toFixed(2)} ms</p>
          )}
          {typeof tcp.error === "string" && tcp.error && (
            <p className={styles.error}>{tcp.error}</p>
          )}
          <details className={styles.routeDetails}>
            <summary>Diagnóstico de ruta</summary>
            <p className={styles.muted}>
              Traza UDP desde Lechu. Los tramos sin respuesta no indican una caída.
            </p>
          <ol className={styles.route}>
            <li className={styles.routeReached}>
              <span>Origen</span>
              <strong>Contenedor lechu</strong>
            </li>
            {segments.map((segment) =>
              segment.kind === "reply" ? (
                <li className={styles.routeReached} key={`reply-${segment.number}`}>
                  <span>Salto {segment.number} · respondió</span>
                  <strong>{String(segment.hop.address)}</strong>
                  {typeof segment.hop.latency_ms === "number" && (
                    <small>{segment.hop.latency_ms.toFixed(2)} ms</small>
                  )}
                </li>
              ) : (
                <li className={styles.routeUnknown} key={`gap-${segment.from}`}>
                  <span>
                    {segment.from === segment.to
                      ? `Salto ${segment.from} sin respuesta`
                      : `Saltos ${segment.from}–${segment.to} sin respuesta`}
                  </span>
                  <small>Tramo no visible; no indica una caída.</small>
                </li>
              ),
            )}
            <li className={destinationObserved ? styles.routeReached : styles.routeUnknown}>
              <span>Destino</span>
              <strong>{endpoint}</strong>
              <small>{tcpDescription}</small>
              {trace.reached === true && tcpStatus !== "conectado" && (
                <small>La IP respondió a la traza UDP.</small>
              )}
            </li>
          </ol>
          {attempted === 0 && trace.running === true && (
            <p className={styles.muted}>Midiendo el camino…</p>
          )}
          {typeof trace.error === "string" && trace.error && (
            <p className={styles.error}>Traza: {trace.error}</p>
          )}
          </details>
        </section>
      </div>
    </Card>
  );
}
