import { Button, Card } from "@servicoop/frontend-foundation";
import { useState } from "react";

import type { PanelexemysApiClient } from "../PanelexemysApiClient";
import type { JsonRecord } from "../models";
import styles from "../App.module.css";

export interface PageActionsProps {
  client: PanelexemysApiClient;
  data: JsonRecord;
  onChanged: () => Promise<void>;
  page: string;
}

export function PageActions({ client, data, onChanged, page }: PageActionsProps) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function execute(action: () => Promise<JsonRecord>): Promise<void> {
    setPending(true);
    try {
      await action();
      await onChanged();
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPending(false);
    }
  }

  if (page === "reles") {
    const enabled = data.observer_enabled === true;
    return <Card className={styles.actionCard}><span>Observación MiCOM</span>{error && <strong role="alert">{error}</strong>}<Button disabled={pending} onClick={() => void execute(() => client.setRelesObserver(!enabled))}>{enabled ? "Deshabilitar" : "Habilitar"}</Button></Card>;
  }
  if (page === "broker") {
    const connected = data.status !== "desconectado";
    return <Card className={styles.actionCard}><span>Conexión MQTT</span>{error && <strong role="alert">{error}</strong>}<Button disabled={pending} onClick={() => void execute(() => client.setBrokerConnection(!connected))}>{connected ? "Desconectar" : "Conectar"}</Button></Card>;
  }
  if (page === "email") {
    return <Card className={styles.actionCard}><span>Prueba de mensajería</span>{error && <strong role="alert">{error}</strong>}<Button disabled={pending} onClick={() => void execute(() => client.sendTestEmail())}>Enviar email de prueba</Button></Card>;
  }
  return null;
}
