import { Card, StatusBadge } from "@servicoop/frontend-foundation";
import { useEffect, useMemo, useState } from "react";

import { AlarmeroApiClient } from "../AlarmeroApiClient";
import type { AlarmCatalogItem } from "../AlarmModels";
import styles from "./NotificationSettings.module.css";

const CATALOG_REFRESH_MILLISECONDS = 20_000;

function duration(seconds: number): string {
  return seconds % 60 === 0 ? `${seconds / 60} min` : `${seconds} s`;
}

export function NotificationSettings() {
  const client = useMemo(
    () => new AlarmeroApiClient(new URL("./", document.baseURI)),
    [],
  );
  const [items, setItems] = useState<AlarmCatalogItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const load = () => {
      void client.getCatalog(controller.signal)
        .then((catalog) => {
          setItems(catalog);
          setError(null);
        })
        .catch((reason: unknown) => {
          if (!controller.signal.aborted) {
            setError(reason instanceof Error ? reason.message : "No se pudo leer el catálogo");
          }
        });
    };
    load();
    const timer = window.setInterval(load, CATALOG_REFRESH_MILLISECONDS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [client]);

  const update = async (item: AlarmCatalogItem, field: "send_start" | "send_end", checked: boolean) => {
    const rowKey = `${item.source_id}/${item.alarm_key}`;
    const sendStart = field === "send_start" ? checked : item.send_start === 1;
    const sendEnd = field === "send_end" ? checked : item.send_end === 1;
    setSaving(rowKey);
    try {
      await client.updateNotificationSettings(item, sendStart, sendEnd);
      setItems((current) => current.map((entry) => (
        entry.source_id === item.source_id && entry.alarm_key === item.alarm_key
          ? { ...entry, send_start: Number(sendStart), send_end: Number(sendEnd) }
          : entry
      )));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar la configuración");
    } finally {
      setSaving(null);
    }
  };

  const split = Math.ceil(items.length / 2);
  const columns = [items.slice(0, split), items.slice(split)];

  return (
    <Card>
      <div className={styles.heading}>
        <div><h2>Notificaciones</h2><p>Envío selectivo para los flancos confirmados.</p></div>
        <StatusBadge tone={error ? "danger" : "neutral"}>{error ?? `${items.length} alarmas`}</StatusBadge>
      </div>
      <div className={styles.columns}>
        {columns.map((column, columnIndex) => (
          <div className={styles.list} key={columnIndex}>
            {column.map((item) => {
              const rowKey = `${item.source_id}/${item.alarm_key}`;
              return (
                <div className={styles.row} key={rowKey}>
                  <div className={styles.identity}>
                    <span>{item.source_id}</span>
                    <strong>{item.title}</strong>
                    <code>{item.alarm_key}</code>
                  </div>
                  <div className={styles.timing}>
                    <span>Confirmación: {duration(item.activation_seconds)}</span>
                    <span>Reset: {duration(item.recovery_seconds)}</span>
                  </div>
                  <div className={styles.switches}>
                    <label>
                      <input aria-label={`Enviar inicio de ${item.title}`} checked={item.send_start === 1} disabled={saving === rowKey} onChange={(event) => void update(item, "send_start", event.target.checked)} type="checkbox" />
                      Inicio
                    </label>
                    <label>
                      <input aria-label={`Enviar fin de ${item.title}`} checked={item.send_end === 1} disabled={saving === rowKey} onChange={(event) => void update(item, "send_end", event.target.checked)} type="checkbox" />
                      Fin
                    </label>
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </Card>
  );
}
