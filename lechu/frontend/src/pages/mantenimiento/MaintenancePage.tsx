import { Button, Card } from "@servicoop/frontend-foundation";
import { useEffect, useState } from "react";

import type { LechuApiClient } from "../../LechuApiClient";
import type { JsonRecord } from "../../models";
import commonStyles from "../Pages.module.css";
import {
  readMaintenanceContract,
  readWakeOperation,
  type MaintenancePhone,
  type MaintenancePortMapping,
  type MaintenanceTopology,
  type WakeOperation,
} from "./MaintenanceContract";
import styles from "./MaintenancePage.module.css";

function TopologyImage({ topology }: { topology: MaintenanceTopology }) {
  return (
    <a
      className={styles.topologyLink}
      href={topology.url}
      rel="noreferrer"
      target="_blank"
      title="Abrir topología en tamaño completo"
    >
      <img
        alt={topology.description}
        className={styles.topologyImage}
        src={topology.url}
      />
    </a>
  );
}

function PhoneColumn({ title, items }: { title: string; items: MaintenancePhone[] }) {
  return (
    <Card>
      <h3>{title}</h3>
      <ul className={styles.phoneList}>
        {items.map((item, index) => (
          <li key={[item.number, index].join("-")}>
            <strong>{item.number}</strong>
            {item.comment ? (
              <span className={commonStyles.muted}> ({item.comment})</span>
            ) : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function PortMappings({ items }: { items: MaintenancePortMapping[] }) {
  return (
    <Card>
      <div className={commonStyles.cardHeader}>
        <h2>Mapeo de puertos (docker &lt;-&gt; localhost &lt;-&gt; https)</h2>
      </div>
      <div className={commonStyles.tableWrap}>
        <table className={commonStyles.table}>
          <thead>
            <tr>
              <th>Servicio</th>
              <th>Docker interno</th>
              <th>HTTPS público</th>
              <th>Localhost pruebas</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, index) => (
              <tr key={[item.service, index].join("-")}>
                <td>{item.service}</td>
                <td><code>{item.internal}</code></td>
                <td><code>{item.external ?? "no expuesto"}</code></td>
                <td><code>{item.localhost}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

const statusText: Record<WakeOperation["status"], string> = {
  accepted: "Solicitud aceptada",
  packet_sent: "Paquete mágico enviado; esperando SSH",
  ssh_open: "Equipo encendido: SSH disponible",
  failed: "El encendido no se confirmó",
};

function WakeOnLanControl({
  client,
  protectedMode,
}: {
  client: LechuApiClient;
  protectedMode: boolean;
}) {
  const [operation, setOperation] = useState<WakeOperation | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active =
    operation?.status === "accepted" || operation?.status === "packet_sent";

  useEffect(() => {
    if (!active || operation === null) return undefined;
    const controller = new AbortController();
    const requestId = operation.requestId;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll(): Promise<void> {
      try {
        const current = readWakeOperation(
          await client.wakeOnLanStatus(requestId, controller.signal),
        );
        setOperation(current);
        setError(null);
        if (current.status === "accepted" || current.status === "packet_sent") {
          timer = setTimeout(() => void poll(), 2000);
        }
      } catch (reason) {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : String(reason));
          timer = setTimeout(() => void poll(), 2000);
        }
      }
    }
    timer = setTimeout(() => void poll(), 1000);
    return () => {
      controller.abort();
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [active, client, operation?.requestId]);

  async function start(): Promise<void> {
    setPending(true);
    try {
      setOperation(readWakeOperation(await client.startWakeOnLan()));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPending(false);
    }
  }

  return (
    <Card>
      <div className={commonStyles.cardHeader}>
        <div>
          <h2 className={styles.wolTitle}>
            <svg
              aria-hidden="true"
              className={styles.monkIcon}
              viewBox="0 0 24 24"
            >
              <path d="M12,2C8.7,2 6,4.7 6,8v2.2C4.8,12 4,14.2 4,16.6V22h16v-5.4c0,-2.4 -0.8,-4.6 -2,-6.4V8c0,-3.3 -2.7,-6 -6,-6zM12,5c1.7,0 3,1.3 3,3 0,0.7 -0.2,1.3 -0.6,1.8 -0.7,-0.5 -1.5,-0.8 -2.4,-0.8s-1.7,0.3 -2.4,0.8C9.2,9.3 9,8.7 9,8c0,-1.7 1.3,-3 3,-3zM8,13.2c1,-0.8 2.4,-1.2 4,-1.2s3,0.4 4,1.2c0.6,1 1,2.2 1,3.4V19H7v-2.4c0,-1.2 0.4,-2.4 1,-3.4z" />
            </svg>
            wololo
          </h2>
        </div>
        <Button
          disabled={pending || active || !protectedMode}
          onClick={() => void start()}
        >
          {pending
            ? "Solicitando…"
            : active
              ? "Esperando SSH…"
              : "Despertar equipo"}
        </Button>
      </div>
      {!protectedMode && (
        <p className={commonStyles.muted}>
          Esta acción requiere el acceso protegido.
        </p>
      )}
      {error && (
        <p className={styles.wolError} role="alert">
          {error}
        </p>
      )}
      {operation && (
        <div
          className={
            operation.status === "failed" ? styles.wolError : styles.wolStatus
          }
          role="status"
        >
          <strong>{statusText[operation.status]}</strong>
          <dl className={styles.wolDetails}>
            <div>
              <dt>Destino</dt>
              <dd>
                {operation.targetIp}:{operation.targetPort}
              </dd>
            </div>
            <div>
              <dt>Broadcast</dt>
              <dd>{operation.broadcastIp}:9</dd>
            </div>
            <div>
              <dt>Solicitud</dt>
              <dd>
                <code>{operation.requestId}</code>
              </dd>
            </div>
            <div>
              <dt>Actualizado</dt>
              <dd>{operation.updatedAt}</dd>
            </div>
            {operation.packetBytes !== null && (
              <div>
                <dt>UDP enviado</dt>
                <dd>{operation.packetBytes} bytes</dd>
              </div>
            )}
            {operation.error && (
              <div>
                <dt>Error</dt>
                <dd>{operation.error}</dd>
              </div>
            )}
          </dl>
        </div>
      )}
    </Card>
  );
}

export function MaintenancePage({
  client,
  data,
  protectedMode,
}: {
  client: LechuApiClient;
  data: JsonRecord;
  protectedMode: boolean;
}) {
  const contract = readMaintenanceContract(data);
  return (
    <div className={commonStyles.stack}>
      <WakeOnLanControl client={client} protectedMode={protectedMode} />
      <Card>
        <div className={commonStyles.cardHeader}>
          <div>
            <h2>Topología de red</h2>
            <p className={commonStyles.muted}>
              Seleccione la imagen para verla en tamaño completo.
            </p>
          </div>
        </div>
        <div className={styles.topologyViewport}>
          <TopologyImage topology={contract.topology} />
        </div>
      </Card>
      <section className={commonStyles.stack}>
        <h2 className={commonStyles.sectionTitle}>Líneas telefónicas</h2>
        <div className={styles.phoneGrid}>
          <PhoneColumn items={contract.phones.fontana} title="Fontana" />
          <PhoneColumn items={contract.phones.estivariz} title="Estivariz" />
        </div>
        <div className={styles.phoneGeneral}>
          <PhoneColumn items={contract.phones.general} title="General" />
        </div>
      </section>
      <PortMappings items={contract.portMappings} />
    </div>
  );
}
