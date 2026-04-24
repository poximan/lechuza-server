const REFRESH_MS = 10000;

const state = {
    groups: [],
    error: "",
    lastRefresh: "",
    refreshing: false,
    loaded: false,
};

function stateToClass(s) {
    if (s === "cerrado") return "switch-closed";
    if (s === "abierto") return "switch-open";
    return "switch-unknown";
}

function pillClass(s) {
    if (s === "cerrado") return "state-pill pill-closed";
    if (s === "abierto") return "state-pill pill-open";
    return "state-pill pill-unknown";
}

const SCADA_BASE = (() => {
    const path = window.location.pathname || "/";
    if (path === "/scada" || path.startsWith("/scada/")) {
        return "/scada";
    }
    return "";
})();

const API_STATE_URL = `${SCADA_BASE}/api/mimic/state`;

async function fetchState() {
    try {
        state.refreshing = true;
        render();
        const response = await fetch(API_STATE_URL);
        if (!response.ok) {
            throw new Error(`API devolvio ${response.status}`);
        }
        const data = await response.json();
        state.groups = data.groups || [];
        state.lastRefresh = new Date().toLocaleTimeString();
        state.error = "";
        state.loaded = true;
    } catch (err) {
        state.error = err.message || "No se pudo actualizar";
    } finally {
        state.refreshing = false;
        render();
    }
}

function buildSwitches(elements) {
    const spacing = 180;
    const offset = 120;
    const busY = 90;
    const circleY = 130;
    const contactY = 230;
    const tailBottom = contactY + 40;
    const openOffset = 45;
    return elements
        .map((el, idx) => {
            const x = offset + idx * spacing;
            const cls = stateToClass(el.state);
            const blade = (() => {
                if (cls === "switch-closed") {
                    return `<line x1="${x}" y1="${circleY}" x2="${x}" y2="${contactY}" class="breaker-blade blade-closed" />`;
                }
                if (cls === "switch-open") {
                    const targetX = x + openOffset;
                    return `<line x1="${x}" y1="${circleY}" x2="${targetX}" y2="${contactY}" class="breaker-blade blade-open" />`;
                }
                return `<line x1="${x}" y1="${circleY}" x2="${x}" y2="${contactY}" class="breaker-blade blade-unknown" stroke-dasharray="8 6" />`;
            })();
            return `
            <text x="${x}" y="60" text-anchor="middle" class="switch-label">${el.label}</text>
            <line x1="${x}" y1="${busY}" x2="${x}" y2="${circleY}" class="feeder-line" />
            <circle cx="${x}" cy="${circleY}" r="10" class="feeder-node" />
            ${blade}
            <line x1="${x - 12}" y1="${contactY + 16}" x2="${x + 12}" y2="${contactY - 16}" class="contact-arm" />
            <line x1="${x + 12}" y1="${contactY + 16}" x2="${x - 12}" y2="${contactY - 16}" class="contact-arm" />
            <line x1="${x}" y1="${contactY}" x2="${x}" y2="${tailBottom}" class="switch-tail" />
            <circle cx="${x}" cy="${tailBottom}" r="8" class="tail-node" />
            `;
        })
        .join("");
}

function buildCards(elements) {
    return elements
        .map(
            (el) => `
        <div class="status-card">
            <h3>${el.label}</h3>
            <div class="status-meta">Tag: ${el.tag}</div>
            <div class="status-meta">Ultimo dato: ${el.updated_at || "sin datos"}</div>
            <div class="${pillClass(el.state)}">
                <strong>${(el.state || "desconocido").toUpperCase()}</strong>
                ${el.raw_value ? `<span>(valor ${el.raw_value})</span>` : ""}
            </div>
        </div>`
        )
        .join("");
}

function buildGroupSection(group) {
    const elements = group.elements || [];
    const svgContent = buildSwitches(elements);
    const cards = buildCards(elements);
    const count = elements.length || 1;
    const width = Math.max(1024, 200 + (count - 1) * 180);
    return `
        <section class="group-section">
            <h2>${group.label}</h2>
            <div class="mimic-wrapper">
                <svg viewBox="0 0 ${width} 360">
                    <line x1="80" y1="90" x2="${width - 80}" y2="90" class="bus-line" />
                    ${svgContent}
                </svg>
                <div class="status-board">
                    ${cards}
                </div>
            </div>
        </section>`;
}

function render() {
    const app = document.getElementById("app");
    if (!app) return;
    app.innerHTML = `
        <div>
            <header>
                <div>
                    <h1>SCADA Citec</h1>
                    <div class="refresh-info">Ultima actualizacion: ${state.lastRefresh || "sin datos"}</div>
                </div>
                <button class="refresh-btn" ${state.refreshing ? "disabled" : ""} id="refresh-btn">
                    ${state.refreshing ? "Actualizando..." : "Actualizar ahora"}
                </button>
            </header>
            ${state.error ? `<div class="error-box">${state.error}</div>` : ""}
            ${!state.loaded ? `<div class="loading-box">Inicializando lectura de SCADA...</div>` : ""}
            ${state.loaded && state.groups.length === 0 ? `<p>No hay tags disponibles.</p>` : state.groups.map(buildGroupSection).join("")}
        </div>`;
    const btn = document.getElementById("refresh-btn");
    if (btn) {
        btn.addEventListener("click", () => {
            if (!state.refreshing) {
                fetchState();
            }
        });
    }
}

document.addEventListener("DOMContentLoaded", () => {
    render();
    fetchState();
    setInterval(fetchState, REFRESH_MS);
});
