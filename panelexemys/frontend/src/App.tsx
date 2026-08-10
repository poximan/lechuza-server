import { AppShell, StatusBadge } from "@servicoop/frontend-foundation";
import { useCallback, useEffect, useMemo, useState } from "react";

import styles from "./App.module.css";
import { PanelexemysApiClient } from "./PanelexemysApiClient";
import { DataView } from "./components/DataView";
import { OverviewPage } from "./components/OverviewPage";
import { PageActions } from "./components/PageActions";
import type { JsonRecord, NavigationContract } from "./models";

const PAGE_TITLES: Record<string, string> = {
  overview: "Middleware Exemys",
  charito: "Charito",
  generadores: "Generadores",
  proxmox: "Proxmox",
  reles: "Relés MiCOM",
  mantenimiento: "Mantenimiento",
  mensagelo: "Mensagelo",
  broker: "Broker MQTT",
  email: "Estado de correo",
};

function currentPage(): string {
  const segment = window.location.pathname.replace(/^\/panelexemys\/?/, "").split("/")[0];
  return segment || "overview";
}

export function App() {
  const client = useMemo(() => new PanelexemysApiClient(), []);
  const page = currentPage();
  const [navigation, setNavigation] = useState<NavigationContract | null>(null);
  const [data, setData] = useState<JsonRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const [nextNavigation, nextData] = await Promise.all([
        client.navigation(signal),
        client.page(page, signal),
      ]);
      setNavigation(nextNavigation);
      setData(nextData);
      setError(null);
    } catch (reason) {
      if (!signal?.aborted) setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, [client, page]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    const timer = window.setInterval(
      () => void load(controller.signal),
      navigation?.refresh_ms ?? 10_000,
    );
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [load, navigation?.refresh_ms]);

  return (
    <AppShell productName="Panelexemys" sectionName="Comunicaciones">
      <main className={styles.main}>
        <header className={styles.header}>
          <div><p>lechuza-server</p><h1>{PAGE_TITLES[page] ?? "Panelexemys"}</h1><span>Supervisión operativa centralizada</span></div>
          <StatusBadge tone={navigation?.mode === "protected" ? "warning" : "info"}>{navigation?.mode ?? "cargando"}</StatusBadge>
        </header>

        <nav className={styles.navigation} aria-label="Secciones Panelexemys">
          {navigation?.items.map((item) => <a className={window.location.pathname.replace(/\/$/, "") === item.href ? styles.active : undefined} href={`${item.href}/`} key={item.href}>{item.label}</a>)}
        </nav>

        {error && <div className={styles.error} role="alert"><strong>No se pudo actualizar la vista.</strong><span>{error}</span></div>}
        {!data && !error && <p className={styles.loading}>Cargando estado operativo…</p>}
        {data && <PageActions client={client} data={data} onChanged={() => load()} page={page} />}
        {data && (page === "overview" ? <OverviewPage client={client} data={data} /> : <DataView data={data} />)}
      </main>
    </AppShell>
  );
}
