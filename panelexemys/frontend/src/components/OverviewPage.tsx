import { Button, Card, StatusBadge } from "@servicoop/frontend-foundation";
import { useEffect, useMemo, useState } from "react";

import type { PanelexemysApiClient } from "../PanelexemysApiClient";
import type { JsonRecord, JsonValue } from "../models";
import styles from "../App.module.css";
import { DataView } from "./DataView";

function record(value: JsonValue | undefined): JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value : {};
}

function array(value: JsonValue | undefined): JsonValue[] {
  return Array.isArray(value) ? value : [];
}

export function OverviewPage({ client, data }: { client: PanelexemysApiClient; data: JsonRecord }) {
  const descriptions = record(data.descriptions);
  const summaryEnvelope = record(data.summary);
  const summary = record(summaryEnvelope.summary);
  const modem = record(data.modem);
  const disconnected = array(summaryEnvelope.disconnected);
  const options = useMemo(() => Object.entries(descriptions).map(([id, name]) => ({ id: Number(id), name: String(name) })), [descriptions]);
  const [selected, setSelected] = useState<number | null>(options[0]?.id ?? null);
  const [windowName, setWindowName] = useState("1sem");
  const [page, setPage] = useState(0);
  const [detail, setDetail] = useState<JsonRecord | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    if (selected === null || options.some((item) => item.id === selected)) return;
    setSelected(options[0]?.id ?? null);
  }, [options, selected]);

  useEffect(() => {
    if (selected === null) return;
    const controller = new AbortController();
    client.grd(selected, windowName, page, controller.signal)
      .then((payload) => { setDetail(payload); setDetailError(null); })
      .catch((error: unknown) => { if (!controller.signal.aborted) setDetailError(error instanceof Error ? error.message : String(error)); });
    return () => controller.abort();
  }, [client, page, selected, windowName]);

  const percentage = Number(summary.porcentaje ?? 0);
  return (
    <>
      <div className={styles.metrics}>
        <Card className={styles.metricCard}><span>Conectividad</span><strong>{percentage.toFixed(1)}%</strong></Card>
        <Card className={styles.metricCard}><span>Conectados</span><strong>{String(summary.conectados ?? 0)}</strong></Card>
        <Card className={styles.metricCard}><span>Total GRD</span><strong>{String(summary.total ?? options.length)}</strong></Card>
        <Card className={styles.metricCard}><span>Enlace módem</span><StatusBadge tone={modem.state === "conectado" ? "success" : "danger"}>{String(modem.state ?? "desconocido")}</StatusBadge></Card>
      </div>

      <Card className={styles.sectionCard}>
        <div className={styles.sectionHeading}><div><h2>Equipos desconectados</h2><p>Estado compartido informado por el colector Modbus.</p></div><StatusBadge tone={disconnected.length === 0 ? "success" : "danger"}>{disconnected.length}</StatusBadge></div>
        {disconnected.length === 0 ? <p className={styles.muted}>Todos los equipos están conectados.</p> : <DataView data={{ items: disconnected }} />}
      </Card>

      <Card className={styles.sectionCard}>
        <div className={styles.sectionHeading}><div><h2>Histórico por GRD</h2><p>Consulta directa al contrato del colector.</p></div></div>
        <div className={styles.controls}>
          <select onChange={(event) => { setSelected(Number(event.target.value)); setPage(0); }} value={selected ?? ""}>
            {options.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
          {(["1sem", "1mes", "todo"] as const).map((value) => <Button key={value} onClick={() => { setWindowName(value); setPage(0); }} variant={windowName === value ? "primary" : "ghost"}>{value}</Button>)}
          <Button onClick={() => setPage((current) => current + 1)} variant="ghost">Anterior</Button>
          <Button onClick={() => setPage((current) => Math.max(0, current - 1))} variant="ghost">Siguiente</Button>
        </div>
        {detailError && <p className={styles.error}>{detailError}</p>}
        {detail && <DataView data={{ history: detail.history ?? null, outages: detail.outages ?? null }} />}
      </Card>
    </>
  );
}
