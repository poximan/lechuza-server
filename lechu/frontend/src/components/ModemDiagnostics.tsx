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
  return "Sin resultado";
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
  links,
}: {
  modem: JsonRecord;
  links: JsonRecord;
}) {
  const endpoint =
    modem.ip == null || modem.port == null
      ? "sin datos"
      : `${String(modem.ip)}:${String(modem.port)}`;
  const nodes = records(modem.nodes);
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
          <h2>
            Estado [{endpoint}] = <strong>{String(modem.state ?? "desconocido")}</strong>
          </h2>
          <p>{checkedAt ? `Último chequeo externo: ${checkedAt}` : "Sin chequeo externo confirmado"}</p>
        </div>
        <div className={styles.links}>
          <a href={String(links.external_check)} rel="noreferrer" target="_blank">
            Check desde afuera
          </a>
          <a href={String(links.modem_admin)} rel="noreferrer" target="_blank">
            Visitar MODEM
          </a>
        </div>
      </div>
      <div className={styles.details}>
        <section aria-label="Nodos del chequeo externo">
          <h3>Nodos de Check-Host ({nodes.length} seleccionados)</h3>
          {nodes.length === 0 ? (
            <p className={styles.muted}>Todavía no hay resultados por nodo.</p>
          ) : (
            <ol className={styles.nodes}>
              {nodes.map((node) => {
                const status = String(node.status ?? "pendiente");
                const place = [node.city, node.country]
                  .filter((part) => typeof part === "string" && part.length > 0)
                  .join(", ");
                const probeIp = typeof node.probe_ip === "string" ? node.probe_ip : "";
                const error = typeof node.error === "string" ? node.error : "";
                const latency =
                  typeof node.latency_seconds === "number"
                    ? ` · ${node.latency_seconds.toFixed(2)} s`
                    : "";
                return (
                  <li className={styles.node} key={String(node.id)}>
                    <div className={styles.nodeHeading}>
                      <strong>{String(node.id)}</strong>
                      <span
                        className={
                          status === "conectado"
                            ? styles.connected
                            : status === "desconectado"
                              ? styles.disconnected
                              : styles.pending
                        }
                      >
                        {nodeStatus(node.status)}{latency}
                      </span>
                    </div>
                    {(place || probeIp) && (
                      <small>{place}{place && probeIp ? " · " : ""}{probeIp}</small>
                    )}
                    {error && <small className={styles.error}>{error}</small>}
                  </li>
                );
              })}
            </ol>
          )}
          {typeof modem.error === "string" && modem.error && (
            <p className={styles.error}>{modem.error}</p>
          )}
        </section>
        <section aria-label="Camino desde Lechu">
          <h3>Camino desde el contenedor lechu</h3>
          <p className={styles.muted}>
            Los routers intermedios se buscan con una traza UDP. El destino se comprueba
            aparte con TCP al puerto {String(modem.port ?? "?")}.
          </p>
          <p className={styles.muted}>
            {tracedAt ? `Último diagnóstico: ${tracedAt}` : "Sin diagnóstico completado"}
            {trace.running === true ? " · Actualizando…" : ""}
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
        </section>
      </div>
    </Card>
  );
}
