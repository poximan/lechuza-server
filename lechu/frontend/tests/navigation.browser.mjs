import assert from "node:assert/strict";
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || "playwright-core");

const origin = process.env.LECHU_PREVIEW_ORIGIN || "http://lechu-navigation-preview:8052";
const items = [
  ["exemys", "exemys", true], ["charito", "charito", true],
  ["generadores", "generadores", false], ["proxmox", "proxmox", true],
  ["reles MiCOM", "reles", false], ["analiz. red", "analizadores", false],
  ["Caudalímetros", "caudalimetros", false], ["mantenimiento", "mantenimiento", true],
  ["mensagelo", "mensagelo", true], ["broker", "broker", true], ["correo", "email", true],
].map(([label, page, protectedPage]) => ({ label, href: `/lechu/${page}`, protected: protectedPage }));
const ts = "2026-10-29T10:00:00Z";
const GiB = 1024 ** 3;
const proxmox = {
  view: "vivo", history: { vms: {}, meta: {} }, state_error: null, history_error: null,
  state: { node: "pve-prueba", ts, source_status: "online", stale: false, missing: [],
    host_storage: { rootfs: { used_bytes: 128 * GiB, total_bytes: 512 * GiB, used_pct: 25 },
      storages: [{ id: "disco1", type: "dir", active: true, shared: false, used_bytes: 512 * GiB, total_bytes: 1024 * GiB, used_pct: 50 }], errors: [] },
    vms: [100, 102, 107].map(vmid => ({ vmid, name: `vhost ${vmid}`, status: "running", cpus: 2, uptime_human: "2d",
      cpu_pct: 25, mem_used_gb: 2, mem_total_gb: 4, disk_read_bytes: 3 * GiB, disk_write_bytes: GiB,
      virtual_disks: [{ id: "scsi0", volume: `disco1:${vmid}/vm-${vmid}-disk-0.qcow2`, total_bytes: 32 * GiB }],
      filesystems: [{ name: "sda1", mountpoint: "/", type: "ext4", used_bytes: 8 * GiB, total_bytes: 32 * GiB, used_pct: 25 }],
      disk_usage_status: "ok", disk_usage_error: null })) },
};
function generator(unsafe) {
  return { unsafe_state: unsafe, error: null, status: "online", measured_at: ts,
    interruptor_linea: { bit: 1, estado: "cerrado" },
    interruptor_grupo: { bit: unsafe ? 1 : 0, estado: unsafe ? "cerrado" : "abierto" },
    summary: unsafe ? "Estado peligroso: ambos interruptores cerrados" : "Carga alimentada por la red" };
}
const generators = { estivariz: generator(true), fontana: generator(false) };
const exemys = { descriptions: {}, summary: { summary: { ts }, states: {}, disconnected: [], unavailable: [] },
  modem: { state: "abierto", ip: "192.0.2.10", port: 1234, provider: "Globalping", nodes: [], attempts: [] },
  thresholds: { red_below: 80, yellow_below: 95 }, links: {}, reference_now: ts };
const browser = await chromium.launch({ executablePath: "/usr/bin/chromium", args: ["--no-sandbox", "--disable-dev-shm-usage"] });
const errors = [], writes = [];

async function geometry(page, width) {
  const result = await page.evaluate(() => {
    const main = document.querySelector("main.sc-page");
    const nav = main.querySelector("nav");
    const content = main.querySelector(":scope > section");
    const links = [...nav.querySelectorAll("a")];
    return { scroll: document.documentElement.scrollWidth, viewport: innerWidth,
      main: main.getBoundingClientRect().toJSON(), nav: nav.getBoundingClientRect().toJSON(),
      content: content.getBoundingClientRect().toJSON(),
      first: links[0].getBoundingClientRect().toJSON(), second: links[1].getBoundingClientRect().toJSON(),
      overflow: getComputedStyle(nav).overflowY,
      offenders: [...main.querySelectorAll("*")].filter(node => !node.closest("svg")
        && node.getBoundingClientRect().right > innerWidth + 1).slice(0, 6).map(node => `${node.tagName}.${node.className}`) };
  });
  assert.ok(result.scroll <= width + 1, JSON.stringify(result));
  assert.ok(result.nav.right < result.content.left, "La barra debe estar a la izquierda del contenido");
  assert.ok(result.second.top >= result.first.bottom, "Los accesos deben estar apilados verticalmente");
  assert.equal(result.overflow, "auto");
  assert.ok(result.nav.height <= 960, "La barra debe limitar su altura al viewport");
}

try {
  for (const width of [320, 768, 1440]) {
    for (const theme of ["light", "dark"]) {
      let mode = "protected", changedLabel = false, navigationRequests = 0, documentRequests = 0;
      const context = await browser.newContext({ viewport: { width, height: 960 } });
      await context.addInitScript(value => localStorage.setItem("servicoop-theme", value), theme);
      const page = await context.newPage();
      page.on("pageerror", error => errors.push(error.message));
      page.on("request", request => { if (request.isNavigationRequest()) documentRequests++; });
      await page.route("**/portal/events", route => route.fulfill({ status: 204 }));
      await page.route("**/lechu/api/**", route => {
        const request = route.request(), pathname = new URL(request.url()).pathname;
        if (request.method() !== "GET") {
          writes.push({ method: request.method(), pathname });
          return route.fulfill({ status: 405, json: { error: "Acción no permitida en pruebas" } });
        }
        if (pathname.endsWith("/navigation")) {
          navigationRequests++;
          const visible = items.filter(item => mode === "protected" || !item.protected)
            .map(item => ({ ...item, label: changedLabel && item.href.endsWith("/proxmox") ? "Proxmox · sala principal" : item.label }));
          return route.fulfill({ json: { base_path: "/lechu", mode, refresh_ms: 1000, items: visible } });
        }
        const data = pathname.endsWith("/generadores") ? generators
          : pathname.endsWith("/exemys") ? exemys : proxmox;
        return route.fulfill({ json: data });
      });
      await page.goto(`${origin}/lechu/proxmox/`);
      await page.getByRole("status", { name: "Cargando lechuza-server", exact: true }).waitFor({ state: "detached", timeout: 10000 });
      const nav = page.getByRole("navigation", { name: "Secciones de lechuza-server" });
      assert.equal(await nav.getByRole("link").count(), 11);
      assert.equal(await page.locator("main > header, main h1, main > img").count(), 0);
      assert.equal(await nav.locator('a[aria-current="page"]').getAttribute("href"), "/lechu/proxmox/");
      for (const item of items) {
        const link = nav.getByRole("link", { name: item.label, exact: true });
        assert.equal(await link.getAttribute("title"), item.label);
        assert.equal(await link.locator("svg").count(), 1);
      }
      await nav.evaluate(node => { window.originalNavigation = node; });
      await geometry(page, width);
      await page.evaluate(() => scrollTo(0, 700));
      assert.ok(await page.evaluate(() => scrollY > 0));
      const pinned = await nav.boundingBox();
      const shell = await page.locator("main").evaluate(node => node.parentElement.querySelector("header").getBoundingClientRect().bottom);
      assert.ok(pinned.y >= shell - 1, "La barra fija debe quedar debajo de la cabecera global");
      const proxmoxLink = nav.getByRole("link", { name: "proxmox", exact: true });
      await proxmoxLink.focus();
      await page.keyboard.press("ArrowDown");
      assert.equal(await page.evaluate(() => document.activeElement.getAttribute("href")), "/lechu/reles/");
      await page.keyboard.press("ArrowUp");
      assert.equal(await page.evaluate(() => document.activeElement.getAttribute("href")), "/lechu/proxmox/");
      await page.keyboard.press("Home");
      assert.equal(await page.evaluate(() => document.activeElement.getAttribute("href")), "/lechu/exemys/");
      await page.keyboard.press("End");
      assert.equal(await page.evaluate(() => document.activeElement.getAttribute("href")), "/lechu/email/");
      assert.equal(new URL(page.url()).pathname, "/lechu/proxmox/");

      await nav.getByRole("link", { name: "generadores", exact: true }).focus();
      await page.keyboard.press("Enter");
      await page.getByRole("heading", { name: "edificio estivariz", exact: true }).waitFor();
      assert.equal(new URL(page.url()).pathname, "/lechu/generadores/");
      assert.equal(await page.evaluate(() => scrollY), 0);
      assert.ok(await page.getByText("Estado peligroso: ambos interruptores cerrados", { exact: true }).isVisible());
      const unsafe = page.locator('[data-sc-card]').filter({ has: page.getByRole("heading", { name: "edificio estivariz", exact: true }) });
      assert.ok((await unsafe.evaluate(node => getComputedStyle(node).boxShadow)).includes("1px"), "Debe conservarse la alerta de la tarjeta");
      await geometry(page, width);
      await nav.getByRole("link", { name: "exemys", exact: true }).click();
      await page.getByRole("heading", { name: "Grado conectividad", exact: true }).waitFor();
      await geometry(page, width);
      await page.goBack();
      await page.getByRole("heading", { name: "edificio estivariz", exact: true }).waitFor();
      await nav.getByRole("link", { name: "proxmox", exact: true }).click();
      await page.getByRole("heading", { name: /Almacenamiento de Proxmox/ }).waitFor();
      assert.equal(documentRequests, 1, "Cambiar de sección y volver no debe recargar el documento");
      assert.equal(await page.getByRole("status", { name: "Cargando lechuza-server", exact: true }).count(), 0);
      assert.ok(await nav.evaluate(node => node === window.originalNavigation));
      if (process.env.NAV_SCREENSHOTS === "1" && theme === "light" && [320, 1440].includes(width))
        await page.screenshot({ path: `/tmp/lechu-navigation-${width}.png` });
      changedLabel = true;
      await nav.getByRole("link", { name: "Proxmox · sala principal", exact: true }).waitFor();
      assert.equal(await nav.locator('a[aria-current="page"]').getAttribute("aria-label"), "Proxmox · sala principal");
      assert.ok(navigationRequests > 1);
      mode = "secure";
      await page.waitForFunction(() => document.querySelector('nav[aria-label="Secciones de lechuza-server"]').querySelectorAll("a").length === 4);
      await page.waitForURL(url => url.pathname === "/lechu/generadores/");
      assert.equal(await nav.getByRole("link", { name: /proxmox/i }).count(), 0);
      assert.equal(await nav.locator('a[aria-current="page"]').getAttribute("href"), "/lechu/generadores/");
      assert.equal(await page.getByRole("status", { name: "Cargando lechuza-server", exact: true }).count(), 0);
      assert.equal(documentRequests, 1);
      await context.close();
      console.log(`Lechu ${width}px ${theme}: barra vertical, encabezado eliminado, teclado, alertas locales, SPA, splash único, nombres del backend y permisos OK`);
    }
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(writes, []);
} finally {
  await browser.close();
}
