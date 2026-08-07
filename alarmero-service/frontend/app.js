(function () {
  "use strict";

  let selectedFilter = "active";
  const labels = {
    potential: "Potencial", active: "Activa", recovering: "Recuperando", resolved: "Resuelta"
  };
  const dispatchLabels = {
    pending: "Aceptado / en cola", processing: "Enviando por SMTP",
    sent: "Enviado por SMTP", failed: "Falló el envío"
  };

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>'"]/g, function (char) {
      return {"&":"&amp;", "<":"&lt;", ">":"&gt;", "'":"&#39;", '"':"&quot;"}[char];
    });
  }

  function formatDate(value) {
    if (!value) return "—";
    return new Intl.DateTimeFormat("es-AR", {dateStyle: "short", timeStyle: "short"}).format(new Date(value));
  }

  function age(value, endValue) {
    if (!value) return "—";
    const minutes = Math.max(0, Math.floor((new Date(endValue || Date.now()) - new Date(value)) / 60000));
    if (minutes < 60) return minutes + " min";
    const hours = Math.floor(minutes / 60);
    if (hours < 48) return hours + " h " + (minutes % 60) + " min";
    return Math.floor(hours / 24) + " d " + (hours % 24) + " h";
  }

  function minutes(value) {
    return value == null ? "—" : Number(value).toLocaleString("es-AR", {maximumFractionDigits: 1}) + " min";
  }

  async function json(path) {
    const response = await fetch(path, {credentials: "same-origin"});
    if (!response.ok) throw new Error(path + " respondió " + response.status);
    return response.json();
  }

  function renderIncidents(items) {
    const body = document.getElementById("incidents-body");
    const empty = document.getElementById("incidents-empty");
    empty.classList.toggle("hidden", items.length !== 0);
    body.innerHTML = items.map(function (item) {
      const recipients = item.recipients.length ? item.recipients.join(", ") : "—";
      const dispatchStatus = item.dispatch_status || "not_requested";
      const dispatchText = dispatchLabels[dispatchStatus] || (item.notified ? "Aceptado" : "No solicitado");
      return "<tr>" +
        '<td><span class="badge ' + escapeHtml(item.status) + '">' + escapeHtml(labels[item.status] || item.status) + "</span></td>" +
        '<td><span class="alarm-title">' + escapeHtml(item.title) + '</span><span class="alarm-key">' + escapeHtml(item.alarm_key) + "</span></td>" +
        "<td>" + escapeHtml(formatDate(item.first_seen_at)) + "</td>" +
        "<td>" + escapeHtml(age(item.first_seen_at, item.resolved_at)) + "</td>" +
        "<td>" + escapeHtml(minutes(item.expected_clearance_minutes)) + "</td>" +
        '<td class="dispatch-' + escapeHtml(dispatchStatus) + '" title="' + escapeHtml(item.dispatch_error || "") + '">' + escapeHtml(dispatchText) + "</td>" +
        '<td class="muted">' + escapeHtml(recipients) + "</td></tr>";
    }).join("");
  }

  function renderDashboard(data) {
    ["potential", "active", "recovering", "resolved"].forEach(function (key) {
      document.getElementById("count-" + key).textContent = data.counts[key] || 0;
    });
    const maximum = Math.max(1, ...data.frequent.map(function (item) { return item.total; }));
    document.getElementById("frequent-list").innerHTML = data.frequent.map(function (item) {
      return '<div class="rank-item"><span class="rank-label" title="' + escapeHtml(item.title) + '">' +
        escapeHtml(item.title) + '</span><div class="rank-track"><div class="rank-bar" style="width:' +
        Math.round(item.total * 100 / maximum) + '%"></div></div><span class="rank-count">' + item.total + "</span></div>";
    }).join("") || '<p class="empty">Aún no hay alarmas confirmadas.</p>';

    const clearanceBody = document.getElementById("clearance-body");
    document.getElementById("clearance-empty").classList.toggle("hidden", data.clearance.length !== 0);
    clearanceBody.innerHTML = data.clearance.map(function (item) {
      return "<tr><td>" + escapeHtml(item.title) + "</td><td>" + minutes(item.configured_minutes) +
        "</td><td>" + minutes(item.median_minutes) + "</td><td>" + minutes(item.p90_minutes) +
        "</td><td>" + item.sample_count + "</td></tr>";
    }).join("");
  }

  async function refresh() {
    const syncBox = document.getElementById("sync-state");
    try {
      const values = await Promise.all([
        json("api/incidents?filter=" + encodeURIComponent(selectedFilter) + "&limit=1000"),
        json("api/dashboard"), json("health")
      ]);
      renderIncidents(values[0].items);
      renderDashboard(values[1]);
      const sync = values[2].sync;
      syncBox.className = "sync " + sync.state;
      syncBox.textContent = sync.state === "ok" ? "Fuentes sincronizadas" : "Sincronización degradada";
      syncBox.title = sync.last_error || (sync.last_success_at ? "Última: " + formatDate(sync.last_success_at) : "");
    } catch (error) {
      syncBox.className = "sync degraded";
      syncBox.textContent = "No se pudo actualizar";
      syncBox.title = error.message;
    }
  }

  document.querySelectorAll("[data-filter]").forEach(function (button) {
    button.addEventListener("click", function () {
      selectedFilter = button.dataset.filter;
      document.querySelectorAll("[data-filter]").forEach(function (item) {
        item.classList.toggle("selected", item === button);
      });
      refresh();
    });
  });

  refresh();
  window.setInterval(refresh, 20000);
})();
