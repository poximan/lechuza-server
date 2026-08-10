import { Button, Card } from "@servicoop/frontend-foundation";
import { useState } from "react";

import { JsonContractReader } from "../contracts/JsonContractReader";
import { OperationalFormatter } from "../contracts/OperationalFormatter";
import type { PanelexemysApiClient } from "../PanelexemysApiClient";
import type { JsonRecord } from "../models";
import styles from "./Pages.module.css";

const reader = new JsonContractReader();
const formatter = new OperationalFormatter();

export function EmailPage({
  client,
  data,
  protectedMode,
}: {
  client: PanelexemysApiClient;
  data: JsonRecord;
  protectedMode: boolean;
}) {
  const health = reader.record(data.health, "email.health");
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<JsonRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const checks = [
    ["SMTP configurado", data.smtp_host, health.smtp],
    ["Ping host local", data.ping_local_host, health.ping_local],
    ["Ping host remoto", data.ping_remote_host, health.ping_remoto],
  ];
  async function send(): Promise<void> {
    setPending(true);
    try {
      setResult(await client.sendTestEmail());
      setError(null);
    } catch (reason) {
      setResult(null);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPending(false);
    }
  }
  return (
    <div className={styles.stack}>
      <Card>
        <h2 className={styles.sectionTitle}>Servidor de correo</h2>
        <div className={styles.emailHealthGrid}>
          {checks.map(([label, host, value]) => {
            const connected =
              String(value).trim().toLowerCase() === "conectado";
            return (
              <div className={styles.emailHealthItem} key={String(label)}>
                <span>
                  {formatter.scalar(label)} ({formatter.scalar(host)})
                </span>
                <strong
                  className={connected ? styles.healthOk : styles.healthBad}
                >
                  {formatter.scalar(value)}
                </strong>
              </div>
            );
          })}
        </div>
      </Card>
      <div className={styles.emailAction}>
        <Button
          disabled={pending || !protectedMode}
          onClick={() => void send()}
        >
          {pending ? "Enviando…" : "Probar Email (async)"}
        </Button>
        {!protectedMode && (
          <p className={styles.muted}>
            El envío de prueba requiere el acceso protegido.
          </p>
        )}
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        {result && (
          <div className={result.ok === true ? styles.success : styles.error}>
            <strong>
              {result.ok === true
                ? "Pedido aceptado por mensagelo (cola async)."
                : "No se pudo encolar el email de prueba."}
            </strong>
            <p>Destinatarios: {formatter.scalar(result.recipients)}</p>
            <p>Detalle: {formatter.scalar(result.detail)}</p>
            {result.event_error && (
              <p>
                Evento MQTT no publicado: {formatter.scalar(result.event_error)}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
