import { Card, UtcMinusThreePresenter } from "@servicoop/frontend-foundation";
import { useState, type CSSProperties } from "react";

import { JsonContractReader } from "../contracts/JsonContractReader";
import { OperationalFormatter } from "../contracts/OperationalFormatter";
import { MetricHistoryChart } from "../history/MetricHistoryChart";
import { ToggleSwitch } from "../components/ToggleSwitch";
import type { PanelexemysApiClient } from "../PanelexemysApiClient";
import type { JsonRecord } from "../models";
import styles from "./Pages.module.css";

const reader = new JsonContractReader();
const formatter = new OperationalFormatter();
const time = new UtcMinusThreePresenter();

function usageClass(value: number): string {
  return value >= 85
    ? styles.progressDanger!
    : value >= 70
      ? styles.progressWarning!
      : styles.progressFill!;
}

function vmHistory(historyMap: JsonRecord | null, vmid: string): JsonRecord {
  const envelope = historyMap
    ? reader.optionalRecord(historyMap[vmid], `proxmox.history.vms.${vmid}`)
    : null;
  return envelope
    ? reader.record(
        envelope.history ?? {},
        `proxmox.history.vms.${vmid}.history`,
      )
    : {};
}

function latestHistoryTimestamp(historyMap: JsonRecord | null): string | null {
  let latest: { iso: string; timestamp: number } | null = null;
  for (const [vmid, value] of Object.entries(historyMap ?? {})) {
    const envelope = reader.record(value, `proxmox.history.vms.${vmid}`);
    const history = reader.record(
      envelope.history ?? {},
      `proxmox.history.vms.${vmid}.history`,
    );
    for (const metric of ["cpu_pct", "mem_pct"]) {
      for (const item of reader.records(
        history[metric] ?? [],
        `proxmox.history.vms.${vmid}.${metric}`,
      )) {
        if (typeof item.ts !== "string") continue;
        const timestamp = new Date(item.ts).getTime();
        if (
          Number.isFinite(timestamp) &&
          (latest === null || timestamp > latest.timestamp)
        )
          latest = { iso: item.ts, timestamp };
      }
    }
  }
  return latest?.iso ?? null;
}

function DiskMetrics({ vm }: { vm: JsonRecord }) {
  return (
    <div className={styles.metricGrid}>
      <div className={styles.metric}>
        <span>Disco asignado</span>
        <strong>
          {typeof vm.disk_total_gb === "number"
            ? `${vm.disk_total_gb.toFixed(1)} GB`
            : "N/D"}
        </strong>
      </div>
      <div className={styles.metric}>
        <span>Lectura</span>
        <strong>{formatter.bytes(vm.disk_read_bytes)}</strong>
      </div>
      <div className={styles.metric}>
        <span>Escritura</span>
        <strong>{formatter.bytes(vm.disk_write_bytes)}</strong>
      </div>
    </div>
  );
}

function VmHeader({ vm }: { vm: JsonRecord }) {
  const status = String(vm.status ?? "desconocido");
  const statusClass =
    status === "running"
      ? styles.proxmoxStatusRunning
      : status === "stopped"
        ? styles.proxmoxStatusStopped
        : styles.proxmoxStatusUnknown;
  return (
    <div className={styles.cardHeader}>
      <div className={styles.proxmoxCardTitle}>
        <strong>VM {formatter.scalar(vm.vmid)}</strong>
        <div>
          <strong>{formatter.scalar(vm.name)}</strong>
          <p className={styles.subtitle}>
            vCPUs: {formatter.scalar(vm.cpus)} - Uptime:{" "}
            {formatter.scalar(vm.uptime_human)}
          </p>
        </div>
      </div>
      <div className={`${styles.proxmoxStatus} ${statusClass}`}>
        <span>{status.toUpperCase()}</span>
        <i aria-hidden="true" />
      </div>
    </div>
  );
}

function LiveVmCard({ vm }: { vm: JsonRecord }) {
  const rawCpu =
    typeof vm.cpu_usage_pct === "number"
      ? vm.cpu_usage_pct
      : typeof vm.cpu_pct === "number"
        ? vm.cpu_pct
        : 0;
  const cpu = Math.max(0, Math.min(100, rawCpu));
  const used = typeof vm.mem_used_gb === "number" ? vm.mem_used_gb : 0;
  const total = typeof vm.mem_total_gb === "number" ? vm.mem_total_gb : 0;
  const memory =
    total > 0 ? Math.max(0, Math.min(100, (used / total) * 100)) : 0;
  const gaugeStyle = { "--resource-value": `${cpu * 3.6}deg` } as CSSProperties;
  return (
    <Card className={`${styles.card} ${styles.proxmoxCard}`}>
      <VmHeader vm={vm} />
      <div className={styles.stack}>
        <div
          aria-label={`CPU ${cpu.toFixed(2)} por ciento`}
          className={styles.resourceGauge}
          role="meter"
          style={gaugeStyle}
        >
          <span>CPU</span>
          <strong>{formatter.percentage(rawCpu, 2)}</strong>
        </div>
        <div className={styles.progressBlock}>
          <div className={styles.progressLabel}>
            <span>CPU uso</span>
            <strong>{formatter.percentage(rawCpu, 2)}</strong>
          </div>
          <div className={styles.progressTrack}>
            <div
              className={usageClass(cpu)}
              style={{ height: "100%", width: `${cpu}%` }}
            />
          </div>
        </div>
        <div className={styles.progressBlock}>
          <div className={styles.progressLabel}>
            <span>Memoria</span>
            <strong>
              {total > 0
                ? `${used.toFixed(1)} / ${total.toFixed(1)} GB`
                : "N/D"}
            </strong>
          </div>
          <div className={styles.progressTrack}>
            <div
              className={usageClass(memory)}
              style={{ height: "100%", width: `${memory}%` }}
            />
          </div>
        </div>
        <DiskMetrics vm={vm} />
        {vm.status_detail_error && (
          <p className={styles.error}>
            {formatter.scalar(vm.status_detail_error)}
          </p>
        )}
      </div>
    </Card>
  );
}

function HistoricalVmCard({
  historyMap,
  vm,
}: {
  historyMap: JsonRecord | null;
  vm: JsonRecord;
}) {
  const history = vmHistory(historyMap, String(vm.vmid));
  return (
    <Card className={`${styles.card} ${styles.proxmoxCard}`}>
      <VmHeader vm={vm} />
      <div className={styles.stack}>
        <MetricHistoryChart history={history} label="CPU" metric="cpu_pct" />
        <MetricHistoryChart
          history={history}
          label="Memoria"
          metric="mem_pct"
        />
        <DiskMetrics vm={vm} />
        {vm.status_detail_error && (
          <p className={styles.error}>
            {formatter.scalar(vm.status_detail_error)}
          </p>
        )}
      </div>
    </Card>
  );
}

export function ProxmoxPage({
  client,
  data,
  onChanged,
}: {
  client: PanelexemysApiClient;
  data: JsonRecord;
  onChanged: () => Promise<void>;
}) {
  const state = reader.optionalRecord(data.state, "proxmox.state");
  const history = reader.optionalRecord(data.history, "proxmox.history");
  const historyMap = history
    ? reader.record(history.vms ?? {}, "proxmox.history.vms")
    : null;
  const persistedView = reader.string(data.view, "proxmox.view");
  if (persistedView !== "vivo" && persistedView !== "historico")
    throw new Error("Contrato inválido: proxmox.view fuera de dominio");
  const liveVms = state
    ? reader.records(state.vms ?? [], "proxmox.state.vms")
    : [];
  const historicalVms = historyMap
    ? Object.entries(historyMap).map(([vmid, value]) => {
        const envelope = reader.record(value, `proxmox.history.vms.${vmid}`);
        return {
          ...envelope,
          vmid,
          name: envelope.name ?? `VM ${vmid}`,
          status: envelope.status ?? "historico",
          uptime_human: envelope.uptime_human ?? "N/D",
          cpus: envelope.cpus ?? "N/D",
        } as JsonRecord;
      })
    : [];
  const historyOnly = liveVms.length === 0 && historicalVms.length > 0;
  const visibleView = historyOnly ? "historico" : persistedView;
  const vms = liveVms.length > 0 ? liveVms : historicalVms;
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function changeView(view: "vivo" | "historico"): Promise<void> {
    setPending(true);
    try {
      await client.setProxmoxView(view);
      await onChanged();
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPending(false);
    }
  }
  const missing =
    state && Array.isArray(state.missing) ? state.missing.map(String) : [];
  const stateError = data.state_error ?? state?.error ?? null;
  const lastUpdate =
    state && typeof state.ts === "string"
      ? state.ts
      : latestHistoryTimestamp(historyMap);
  return (
    <div className={styles.stack}>
      <div className={styles.proxmoxToolbar}>
        <p className={styles.proxmoxLastUpdate}>
          Última actualización:{" "}
          {lastUpdate ? time.formatInstant(lastUpdate) : "N/D"}
        </p>
        <p className={stateError ? styles.healthBad : styles.healthOk}>
          {stateError
            ? "Hipervisor Proxmox no responde"
            : "Hipervisor Proxmox en línea"}
        </p>
        <div className={styles.proxmoxViewControl}>
          <span>Vista</span>
          <ToggleSwitch
            checked={visibleView === "historico"}
            disabled={pending || historyOnly}
            leftLabel="En vivo"
            onChange={(checked) =>
              void changeView(checked ? "historico" : "vivo")
            }
            rightLabel="Histórico"
          />
        </div>
        {stateError && (
          <p className={styles.error}>{formatter.scalar(stateError)}</p>
        )}
        {data.history_error && (
          <p className={styles.error}>
            Histórico no disponible: {formatter.scalar(data.history_error)}
          </p>
        )}
        {historyOnly && (
          <p className={styles.error}>
            Mostrando datos históricos porque no hay snapshot reciente.
          </p>
        )}
        {missing.length > 0 && (
          <p className={styles.error}>
            VM sin datos en la última consulta: {missing.join(", ")}
          </p>
        )}
        {error && <p className={styles.error}>{error}</p>}
      </div>
      {vms.length === 0 ? (
        <Card>
          <p>Sin datos disponibles. Esperando la primera actualización.</p>
        </Card>
      ) : (
        <div className={styles.proxmoxGrid}>
          {vms
            .sort((left, right) => Number(left.vmid) - Number(right.vmid))
            .map((vm) =>
              visibleView === "vivo" ? (
                <LiveVmCard key={String(vm.vmid)} vm={vm} />
              ) : (
                <HistoricalVmCard
                  historyMap={historyMap}
                  key={String(vm.vmid)}
                  vm={vm}
                />
              ),
            )}
        </div>
      )}
    </div>
  );
}
