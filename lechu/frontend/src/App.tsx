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
  analizadores: "analiz. red",
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
  const [navigationError, setNavigationError] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [pageAttention, setPageAttention] = useState(false);

  const loadNavigation = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const nextNavigation = await client.navigation(signal);
        setNavigation(nextNavigation);
        setNavigationError(null);
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
        }
      } catch (reason) {
        if (!signal?.aborted)
          setNavigationError(
            reason instanceof Error ? reason.message : String(reason),
          );
      }
    },
    [client],
  );

  const loadPage = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const nextData = await client.page(page, signal);
        setData(nextData);
        setDataRevision((current) => current + 1);
        setPageError(null);
      } catch (reason) {
        if (!signal?.aborted)
          setPageError(reason instanceof Error ? reason.message : String(reason));
      }
    },
    [client, page],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadNavigation(controller.signal);
    void loadPage(controller.signal);
    const timer = window.setInterval(
      () => {
        void loadNavigation(controller.signal);
        void loadPage(controller.signal);
      },
      navigation?.refresh_ms ?? 10_000,
    );
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [loadNavigation, loadPage, navigation?.refresh_ms]);

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

        {navigationError && (
          <div className={styles.error} role="alert">
            <strong>No se pudo actualizar la navegación.</strong>
            <span>{navigationError}</span>
          </div>
        )}
        {pageError && (
          <div className={styles.error} role="alert">
            <strong>No se pudo actualizar la vista.</strong>
            <span>{pageError}</span>
          </div>
        )}
        {!data && !pageError && (
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
              onChanged={() => loadPage()}
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
