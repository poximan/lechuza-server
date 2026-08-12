import { Button, Card } from "@servicoop/frontend-foundation";
import { useEffect, useMemo, useState } from "react";

import type { PanelexemysApiClient } from "../PanelexemysApiClient";
import type { JsonRecord, JsonValue } from "../models";
import styles from "./OverviewPage.module.css";
import { ConnectionHistoryChart } from "../history/ConnectionHistoryChart";
import { ConnectivityGauge } from "../components/ConnectivityGauge";
import { ConnectivityTrafficLight } from "../components/ConnectivityTrafficLight";
import { DisconnectedEquipmentTable } from "../components/DisconnectedEquipmentTable";
import { OutageCards } from "../components/OutageCards";

function record(value: JsonValue | undefined): JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value
    : {};
}

function array(value: JsonValue | undefined): JsonValue[] {
  return Array.isArray(value) ? value : [];
}

function unavailableDescription(item: JsonRecord): string {
  if (item.reason === "sin_estado_confirmado")
    return "sin estado confirmado en la base nueva";
  if (item.reason === "gateway_no_disponible")
    return "gateway Modbus no disponible; se conserva el último estado";
  const failures = Number(item.confirmable_failures);
  const threshold = Number(item.failure_threshold);
  if (item.disconnect_confirmed === true)
    return (
      failures +
      "/" +
      threshold +
      " fallos individuales; desconexión confirmada"
    );
  return (
    failures +
    "/" +
    threshold +
    " fallos individuales; pendiente de confirmación"
  );
}

export function OverviewPage({
  client,
  data,
}: {
  client: PanelexemysApiClient;
  data: JsonRecord;
}) {
  const descriptions = record(data.descriptions);
  const summaryEnvelope = record(data.summary);
  const summary = record(summaryEnvelope.summary);
  const modem = record(data.modem);
  const thresholds = record(data.thresholds);
  const links = record(data.links);
  const disconnected = array(summaryEnvelope.disconnected);
  const unavailable = array(summaryEnvelope.unavailable);
  const referenceNow =
    typeof data.reference_now === "string" ? data.reference_now : null;
  const states = record(summaryEnvelope.states);
  const options = useMemo(
    () =>
      Object.entries(descriptions).map(([id, name]) => ({
        id: Number(id),
        name: String(name),
      })),
    [descriptions],
  );
  const [selected, setSelected] = useState<number | null>(
    options[0]?.id ?? null,
  );
  const [windowName, setWindowName] = useState("1sem");
  const [page, setPage] = useState(0);
  const [detail, setDetail] = useState<JsonRecord | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    if (selected === null || options.some((item) => item.id === selected))
      return;
    setSelected(options[0]?.id ?? null);
  }, [options, selected]);

  useEffect(() => {
    if (selected === null) return;
    const controller = new AbortController();
    client
      .grd(selected, windowName, page, controller.signal)
      .then((payload) => {
        setDetail(payload);
        setDetailError(null);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setDetailError(
            error instanceof Error ? error.message : String(error),
          );
      });
    return () => controller.abort();
  }, [client, page, selected, summary.ts, windowName]);

  const stateValues = Object.values(states);
  const total = stateValues.length;
  const connected = stateValues.filter((value) => value === 1).length;
  const percentage = total > 0 ? (connected / total) * 100 : 0;
  const redBelow = Number(thresholds.red_below);
  const yellowBelow = Number(thresholds.yellow_below);
  const history = detail ? record(detail.history) : null;
  const totalPeriods =
    history && typeof history.total_periods === "number"
      ? history.total_periods
      : 0;
  const periodTitle =
    windowName === "1sem"
      ? `Semana ${page + 1}`
      : windowName === "1mes"
        ? `Mes ${page + 1}`
        : "Todos los datos";
  const modemEndpoint =
    modem.ip === null || modem.port === null
      ? "sin datos"
      : `${String(modem.ip)}:${String(modem.port)}`;
  return (
    <>
      <Card className={styles.modemBar}>
        <span>
          Estado [{modemEndpoint}] = <strong>{String(modem.state)}</strong>
        </span>
        <div>
          <a
            href={String(links.external_check)}
            rel="noreferrer"
            target="_blank"
          >
            Check desde afuera
          </a>
          <a href={String(links.modem_admin)} rel="noreferrer" target="_blank">
            Visitar MODEM
          </a>
        </div>
      </Card>
      {modem.error && (
        <p className={styles.error}>Monitor del módem: {String(modem.error)}</p>
      )}
      <div className={styles.overviewKpis}>
        <Card className={styles.overviewGauge}>
          <h3>Grado conectividad</h3>
          <ConnectivityGauge
            percentage={percentage}
            redBelow={redBelow}
            yellowBelow={yellowBelow}
          />
        </Card>
        <Card className={styles.overviewTraffic}>
          <h3>Salud conexión</h3>
          <ConnectivityTrafficLight
            percentage={percentage}
            redBelow={redBelow}
            yellowBelow={yellowBelow}
          />
        </Card>
        <Card className={styles.overviewDisconnected}>
          <h3>Actualmente desconectados</h3>
          {unavailable.length > 0 && (
            <div className={styles.unavailable} role="status">
              <strong>Problemas de lectura Modbus</strong>
              <ul>
                {unavailable.map((item, index) => {
                  const current = record(item);
                  return (
                    <li key={`${String(current.id_grd)}-${index}`}>
                      {String(current.description)}:{" "}
                      {unavailableDescription(current)}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
          {disconnected.length === 0 ? (
            <p className={styles.muted}>
              {unavailable.length > 0
                ? "No hay nuevas desconexiones confirmadas."
                : "Todos los equipos conectados."}
            </p>
          ) : referenceNow === null ? (
            <p className={styles.error}>
              Contrato inválido: falta reference_now
            </p>
          ) : (
            <DisconnectedEquipmentTable
              descriptions={descriptions}
              items={disconnected}
              referenceNow={referenceNow}
            />
          )}
        </Card>
      </div>

      <Card className={styles.overviewFocus}>
        <div className={styles.overviewFocusHeader}>
          <div>
            <h2>Seleccionar GRD</h2>
            <p>
              Los datos del histórico y caídas corresponden al GRD seleccionado.
            </p>
          </div>
          <select
            disabled={options.length === 0}
            onChange={(event) => {
              setSelected(Number(event.target.value));
              setPage(0);
            }}
            value={selected ?? ""}
          >
            {options.length === 0 && (
              <option value="">No hay equipos para seleccionar</option>
            )}
            {options.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.overviewFocusBody}>
          <div className={styles.overviewControlsPanel}>
            <strong>Ventana de datos</strong>
            <div className={styles.overviewTimeButtons}>
              {(["1sem", "1mes", "todo"] as const).map((value) => (
                <Button
                  key={value}
                  onClick={() => {
                    setWindowName(value);
                    setPage(0);
                  }}
                  variant={windowName === value ? "primary" : "ghost"}
                >
                  {value === "1sem"
                    ? "1 Sem"
                    : value === "1mes"
                      ? "1 Mes"
                      : "Todo"}
                </Button>
              ))}
            </div>
            <div className={styles.overviewPagination}>
              <Button
                disabled={!history || page >= Math.max(0, totalPeriods - 1)}
                onClick={() => setPage((current) => current + 1)}
                variant="ghost"
              >
                Anterior
              </Button>
              <Button
                disabled={page <= 0}
                onClick={() => setPage((current) => Math.max(0, current - 1))}
                variant="ghost"
              >
                Siguiente
              </Button>
            </div>
          </div>
          <div className={styles.overviewGraphPanel}>
            <h2>Histórico de conexión - {periodTitle}</h2>
            {options.length === 0 && (
              <p className={styles.error}>
                ADVERTENCIA: No se han encontrado equipos GRD en la base de
                datos para consulta.
              </p>
            )}
            {detailError && <p className={styles.error}>{detailError}</p>}
            {history && (
              <ConnectionHistoryChart
                key={`${selected}-${windowName}-${page}`}
                value={history}
              />
            )}
          </div>
        </div>
        {detail && (
          <div className={styles.outages}>
            <h3>
              Últimas caídas de comunicación de{" "}
              {selected === null
                ? "GRD"
                : String(descriptions[String(selected)] ?? `GRD ${selected}`)}
            </h3>
            <OutageCards value={detail.outages} />
          </div>
        )}
      </Card>
    </>
  );
}
