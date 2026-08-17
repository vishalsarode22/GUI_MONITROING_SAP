let activeSystemId = "TST";
let configuredSystems = [];
let savedSendersList = [];

window.addEventListener("pywebviewready", async function () {
  await loadSystemsList();
  await loadEmailSettings();
  if (configuredSystems.length > 0) {
    switchSystem(configuredSystems[0].id || configuredSystems[0].name);
  }
});

async function loadSystemsList() {
  if (!window.pywebview || !window.pywebview.api) return;
  configuredSystems = await window.pywebview.api.get_configured_systems();
  renderTabs();
}

async function loadEmailSettings() {
  if (!window.pywebview || !window.pywebview.api) return;
  const settings = await window.pywebview.api.get_email_settings();
  if (settings) {
    savedSendersList = settings.saved_senders || [];
    renderSenderDropdown(settings.active_sender || "");
    document.getElementById("emailRecipients").value = Array.isArray(settings.recipients) ? settings.recipients.join(", ") : (settings.recipients || "");
    document.getElementById("emailCcRecipients").value = Array.isArray(settings.cc_recipients) ? settings.cc_recipients.join(", ") : (settings.cc_recipients || "");
  }
}

function renderSenderDropdown(selectedSender) {
  const select = document.getElementById("senderSelect");
  select.innerHTML = "";

  savedSendersList.forEach(email => {
    const opt = document.createElement("option");
    opt.value = email;
    opt.innerText = email + " (Vault Password Saved)";
    if (email === selectedSender) opt.selected = true;
    select.appendChild(opt);
  });

  const newOpt = document.createElement("option");
  newOpt.value = "__NEW__";
  newOpt.innerText = "➕ + Add New Sender Email";
  if (!selectedSender || !savedSendersList.includes(selectedSender)) {
    newOpt.selected = true;
  }
  select.appendChild(newOpt);
  handleSenderChange();
}

function handleSenderChange() {
  const select = document.getElementById("senderSelect");
  const isNew = select.value === "__NEW__";
  document.getElementById("newSenderGroup").style.display = isNew ? "block" : "none";
  document.getElementById("passwordGroup").style.display = isNew ? "block" : "none";
  document.getElementById("newSenderInput").required = isNew;
  document.getElementById("emailPassword").required = isNew;
}

async function handleSaveEmailSettings(e) {
  e.preventDefault();
  if (!window.pywebview || !window.pywebview.api) return;

  const select = document.getElementById("senderSelect");
  const isNew = select.value === "__NEW__";

  let sender = isNew ? document.getElementById("newSenderInput").value.trim() : select.value;
  let password = isNew ? document.getElementById("emailPassword").value.trim() : "";

  const recipients = document.getElementById("emailRecipients").value.split(",").map(s => s.trim()).filter(Boolean);
  const cc = document.getElementById("emailCcRecipients").value.split(",").map(s => s.trim()).filter(Boolean);

  const res = await window.pywebview.api.save_email_settings({
    sender_email: sender,
    sender_password: password,
    recipients: recipients,
    cc_recipients: cc
  });

  const status = document.getElementById("emailSaveStatus");
  if (res.success) {
    status.style.color = "var(--success)";
    status.innerText = res.message;
    await loadEmailSettings();
  } else {
    status.style.color = "var(--danger)";
    status.innerText = res.error;
  }
}

function renderTabs() {
  const container = document.getElementById("systemTabsContainer");
  container.innerHTML = "";
  configuredSystems.forEach(sys => {
    const id = sys.id || sys.name;
    const btn = document.createElement("button");
    btn.className = `tab-btn ${id.toUpperCase() === activeSystemId.toUpperCase() ? 'active' : ''}`;
    btn.innerText = id.toUpperCase();
    btn.onclick = () => switchSystem(id);
    container.appendChild(btn);
  });
}

async function switchSystem(systemId) {
  activeSystemId = systemId.toUpperCase();
  renderTabs();
  if (!window.pywebview || !window.pywebview.api) return;
  const data = await window.pywebview.api.get_system_status(activeSystemId);
  renderSystemData(data);
}

function renderSystemData(data) {
  if (!data) return;

  document.getElementById("updatedAt").innerText = `Updated: ${data.cycle_timestamp || 'N/A'}`;
  document.getElementById("subSystemInfo").innerText = `${data.system} / Client ${data.client || '000'}`;

  const statusElem = document.getElementById("overallStatus");
  statusElem.innerText = data.overall_status || "UNKNOWN";
  statusElem.className = "card-value " + (
    data.overall_status === "HEALTHY" ? "status-healthy" :
    data.overall_status === "WARNING" ? "status-warning" :
    data.overall_status === "CRITICAL" ? "status-critical" : "status-unknown"
  );

  const metrics = data.metrics || [];
  let alerts = 0;
  let locks = "0";
  let dumps = "0";

  const tableBody = document.getElementById("metricsTableBody");
  tableBody.innerHTML = "";

  if (metrics.length === 0) {
    tableBody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No metrics collected yet for ${activeSystemId}. Click 'Run Monitoring Now'</td></tr>`;
  } else {
    metrics.forEach(m => {
      if (m.status === "WARNING" || m.status === "CRITICAL") alerts++;
      if (m.name.includes("SM12")) locks = m.display_value.replace(/[^0-9]/g, '') || "0";
      if (m.name.includes("ST22")) dumps = m.display_value.replace(/[^0-9]/g, '') || "0";

      const row = document.createElement("tr");
      const badgeClass = m.status === "OK" ? "badge-ok" : (m.status === "WARNING" ? "badge-warning" : "badge-critical");
      row.innerHTML = `
        <td><strong>${m.name}</strong></td>
        <td>${m.display_value}</td>
        <td><span class="badge ${badgeClass}">${m.status}</span></td>
        <td style="color: var(--text-muted);">${m.detail || ''}</td>
      `;
      tableBody.appendChild(row);
    });
  }

  document.getElementById("activeLocks").innerText = locks;
  document.getElementById("dumpCount").innerText = dumps;
  document.getElementById("alertsCount").innerText = alerts;
  document.getElementById("alertsCount").className = "card-value " + (alerts > 0 ? "status-warning" : "status-healthy");

  const ai = data.ai_analysis || {};
  document.getElementById("aiSeverity").innerText = `Severity: ${ai.severity || 'NORMAL'}`;
  document.getElementById("aiSeverity").className = (ai.severity === 'CRITICAL' ? 'status-critical' : (ai.severity === 'WARNING' ? 'status-warning' : 'status-healthy'));
  document.getElementById("aiRootCause").innerText = ai.root_cause || "System parameters optimal.";

  const grid = document.getElementById("tcodeGrid");
  grid.innerHTML = "";
  (data.gui_evidence || []).forEach(e => {
    const box = document.createElement("div");
    box.className = "tcode-box";
    box.innerHTML = `<div class="tcode-name">${e.tcode}</div><div class="tcode-val">${e.display_value || 'Evidence captured'}</div>`;
    grid.appendChild(box);
  });
}

async function triggerMonitoring() {
  if (!window.pywebview || !window.pywebview.api) return;
  const btnText = document.getElementById("runBtnText");
  btnText.innerText = `Running ${activeSystemId}...`;

  const res = await window.pywebview.api.run_monitoring_for_system(activeSystemId);
  
  const checkInterval = setInterval(async () => {
    const data = await window.pywebview.api.get_system_status(activeSystemId);
    renderSystemData(data);
  }, 4000);

  setTimeout(() => {
    clearInterval(checkInterval);
    btnText.innerText = "Run Monitoring Now";
  }, 50000);
}

function toggleSchedInputs() {
  const type = document.getElementById("schedType").value;
  document.getElementById("timeGroup").style.display = (type === "daily") ? "block" : "none";
  document.getElementById("intervalGroup").style.display = (type !== "daily") ? "block" : "none";
}

async function saveSchedule() {
  if (!window.pywebview || !window.pywebview.api) return;
  const type = document.getElementById("schedType").value;
  const value = type === "daily" ? document.getElementById("schedTime").value.trim() : document.getElementById("schedInterval").value.trim();

  const res = await window.pywebview.api.set_schedule(type, value);
  const statusEl = document.getElementById("schedStatus");
  statusEl.style.color = res.success ? "var(--success)" : "var(--danger)";
  statusEl.innerText = res.message || res.error;
}

async function disableSchedule() {
  if (!window.pywebview || !window.pywebview.api) return;
  const res = await window.pywebview.api.stop_schedule();
  document.getElementById("schedStatus").innerText = res.message;
}

async function handleAddSystem(e) {
  e.preventDefault();
  const sysId = document.getElementById("sysId").value.trim().toUpperCase();
  const client = document.getElementById("sysClient").value.trim();
  const connection_name = document.getElementById("sysConn").value.trim();
  const username = document.getElementById("sysUser").value.trim();
  const password = document.getElementById("sysPass").value.trim();

  const res = await window.pywebview.api.add_system({
    name: sysId,
    client: client,
    connection_name: connection_name,
    username: username,
    password: password
  });

  if (res.success) {
    document.getElementById("addSystemForm").reset();
    await loadSystemsList();
    switchSystem(sysId);
  } else {
    alert(`Failed to add system: ${res.error}`);
  }
}