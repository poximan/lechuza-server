import { AppShell, StartupSplash } from "@servicoop/frontend-foundation";
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
  caudalimetros: "Caudalímetros",
  mantenimiento: "mantenimiento",
  mensagelo: "mensagelo",
  broker: "broker mqtt",
  email: "estado de correo",
};

function currentPage(path: string): string {
  const segment = path
    .replace(/^\/lechu\/?/, "")
    .split("/")[0];
  return segment || "exemys";
}

export function App() {
  const client = useMemo(() => new LechuApiClient(), []);
  const [path, setPath] = useState(window.location.pathname);
  const page = currentPage(path);
  const [navigation, setNavigation] = useState<NavigationContract | null>(null);
  const [snapshot, setSnapshot] = useState<{ page: string; data: JsonRecord } | null>(null);
  const data = snapshot?.page === page ? snapshot.data : null;
  const [dataRevision, setDataRevision] = useState(0);
  const [navigationError, setNavigationError] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [pageAttention, setPageAttention] = useState(false);

  const updatePath = useCallback(() => {
    setPath(window.location.pathname);
    setPageError(null);
    setPageAttention(false);
  }, []);

  const navigate = useCallback((href: string, replace = false) => {
    if (href === window.location.pathname) return;
    if (replace) window.history.replaceState(null, "", href);
    else window.history.pushState(null, "", href);
    updatePath();
  }, [updatePath]);

  useEffect(() => {
    window.addEventListener("popstate", updatePath);
    return () => window.removeEventListener("popstate", updatePath);
  }, [updatePath]);

  const loadNavigation = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const nextNavigation = await client.navigation(signal);
        if (signal?.aborted) return;
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
          navigate(`${firstVisible.href}/`, true);
        }
      } catch (reason) {
        if (!signal?.aborted)
          setNavigationError(
            reason instanceof Error ? reason.message : String(reason),
          );
      }
    },
    [client, navigate],
  );

  const loadPage = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const nextData = await client.page(page, signal);
        if (signal?.aborted || currentPage(window.location.pathname) !== page) return;
        setSnapshot({ page, data: nextData });
        setDataRevision((current) => current + 1);
        setPageError(null);
      } catch (reason) {
        if (!signal?.aborted && currentPage(window.location.pathname) === page)
          setPageError(reason instanceof Error ? reason.message : String(reason));
      }
    },
    [client, page],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadNavigation(controller.signal);
    const timer = window.setInterval(
      () => { void loadNavigation(controller.signal); },
      navigation?.refresh_ms ?? 10_000,
    );
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [loadNavigation, navigation?.refresh_ms]);

  useEffect(() => {
    const controller = new AbortController();
    void loadPage(controller.signal);
    const timer = window.setInterval(
      () => { void loadPage(controller.signal); }, navigation?.refresh_ms ?? 10_000,
    );
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [loadPage, navigation?.refresh_ms]);

  return (
    <StartupSplash
      productName="lechuza-server"
      logoSrc={`${import.meta.env.BASE_URL}icono.png`}
      ready={(navigation !== null || navigationError !== null) && (data !== null || pageError !== null)}
    >
      <AppShell productName="lechuza-server" sectionName="Comunicaciones">
        <main className={`sc-page ${styles.main}`}>
          <header className={styles.header}>
            <img className={styles.productLogo} src={`${import.meta.env.BASE_URL}icono.png`} alt="Logo de lechuza-server" width="96" height="96" />
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
                  path.replace(/\/$/, "") === item.href
                    ? styles.active
                    : undefined
                }
                href={`${item.href}/`}
                aria-current={path.replace(/\/$/, "") === item.href ? "page" : undefined}
                onClick={(event) => {
                  if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
                  event.preventDefault();
                  navigate(`${item.href}/`);
                }}
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
              key={page}
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
    </StartupSplash>
  );
}
