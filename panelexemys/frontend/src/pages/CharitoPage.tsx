import { Card, UtcMinusThreePresenter } from "@servicoop/frontend-foundation";

import { JsonContractReader } from "../contracts/JsonContractReader";
import { OperationalFormatter } from "../contracts/OperationalFormatter";
import type { JsonRecord, JsonValue } from "../models";
import styles from "./Pages.module.css";

const reader = new JsonContractReader();
const formatter = new OperationalFormatter();
const time = new UtcMinusThreePresenter();

function timestamp(value: JsonValue | undefined): string {
  return typeof value === "string" ? time.formatInstant(value) : "N/D";
}

function percentageWidth(value: JsonValue | undefined): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0)
    return 0;
  return Math.min(100, value <= 1 ? value * 100 : value);
}

function ipv4Interfaces(item: JsonRecord): JsonRecord[] {
  const sample = reader.optionalRecord(
    item.latestSample,
    "charito.latestSample",
  );
  const value = sample?.networkInterfaces ?? item.networkInterfaces ?? [];
  return reader.records(value, "charito.networkInterfaces").filter((entry) => {
    const addresses = reader.records(
      entry.addresses ?? [],
      "charito.networkInterfaces.addresses",
    );
    return addresses.some(
      (address) =>
        typeof address.address === "string" &&
        /^\d{1,3}(\.\d{1,3}){3}$/.test(address.address),
    );
  });
}

function watchedProcesses(item: JsonRecord): JsonRecord[] {
  const sample = reader.optionalRecord(
    item.latestSample,
    "charito.latestSample",
  );
  return reader.records(
    sample?.watchedProcesses ?? item.watchedProcesses ?? [],
    "charito.watchedProcesses",
  );
}

export function CharitoPage({ data }: { data: JsonRecord }) {
  const items = reader.records(data.items, "charito.items");
  return (
    <div>
      <p className={styles.charitoLastUpdate}>
        Actualizado: {timestamp(data.ts)}
      </p>
      {items.length === 0 && (
        <Card>
          <p>Sin datos recibidos.</p>
        </Card>
      )}
      <div className={styles.charitoGrid}>
        {items.map((item, index) => {
          const instanceId = formatter.scalar(item.instanceId ?? item.alias);
          const alias =
            typeof item.alias === "string" && item.alias !== instanceId
              ? item.alias
              : null;
          const status = String(item.status ?? "unknown").toLowerCase();
          const interfaces = ipv4Interfaces(item);
          const processes = watchedProcesses(item);
          const cpuWidth = percentageWidth(item.cpuLoad);
          const memoryWidth = percentageWidth(item.memoryUsageRatio);
          return (
            <Card
              className={`${styles.card} ${styles.charitoCard} ${status === "offline" || status === "error" ? styles.charitoCardStale : ""}`}
              key={`${instanceId}-${index}`}
            >
              <div className={styles.charitoHeader}>
                <div>
                  <h2>{instanceId}</h2>
                  {alias && <p className={styles.subtitle}>{alias}</p>}
                  <p className={styles.subtitle}>
                    Actualizado:{" "}
                    {timestamp(item.receivedAt ?? item.generatedAt)}
                  </p>
                </div>
                <div
                  className={`${styles.charitoStatus} ${status === "offline" || status === "error" ? styles.charitoStatusOffline : ""}`}
                >
                  <i className={styles.charitoStatusDot} />
                  {status === "online"
                    ? "Online"
                    : status === "offline"
                      ? "Offline"
                      : status === "error"
                        ? "Error de métricas"
                        : "Desconocido"}
                </div>
              </div>
              <p className={styles.subtitle}>
                {formatter.scalar(item.samples)} muestras | Ventana{" "}
                {formatter.scalar(item.windowSeconds)}s
              </p>
              {item.dataStatus !== undefined && item.dataStatus !== "ok" && (
                <p className={styles.error}>
                  {formatter.scalar(item.dataStatus)}:{" "}
                  {formatter.scalar(item.dataError)}
                </p>
              )}
              <div className={styles.charitoProgressGrid}>
                <div className={styles.progressBlock}>
                  <div className={styles.progressLabel}>
                    <span>CPU</span>
                    <strong>{formatter.ratioPercentage(item.cpuLoad)}</strong>
                  </div>
                  <div className={styles.progressTrack}>
                    <div
                      className={styles.progressFill}
                      style={{ width: `${cpuWidth}%` }}
                    />
                  </div>
                </div>
                <div className={styles.progressBlock}>
                  <div className={styles.progressLabel}>
                    <span>MEM</span>
                    <strong>
                      {formatter.ratioPercentage(item.memoryUsageRatio)}
                    </strong>
                  </div>
                  <div className={styles.progressTrack}>
                    <div
                      className={styles.progressFill}
                      style={{ width: `${memoryWidth}%` }}
                    />
                  </div>
                </div>
              </div>
              <div className={styles.charitoTemperature}>
                <span>Temp CPU</span>
                <strong>
                  {typeof item.cpuTemperatureCelsius === "number"
                    ? `${item.cpuTemperatureCelsius.toFixed(1)} °C`
                    : "N/D"}
                </strong>
              </div>
              <section className={styles.stack}>
                <h3 className={styles.sectionTitle}>Interfaces de red</h3>
                <div className={styles.chipGrid}>
                  {interfaces.length === 0 ? (
                    <span className={styles.muted}>
                      Sin interfaces IPv4 visibles
                    </span>
                  ) : (
                    interfaces.map((entry, interfaceIndex) => {
                      const addresses = reader.records(
                        entry.addresses ?? [],
                        "charito.networkInterfaces.addresses",
                      );
                      const address = addresses.find(
                        (candidate) =>
                          typeof candidate.address === "string" &&
                          /^\d{1,3}(\.\d{1,3}){3}$/.test(
                            candidate.address as string,
                          ),
                      );
                      const up = entry.up === true;
                      return (
                        <div
                          className={`${styles.charitoTile} ${up ? styles.charitoTileOk : styles.charitoTileBad}`}
                          key={`${instanceId}-if-${interfaceIndex}`}
                        >
                          <strong>
                            {formatter.scalar(entry.displayName ?? entry.name)}
                            {entry.virtual === true ? " (virtual)" : ""}
                          </strong>
                          <span>{up ? "activa" : "inactiva"}</span>
                          <code>
                            {formatter.scalar(address?.address)}
                            {address?.netmask
                              ? ` / ${String(address.netmask)}`
                              : ""}
                          </code>
                        </div>
                      );
                    })
                  )}
                </div>
              </section>
              <section className={styles.stack}>
                <h3 className={styles.sectionTitle}>Procesos monitoreados</h3>
                <div className={styles.chipGrid}>
                  {processes.length === 0 ? (
                    <span className={styles.muted}>Sin datos de procesos</span>
                  ) : (
                    processes.map((process, processIndex) => {
                      const running = process.running;
                      return (
                        <div
                          className={`${styles.charitoTile} ${running === true ? styles.charitoTileOk : running === false ? styles.charitoTileBad : styles.charitoTileUnknown}`}
                          key={`${instanceId}-process-${processIndex}`}
                        >
                          <strong>
                            {formatter.scalar(
                              process.processName ?? process.name,
                            )}
                          </strong>
                          <span>
                            {running === true
                              ? "activo"
                              : running === false
                                ? "detenido"
                                : "sin datos"}
                          </span>
                        </div>
                      );
                    })
                  )}
                </div>
              </section>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
