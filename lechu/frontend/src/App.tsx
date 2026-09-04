import { AppShell } from "@servicoop/frontend-foundation";
import { useCallback, useEffect, useMemo, useState } from "react";

import styles from "./App.module.css";
import { LechuApiClient } from "./LechuApiClient";
import { PageErrorBoundary } from "./components/PageErrorBoundary";
import { PageRenderer } from "./pages/PageRenderer";
import type { JsonRecord, NavigationContract } from "./models";

const PAGE_TITLES: Record<string, string> = {
  exemys: "exemys",
  charito: "charo-daemon",
  generadores: "generadores",
  proxmox: "proxmox",
  reles: "estado reles MiCOM",
  mantenimiento: "mantenimiento",
  mensagelo: "mensagelo",
  broker: "broker mqtt",
  email: "estado de correo",
};

function currentPage(): string {
  const segment = window.location.pathname
    .replace(/^\/lechu\/?/, "")
    .split("/")[0];
  return segment || "exemys";
}

export function App() {
  const client = useMemo(() => new LechuApiClient(), []);
  const page = currentPage();
  const [navigation, setNavigation] = useState<NavigationContract | null>(null);
  const [data, setData] = useState<JsonRecord | null>(null);
  const [dataRevision, setDataRevision] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [pageAttention, setPageAttention] = useState(false);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const nextNavigation = await client.navigation(signal);
        const currentPath = window.location.pathname.replace(/\/$/, "");
        const visiblePage = nextNavigation.items.some(
          (item) => item.href === currentPath,
        );
        if (!visiblePage) {
          const firstVisible = nextNavigation.items[0];
          if (firstVisible === undefined) {
            throw new Error("El modo actual no tiene solapas habilitadas");
          }
          window.location.replace(`${firstVisible.href}/`);
          return;
        }
        const nextData = await client.page(page, signal);
        setNavigation(nextNavigation);
        setData(nextData);
        setDataRevision((current) => current + 1);
        setError(null);
      } catch (reason) {
        if (!signal?.aborted)
          setError(reason instanceof Error ? reason.message : String(reason));
      }
    },
    [client, page],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    const timer = window.setInterval(
      () => void load(controller.signal),
      navigation?.refresh_ms ?? 10_000,
    );
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [load, navigation?.refresh_ms]);

  return (
    <AppShell productName="lechuza-server" sectionName="Comunicaciones">
      <main className={styles.main}>
        <header className={styles.header}>
          <h1
            className={pageAttention ? styles.pageTitleAttention : undefined}
          >
            {PAGE_TITLES[page] ?? "lechuza-server"}
          </h1>
        </header>

        <nav className={styles.navigation} aria-label="Secciones de lechuza-server">
          {navigation?.items.map((item) => (
            <a
              className={
                window.location.pathname.replace(/\/$/, "") === item.href
                  ? styles.active
                  : undefined
              }
              href={`${item.href}/`}
              key={item.href}
            >
              {item.label}
            </a>
          ))}
        </nav>

        {error && (
          <div className={styles.error} role="alert">
            <strong>No se pudo actualizar la vista.</strong>
            <span>{error}</span>
          </div>
        )}
        {!data && !error && (
          <p className={styles.loading}>Cargando estado operativo…</p>
        )}
        {data && (
          <PageErrorBoundary
            className={styles.error}
            resetToken={`${page}-${dataRevision}`}
          >
            <PageRenderer
              client={client}
              data={data}
              onChanged={() => load()}
              page={page}
              protectedMode={navigation?.mode === "protected"}
              onAttentionChange={setPageAttention}
            />
          </PageErrorBoundary>
        )}
      </main>
    </AppShell>
  );
}
