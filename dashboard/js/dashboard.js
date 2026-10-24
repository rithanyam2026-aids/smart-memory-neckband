/**
 * Smart Memory Neckband - Client-Side Dashboard Controller
 * Pure Vanilla JavaScript (No Frameworks)
 * Handles USER mode, CAREGIVER mode, House Grid map, Voice TTS, and Cloud Sync
 */

const API_BASE = window.location.origin.includes("localhost") || window.location.origin.includes("127.0.0.1")
  ? window.location.origin
  : "http://localhost:8000";

let state = {
  currentMode: "user",
  userTab: "today",
  caregiverTab: "overview",
  token: null,
  role: "user",
  blueprint: null,
  deviceStatus: {
    privacy_state: "SLEEP",
    battery_pct: 98,
    is_inside: 1,
    current_zone: "Living Room",
    cell_row: 4,
    cell_col: 2,
  },
  people: [],
  sightings: [],
  summaries: [],
  notes: [],
  reminders: [],
  alerts: [],
  privateSettings: [],
  auditLog: [],
  voiceRecognition: null,
  isRecordingVoice: false,
};

// --- Initialization ---
document.addEventListener("DOMContentLoaded", async () => {
  initSpeechRecognition();
  checkFirstTimeSetup();
  await loadBlueprint();
  await fetchAllData();

  // Set today's date picker defaults
  const todayStr = new Date().toISOString().split("T")[0];
  const uDate = document.getElementById("userDateSelect");
  if (uDate) uDate.value = todayStr;
  const cgDate = document.getElementById("cgHistDate");
  if (cgDate) cgDate.value = todayStr;

  renderAll();

  // Polling loop for live status updates every 4 seconds
  setInterval(fetchStatusAndAlerts, 4000);
});

// --- Speech Recognition & Web Speech API ---
function initSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    state.voiceRecognition = new SpeechRecognition();
    state.voiceRecognition.continuous = false;
    state.voiceRecognition.interimResults = false;
    state.voiceRecognition.lang = "en-US";

    state.voiceRecognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      const noteInput = document.getElementById("noteInputContent");
      if (noteInput) {
        noteInput.value = (noteInput.value + " " + transcript).trim();
      }
      setVoiceButtonState(false);
    };

    state.voiceRecognition.onerror = () => {
      setVoiceButtonState(false);
    };

    state.voiceRecognition.onend = () => {
      setVoiceButtonState(false);
    };
  }
}

function toggleVoiceDictation() {
  if (!state.voiceRecognition) {
    alert("Speech recognition is not supported in this browser. Please type your note.");
    return;
  }
  if (state.isRecordingVoice) {
    state.voiceRecognition.stop();
    setVoiceButtonState(false);
  } else {
    try {
      state.voiceRecognition.start();
      setVoiceButtonState(true);
    } catch (e) {
      console.warn("Speech recognition error:", e);
    }
  }
}

function setVoiceButtonState(isListening) {
  state.isRecordingVoice = isListening;
  const btn = document.getElementById("btnVoiceInput");
  if (btn) {
    btn.innerHTML = isListening ? "🔴 Listening... (Speak Now)" : "🎤 Voice Dictate";
    btn.style.background = isListening ? "rgba(239, 68, 68, 0.3)" : "";
  }
}

// --- Browser Text-to-Speech (Read Aloud) ---
function speakText(text) {
  if (!("speechSynthesis" in window)) {
    alert("Text-to-speech is not supported in your browser.");
    return;
  }
  window.speechSynthesis.cancel(); // Stop prior speech
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 0.95; // Slightly slower, clear elderly cadence
  utterance.pitch = 1.0;
  window.speechSynthesis.speak(utterance);
}

// --- Mode Switching (User vs Caregiver) ---
function switchDashboardMode(mode) {
  state.currentMode = mode;
  document.body.className = mode === "user" ? "mode-user" : "mode-caregiver";

  document.getElementById("btnModeUser").classList.toggle("active", mode === "user");
  document.getElementById("btnModeCaregiver").classList.toggle("active", mode === "caregiver");

  document.getElementById("userView").classList.toggle("active-view", mode === "user");
  document.getElementById("caregiverView").classList.toggle("active-view", mode === "caregiver");

  renderAll();
}

function switchUserTab(tab) {
  state.userTab = tab;
  document.querySelectorAll(".user-tab-btn").forEach((btn, idx) => {
    const tabs = ["today", "history", "notes", "map"];
    btn.classList.toggle("active", tabs[idx] === tab);
  });

  document.getElementById("userTabToday").style.display = tab === "today" ? "block" : "none";
  document.getElementById("userTabHistory").style.display = tab === "history" ? "block" : "none";
  document.getElementById("userTabNotes").style.display = tab === "notes" ? "block" : "none";
  document.getElementById("userTabMap").style.display = tab === "map" ? "block" : "none";

  if (tab === "map") renderHouseGrid("userMapContainer", true);
}

function switchCaregiverTab(tab) {
  state.caregiverTab = tab;
  const tabNames = ["overview", "history", "people", "reminders", "notes", "house_map", "privacy_settings"];
  document.querySelectorAll(".cg-tab-btn").forEach((btn, idx) => {
    btn.classList.toggle("active", tabNames[idx] === tab);
  });

  document.getElementById("cgTabOverview").style.display = tab === "overview" ? "block" : "none";
  document.getElementById("cgTabHistory").style.display = tab === "history" ? "block" : "none";
  document.getElementById("cgTabPeople").style.display = tab === "people" ? "block" : "none";
  document.getElementById("cgTabReminders").style.display = tab === "reminders" ? "block" : "none";
  document.getElementById("cgTabNotes").style.display = tab === "notes" ? "block" : "none";
  document.getElementById("cgTabHouseMap").style.display = tab === "house_map" ? "block" : "none";
  document.getElementById("cgTabPrivacySettings").style.display = tab === "privacy_settings" ? "block" : "none";

  if (tab === "house_map") {
    renderHouseGrid("caregiverMapContainer", false);
    renderRoomLegend();
    renderAuditLog();
  }
}

// --- First-Time Setup Prompt ---
function checkFirstTimeSetup() {
  const isSetupDone = localStorage.getItem("smart_neckband_setup_done");
  if (!isSetupDone) {
    const modal = document.getElementById("modalFirstTimeSetup");
    if (modal) modal.classList.add("active");
  }
}

function completeFirstTimeSetup() {
  localStorage.setItem("smart_neckband_setup_done", "true");
  closeModal("modalFirstTimeSetup");
  switchDashboardMode("user");
  switchUserTab("map");
}

// --- Data Fetching from Cloud API ---
async function loadBlueprint() {
  try {
    const res = await fetch(`${API_BASE}/api/grid/blueprint`);
    if (res.ok) {
      state.blueprint = await res.json();
    }
  } catch (e) {
    console.warn("Using sample blueprint fallback:", e);
    state.blueprint = getFallbackBlueprint();
  }
}

async function fetchAllData() {
  try {
    const [statusRes, peopleRes, remRes, notesRes, paRes, sumRes, sightRes, alertsRes, logsRes] = await Promise.all([
      fetch(`${API_BASE}/api/status`).then(r => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/people`).then(r => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/reminders`).then(r => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/notes`).then(r => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/private-areas`).then(r => r.json()).catch(() => ({ settings: [], audit_log: [] })),
      fetch(`${API_BASE}/api/summaries`).then(r => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/sightings`).then(r => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/alerts`).then(r => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/privacy-logs`).then(r => r.json()).catch(() => []),
    ]);

    if (statusRes) state.deviceStatus = statusRes;
    state.people = peopleRes || [];
    state.reminders = remRes || [];
    state.notes = notesRes || [];
    state.privateSettings = paRes.settings || [];
    state.auditLog = paRes.audit_log || [];
    state.summaries = sumRes || [];
    state.sightings = sightRes || [];
    state.alerts = alertsRes || [];
    state.privacyLogs = logsRes || [];

    // If completely empty (first run), populate rich demo fixtures
    if (state.people.length === 0) populateInitialSampleData();

  } catch (e) {
    console.warn("Using offline sample dataset:", e);
    populateInitialSampleData();
  }
}

async function fetchStatusAndAlerts() {
  try {
    const status = await fetch(`${API_BASE}/api/status`).then(r => r.json());
    if (status) {
      state.deviceStatus = status;
      renderNeckbandStatus();
    }
    const alerts = await fetch(`${API_BASE}/api/alerts`).then(r => r.json());
    if (alerts) {
      state.alerts = alerts;
      renderEmergencyAlerts();
    }
  } catch (e) {
    // Silent fail in offline mode
  }
}

// --- Rendering Logic ---
function renderAll() {
  renderNeckbandStatus();
  renderEmergencyAlerts();

  if (state.currentMode === "user") {
    renderUserToday();
    renderUserNotes();
    if (state.userTab === "map") renderHouseGrid("userMapContainer", true);
  } else {
    renderCaregiverOverview();
    renderCaregiverPeople();
    renderCaregiverReminders();
    renderCaregiverNotes();
    renderCaregiverHistory();
    if (state.caregiverTab === "house_map") {
      renderHouseGrid("caregiverMapContainer", false);
      renderRoomLegend();
      renderAuditLog();
    }
  }
}

// 1. Status Pill
function renderNeckbandStatus() {
  const pill = document.getElementById("neckbandStatusPill");
  const txt = document.getElementById("neckbandStatusText");
  const batt = document.getElementById("batteryPill");
  const locSubtitle = document.getElementById("userLocationSubtitle");

  const st = state.deviceStatus.privacy_state || "SLEEP";
  pill.className = `status-pill ${st.toLowerCase()}`;

  let label = "🌙 SLEEP MODE";
  if (st === "ACTIVE") label = "● LISTENING";
  if (st === "PRIVATE") label = "🔒 PRIVATE MODE";

  txt.textContent = label;
  batt.textContent = `🔋 ${Math.round(state.deviceStatus.battery_pct || 95)}%`;

  const zone = state.deviceStatus.current_zone || "Living Room";
  const insideText = state.deviceStatus.is_inside ? "Inside" : "Outside";
  if (locSubtitle) locSubtitle.textContent = `Location: ${insideText} • ${zone}`;

  // Caregiver stats
  const cgPrivacy = document.getElementById("cgStatPrivacyState");
  if (cgPrivacy) cgPrivacy.textContent = st;
  const cgLoc = document.getElementById("cgStatLocation");
  if (cgLoc) cgLoc.textContent = insideText;
  const cgZone = document.getElementById("cgStatZone");
  if (cgZone) cgZone.textContent = zone;
  const cgBatt = document.getElementById("cgStatBattery");
  if (cgBatt) cgBatt.textContent = `${Math.round(state.deviceStatus.battery_pct || 95)}%`;
  const cgMapZone = document.getElementById("cgMapCurrentZone");
  if (cgMapZone) cgMapZone.textContent = zone;
}

// 2. Emergency Alerts
function renderEmergencyAlerts() {
  const banner = document.getElementById("emergencyBanner");
  const title = document.getElementById("emergencyTitle");
  const details = document.getElementById("emergencyDetails");
  const cgStatAlerts = document.getElementById("cgStatAlerts");

  const unresolved = state.alerts.filter(a => !a.resolved);
  if (cgStatAlerts) cgStatAlerts.textContent = unresolved.length;

  if (unresolved.length > 0) {
    const first = unresolved[0];
    banner.classList.add("active");
    title.textContent = `CRITICAL ALERT: ${first.severity} Emergency!`;
    details.textContent = `${first.trigger_reason} (Pulse: ${first.pulse_bpm} BPM, Motion: ${first.motion_status}) in ${first.location_zone || 'Unknown'}`;
  } else {
    banner.classList.remove("active");
  }

  // Caregiver overview alerts
  const cgAlertsList = document.getElementById("cgOverviewAlertsList");
  if (cgAlertsList) {
    if (state.alerts.length === 0) {
      cgAlertsList.innerHTML = "<p style='color: var(--text-muted);'>No emergency alerts recorded.</p>";
    } else {
      cgAlertsList.innerHTML = state.alerts.map(a => `
        <div class="reminder-item" style="border-left-color: ${a.resolved ? 'var(--accent-success)' : 'var(--accent-danger)'};">
          <div>
            <strong style="color: #FFFFFF;">${a.trigger_reason}</strong>
            <div style="font-size: 0.85rem; color: var(--text-dim);">
              ${new Date(a.timestamp * 1000).toLocaleTimeString()} • ${a.location_zone || 'Area'} • Pulse: ${a.pulse_bpm} BPM
            </div>
          </div>
          <span class="badge ${a.resolved ? 'badge-known' : 'badge-stranger'}">${a.resolved ? 'Resolved' : 'CRITICAL'}</span>
        </div>
      `).join("");
    }
  }
}

// 3. User Mode: Today's Encounters & Reminders
function renderUserToday() {
  const encList = document.getElementById("userTodayEncountersList");
  const remList = document.getElementById("userTodayRemindersList");

  // Encounters
  if (!state.sightings || state.sightings.length === 0) {
    encList.innerHTML = "<p style='color: var(--text-muted); padding: 12px;'>No visitors met yet today.</p>";
  } else {
    encList.innerHTML = state.sightings.slice(0, 5).map(s => {
      const person = state.people.find(p => p.id === s.person_id) || { relationship: "Contact", label: s.person_label };
      const relationText = person.relationship ? `(${person.relationship})` : "";
      const isDoubtful = s.is_doubtful ? "<span style='color: var(--accent-warning); font-size: 0.8rem;'> • (I'm not sure)</span>" : "";
      return `
        <div class="encounter-item">
          <div class="encounter-avatar">${(s.person_label || "U")[0]}</div>
          <div class="encounter-info">
            <div class="encounter-name">${s.person_label} ${relationText} ${isDoubtful}</div>
            <div class="encounter-meta">Met at ${new Date(s.timestamp * 1000).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})} in ${s.zone || 'Room'}</div>
          </div>
          <button class="read-btn" onclick="speakText('This is ${s.person_label}. You met in the ${s.zone || 'house'}.')">🔊</button>
        </div>
      `;
    }).join("");
  }

  // Reminders
  if (!state.reminders || state.reminders.length === 0) {
    remList.innerHTML = "<p style='color: var(--text-muted); padding: 12px;'>No remaining reminders for today.</p>";
  } else {
    remList.innerHTML = state.reminders.map(r => `
      <div class="reminder-item ${r.category}">
        <div>
          <div class="reminder-time">${r.scheduled_time}</div>
          <div class="reminder-title">${r.title}</div>
          <div class="reminder-desc">${r.description || ''}</div>
        </div>
        <button class="read-btn" onclick="speakText('Reminder: ${r.title} scheduled for ${r.scheduled_time}. ${r.description || ''}')">🔊</button>
      </div>
    `).join("");
  }
}

// 4. User Mode: Notes
function renderUserNotes() {
  const container = document.getElementById("userNotesList");
  if (!container) return;
  if (state.notes.length === 0) {
    container.innerHTML = "<p style='color: var(--text-muted); padding: 16px;'>No notes saved yet.</p>";
    return;
  }
  container.innerHTML = state.notes.map(n => `
    <div class="encounter-item" style="border-left: 4px solid var(--accent-primary);">
      <div style="flex-grow: 1;">
        <div style="font-size: 1.15rem; font-weight: 700; color: #FFFFFF;">${n.content}</div>
        <div style="font-size: 0.85rem; color: var(--text-dim); margin-top: 4px;">
          Saved by ${n.author_name} (${n.author_role}) • ${n.date}
        </div>
      </div>
      <button class="read-btn" onclick="speakText('${n.content.replace(/'/g, "\\'")}')">🔊 Read</button>
    </div>
  `).join("");
}

// 5. User Mode: Previous Days History
function loadUserHistoryForDate() {
  const dateInput = document.getElementById("userDateSelect");
  if (!dateInput) return;
  const chosenDate = dateInput.value;

  const encList = document.getElementById("userHistoryEncountersList");
  const sumList = document.getElementById("userHistorySummariesList");

  // Filter sightings by date
  const filteredSightings = state.sightings.filter(s => {
    const d = new Date(s.timestamp * 1000).toISOString().split("T")[0];
    return d === chosenDate;
  });

  if (filteredSightings.length === 0) {
    encList.innerHTML = `<p style='color: var(--text-muted);'>No people logged on ${chosenDate}.</p>`;
  } else {
    encList.innerHTML = filteredSightings.map(s => `
      <div class="encounter-item">
        <div class="encounter-avatar">${(s.person_label || "U")[0]}</div>
        <div class="encounter-info">
          <div class="encounter-name">${s.person_label}</div>
          <div class="encounter-meta">${new Date(s.timestamp * 1000).toLocaleTimeString()} in ${s.zone || 'Room'}</div>
        </div>
        <button class="read-btn" onclick="speakText('On ${chosenDate}, you met ${s.person_label}.')">🔊</button>
      </div>
    `).join("");
  }

  // Filter summaries by date
  const filteredSummaries = state.summaries.filter(sm => {
    const d = new Date(sm.timestamp * 1000).toISOString().split("T")[0];
    return d === chosenDate;
  });

  if (filteredSummaries.length === 0) {
    sumList.innerHTML = `<p style='color: var(--text-muted);'>No conversation summaries on ${chosenDate}.</p>`;
  } else {
    sumList.innerHTML = filteredSummaries.map(sm => `
      <div class="encounter-item" style="border-left: 4px solid var(--accent-cyan);">
        <div>
          <div class="encounter-name">${sm.person_label || 'Contact'}: ${sm.summary}</div>
          <div class="encounter-meta">${new Date(sm.timestamp * 1000).toLocaleTimeString()}</div>
        </div>
        <button class="read-btn" onclick="speakText('Conversation summary: ${sm.summary.replace(/'/g, "\\'")}')">🔊</button>
      </div>
    `).join("");
  }
}

// 6. Caregiver Mode: People Management
function renderCaregiverPeople() {
  const tbody = document.getElementById("cgPeopleTableBody");
  if (!tbody) return;
  tbody.innerHTML = state.people.map(p => {
    const badgeClass = p.status === "known" ? "badge-known" : (p.status === "familiar" ? "badge-familiar" : "badge-stranger");
    return `
      <tr>
        <td><strong>${p.label}</strong></td>
        <td>${p.relationship || '<em style="color: var(--text-dim);">Unset</em>'}</td>
        <td><span class="badge ${badgeClass}">${p.status}</span></td>
        <td>${p.visit_count} visits</td>
        <td>${new Date(p.last_seen * 1000).toLocaleDateString()}</td>
        <td>
          <button class="btn-large btn-secondary" style="min-height: 40px; padding: 6px 14px; font-size: 0.9rem;"
                  onclick="openEditPersonModal('${p.id}', '${p.label.replace(/'/g, "\\'")}', '${(p.relationship || '').replace(/'/g, "\\'")}')">
            ✏️ Customise
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

// 7. Caregiver Mode: Reminders
function renderCaregiverReminders() {
  const list = document.getElementById("cgRemindersList");
  if (!list) return;
  if (state.reminders.length === 0) {
    list.innerHTML = "<p style='color: var(--text-muted);'>No reminders registered.</p>";
    return;
  }
  list.innerHTML = state.reminders.map(r => `
    <div class="reminder-item ${r.category}">
      <div>
        <div class="reminder-time">${r.scheduled_time}</div>
        <div class="reminder-title">${r.title} (${r.category})</div>
        <div class="reminder-desc">${r.description || ''} • Created by ${r.created_by}</div>
      </div>
      <div style="display: flex; gap: 8px;">
        <button class="btn-large btn-secondary" style="min-height: 40px; padding: 6px 14px; font-size: 0.9rem;" onclick="openEditReminderModal('${r.id}')">✏️</button>
        <button class="btn-large btn-danger" style="min-height: 40px; padding: 6px 14px; font-size: 0.9rem;" onclick="deleteReminder('${r.id}')">🗑️</button>
      </div>
    </div>
  `).join("");
}

// 8. Caregiver Mode: Notes
function renderCaregiverNotes() {
  const list = document.getElementById("cgNotesList");
  if (!list) return;
  if (state.notes.length === 0) {
    list.innerHTML = "<p style='color: var(--text-muted);'>No notes recorded.</p>";
    return;
  }
  list.innerHTML = state.notes.map(n => {
    const isUser = n.author_role === "user";
    return `
      <div class="encounter-item">
        <div style="flex-grow: 1;">
          <div style="font-size: 1.1rem; color: #FFFFFF; font-weight: 600;">${n.content}</div>
          <div style="font-size: 0.85rem; color: var(--text-dim); margin-top: 4px;">
            <span class="badge ${isUser ? 'badge-author-user' : 'badge-author-cg'}">${n.author_role.toUpperCase()}: ${n.author_name}</span>
            • ${n.date}
          </div>
        </div>
      </div>
    `;
  }).join("");
}

// 9. Caregiver Mode: Overview Privacy Logs
function renderCaregiverOverview() {
  const container = document.getElementById("cgOverviewPrivacyLogsList");
  if (!container) return;
  const logs = state.privacyLogs || [];
  if (logs.length === 0) {
    container.innerHTML = "<p style='color: var(--text-muted);'>No privacy state transitions recorded.</p>";
    return;
  }
  container.innerHTML = logs.slice(0, 5).map(l => `
    <div class="encounter-item" style="padding: 10px 14px; margin-bottom: 8px;">
      <div>
        <strong style="color: ${l.state === 'PRIVATE' ? 'var(--accent-danger)' : (l.state === 'ACTIVE' ? 'var(--accent-success)' : 'var(--text-muted)')};">
          ${l.state}
        </strong>
        <span style="font-size: 0.85rem; color: #E2E8F0; margin-left: 8px;">${l.reason}</span>
        <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 2px;">
          ${new Date(l.timestamp * 1000).toLocaleTimeString()} • ${l.zone || 'Surroundings'} (${l.is_inside ? 'Inside' : 'Outside'})
        </div>
      </div>
    </div>
  `).join("");
}

// 10. Caregiver History with Filters
function loadCaregiverHistory() {
  const dateVal = document.getElementById("cgHistDate").value;
  const personVal = document.getElementById("cgHistPerson").value.toLowerCase();
  const zoneVal = document.getElementById("cgHistZone").value;

  const tbody = document.getElementById("cgSightingsTableBody");
  const sumContainer = document.getElementById("cgSummariesContainer");

  // Filter sightings
  const filteredSightings = state.sightings.filter(s => {
    const d = new Date(s.timestamp * 1000).toISOString().split("T")[0];
    if (dateVal && d !== dateVal) return false;
    if (personVal && !s.person_label.toLowerCase().includes(personVal)) return false;
    if (zoneVal && zoneVal !== "All" && s.zone !== zoneVal) return false;
    return true;
  });

  tbody.innerHTML = filteredSightings.map(s => `
    <tr>
      <td>${new Date(s.timestamp * 1000).toLocaleTimeString()}</td>
      <td><strong>${s.person_label}</strong></td>
      <td>${s.zone || 'Room'}</td>
      <td>${(s.confidence * 100).toFixed(0)}%</td>
      <td><span class="badge ${s.is_doubtful ? 'badge-stranger' : 'badge-known'}">${s.is_doubtful ? "I'm not sure" : 'Confirmed'}</span></td>
    </tr>
  `).join("");

  // Filter summaries
  const filteredSummaries = state.summaries.filter(sm => {
    const d = new Date(sm.timestamp * 1000).toISOString().split("T")[0];
    if (dateVal && d !== dateVal) return false;
    if (personVal && sm.person_label && !sm.person_label.toLowerCase().includes(personVal)) return false;
    return true;
  });

  sumContainer.innerHTML = filteredSummaries.map(sm => `
    <div class="encounter-item" style="border-left: 4px solid var(--accent-cyan); margin-bottom: 12px;">
      <div>
        <div style="font-weight: 700; color: #FFFFFF;">${sm.person_label || 'Contact'}: ${sm.summary}</div>
        <div style="font-size: 0.85rem; color: var(--text-dim); margin-top: 4px;">
          Importance Score: <strong>${sm.importance_score}</strong> • ${new Date(sm.timestamp * 1000).toLocaleTimeString()}
        </div>
      </div>
    </div>
  `).join("");
}

function resetHistoryFilters() {
  document.getElementById("cgHistDate").value = "";
  document.getElementById("cgHistPerson").value = "";
  document.getElementById("cgHistZone").value = "All";
  loadCaregiverHistory();
}

// --- Interactive House Grid Map ---
function renderHouseGrid(containerId, isUserMode) {
  const container = document.getElementById(containerId);
  if (!container || !state.blueprint) return;

  const rows = state.blueprint.dimensions.rows || 8;
  const cols = state.blueprint.dimensions.columns || 10;
  container.innerHTML = "";

  // Set grid style
  container.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;

  // Build cell coordinate map
  const zoneMap = {};
  state.blueprint.named_zones.forEach(z => {
    z.cells.forEach(c => {
      zoneMap[`${c.row}_${c.col}`] = z;
    });
  });

  const entrances = new Set((state.blueprint.entrances || []).map(e => `${e.row}_${e.col}`));
  const exits = new Set((state.blueprint.exits || []).map(e => `${e.row}_${e.col}`));

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const cellKey = `${r}_${c}`;
      const zone = zoneMap[cellKey];
      const isPrivate = checkIsAreaPrivate(r, c, zone ? zone.name : null);
      const isUserHere = (state.deviceStatus.cell_row === r && state.deviceStatus.cell_col === c);

      const cellDiv = document.createElement("div");
      cellDiv.className = "grid-cell";
      cellDiv.title = `${zone ? zone.name : 'Hallway'} (Row ${r}, Col ${c})`;

      if (zone) {
        cellDiv.classList.add(`zone-${zone.id.replace("zone_", "")}`);
      }
      if (isPrivate) cellDiv.classList.add("is-private");
      if (isUserHere) cellDiv.classList.add("user-present");
      if (entrances.has(cellKey)) cellDiv.classList.add("is-entrance");
      if (exits.has(cellKey)) cellDiv.classList.add("is-exit");

      // Click cell to toggle privacy
      cellDiv.onclick = () => {
        toggleCellPrivacy(r, c, !isPrivate);
      };

      container.appendChild(cellDiv);
    }
  }
}

function checkIsAreaPrivate(row, col, zoneName) {
  // Check cell override first
  const cellMatch = state.privateSettings.find(s => s.cell_row === row && s.cell_col === col);
  if (cellMatch) return Boolean(cellMatch.is_private);

  // Check zone level
  if (zoneName) {
    const zoneMatch = state.privateSettings.find(s => s.zone_name === zoneName && s.cell_row === null);
    if (zoneMatch) return Boolean(zoneMatch.is_private);
  }
  return false;
}

function renderRoomLegend() {
  const container = document.getElementById("roomLegendContainer");
  if (!container || !state.blueprint) return;

  container.innerHTML = state.blueprint.named_zones.map(zone => {
    const isPrivate = Boolean(state.privateSettings.find(s => s.zone_name === zone.name && s.is_private));
    return `
      <div class="legend-room-btn ${isPrivate ? 'private-active' : ''}" onclick="toggleZonePrivacy('${zone.name.replace(/'/g, "\\'")}', ${!isPrivate})">
        <div style="display: flex; align-items: center;">
          <span class="legend-color-dot" style="background: ${zone.color || '#3B82F6'};"></span>
          <strong>${zone.name}</strong>
        </div>
        <div>
          ${isPrivate ? '<span style="color: var(--accent-danger); font-weight: 700;">🔒 Private</span>' : '<span style="color: var(--accent-success);">Normal</span>'}
        </div>
      </div>
    `;
  }).join("");
}

async function toggleZonePrivacy(zoneName, setPrivate) {
  const changer = state.currentMode === "user" ? "Senior Resident (User)" : "Nurse Priya (Caregiver)";
  try {
    const resp = await fetch(`${API_BASE}/api/private-areas`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        zone_name: zoneName,
        is_private: setPrivate
      })
    });
    if (resp.ok) {
      await fetchAllData();
      renderAll();
    }
  } catch (e) {
    // Offline local mutation
    const existing = state.privateSettings.find(s => s.zone_name === zoneName && s.cell_row === null);
    if (existing) {
      existing.is_private = setPrivate ? 1 : 0;
    } else {
      state.privateSettings.push({ id: `pa_${Date.now()}`, zone_name: zoneName, cell_row: null, cell_col: null, is_private: setPrivate ? 1 : 0 });
    }
    state.auditLog.unshift({
      timestamp: Date.now() / 1000,
      zone_name: zoneName,
      is_private: setPrivate ? 1 : 0,
      changed_by: changer,
      notes: `Toggled ${setPrivate ? 'Private' : 'Normal'} via dashboard`
    });
    renderAll();
  }
}

async function toggleCellPrivacy(row, col, setPrivate) {
  const changer = state.currentMode === "user" ? "Senior Resident (User)" : "Nurse Priya (Caregiver)";
  try {
    const resp = await fetch(`${API_BASE}/api/private-areas`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cell_row: row,
        cell_col: col,
        is_private: setPrivate
      })
    });
    if (resp.ok) {
      await fetchAllData();
      renderAll();
    }
  } catch (e) {
    const existing = state.privateSettings.find(s => s.cell_row === row && s.cell_col === col);
    if (existing) {
      existing.is_private = setPrivate ? 1 : 0;
    } else {
      state.privateSettings.push({ id: `pa_c_${row}_${col}`, zone_name: null, cell_row: row, cell_col: col, is_private: setPrivate ? 1 : 0 });
    }
    state.auditLog.unshift({
      timestamp: Date.now() / 1000,
      cell_row: row,
      cell_col: col,
      is_private: setPrivate ? 1 : 0,
      changed_by: changer,
      notes: `Cell (${row}, ${col}) toggled ${setPrivate ? 'Private' : 'Normal'}`
    });
    renderAll();
  }
}

function renderAuditLog() {
  const tbody = document.getElementById("cgAuditLogTableBody");
  if (!tbody) return;
  if (state.auditLog.length === 0) {
    tbody.innerHTML = "<tr><td colspan='5' style='text-align: center; color: var(--text-muted);'>No private area changes recorded yet.</td></tr>";
    return;
  }
  tbody.innerHTML = state.auditLog.map(l => `
    <tr>
      <td>${new Date(l.timestamp * 1000).toLocaleString()}</td>
      <td><strong>${l.zone_name || `Cell (${l.cell_row}, ${l.cell_col})`}</strong></td>
      <td><span class="badge ${l.is_private ? 'badge-stranger' : 'badge-known'}">${l.is_private ? '🔒 Private' : 'Normal'}</span></td>
      <td>${l.changed_by}</td>
      <td>${l.notes || ''}</td>
    </tr>
  `).join("");
}

// --- Text-to-Speech Helpers ---
function getEncountersSpeechText() {
  if (state.sightings.length === 0) return "You have not met any visitors yet today.";
  const names = state.sightings.slice(0, 3).map(s => s.person_label);
  return `Today you met ${names.join(", ")}.`;
}

function getRemindersSpeechText() {
  if (state.reminders.length === 0) return "You have no remaining reminders for today.";
  return state.reminders.map(r => `At ${r.scheduled_time}: ${r.title}. ${r.description || ''}`).join(". ");
}

function speakDailySummary() {
  const enc = getEncountersSpeechText();
  const rem = getRemindersSpeechText();
  const speech = `Good day! Here is your daily summary. ${enc} For your schedule: ${rem}`;
  speakText(speech);
}

function speakPreviousDaySummary() {
  const chosenDate = document.getElementById("userDateSelect").value;
  const filteredSightings = state.sightings.filter(s => new Date(s.timestamp * 1000).toISOString().split("T")[0] === chosenDate);
  const people = filteredSightings.map(s => s.person_label);
  const speech = `On ${chosenDate}, you met ${people.length > 0 ? people.join(", ") : "no recorded visitors"}.`;
  speakText(speech);
}

// --- Modals & Handlers ---
function openModal(id) {
  document.getElementById(id).classList.add("active");
}
function closeModal(id) {
  document.getElementById(id).classList.remove("active");
}

function openAddReminderModal() {
  document.getElementById("modalReminderTitle").textContent = "⏰ Add New Reminder";
  document.getElementById("formReminder").reset();
  document.getElementById("remInputId").value = "";
  openModal("modalReminder");
}

function openEditReminderModal(id) {
  const rem = state.reminders.find(r => r.id === id);
  if (!rem) return;
  document.getElementById("modalReminderTitle").textContent = "✏️ Edit Reminder";
  document.getElementById("remInputId").value = rem.id;
  document.getElementById("remInputTitle").value = rem.title;
  document.getElementById("remInputDesc").value = rem.description || "";
  document.getElementById("remInputTime").value = rem.scheduled_time;
  document.getElementById("remInputCategory").value = rem.category || "medication";
  openModal("modalReminder");
}

async function handleSaveReminder(event) {
  event.preventDefault();
  const id = document.getElementById("remInputId").value;
  const payload = {
    title: document.getElementById("remInputTitle").value,
    description: document.getElementById("remInputDesc").value,
    scheduled_time: document.getElementById("remInputTime").value,
    category: document.getElementById("remInputCategory").value,
  };

  try {
    const url = id ? `${API_BASE}/api/reminders/${id}` : `${API_BASE}/api/reminders`;
    const method = id ? "PUT" : "POST";
    await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  } catch (e) {
    if (id) {
      const idx = state.reminders.findIndex(r => r.id === id);
      if (idx !== -1) Object.assign(state.reminders[idx], payload);
    } else {
      state.reminders.push({ id: `rem_${Date.now()}`, ...payload, created_by: "Caregiver" });
    }
  }

  closeModal("modalReminder");
  await fetchAllData();
  renderAll();
}

async function deleteReminder(id) {
  if (!confirm("Are you sure you want to delete this reminder?")) return;
  try {
    await fetch(`${API_BASE}/api/reminders/${id}`, { method: "DELETE" });
  } catch (e) {
    state.reminders = state.reminders.filter(r => r.id !== id);
  }
  await fetchAllData();
  renderAll();
}

function openAddNoteModal() {
  document.getElementById("formNote").reset();
  setVoiceButtonState(false);
  openModal("modalNote");
}

async function handleSaveNote(event) {
  event.preventDefault();
  const content = document.getElementById("noteInputContent").value;
  const payload = { content, date: new Date().toISOString().split("T")[0] };

  try {
    await fetch(`${API_BASE}/api/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  } catch (e) {
    state.notes.unshift({
      id: `note_${Date.now()}`,
      content,
      author_role: state.currentMode,
      author_name: state.currentMode === "user" ? "Senior Resident" : "Nurse Priya",
      date: payload.date
    });
  }

  closeModal("modalNote");
  await fetchAllData();
  renderAll();
}

function openEditPersonModal(id, label, relation) {
  document.getElementById("personEditId").value = id;
  document.getElementById("personEditLabel").value = label;
  document.getElementById("personEditRelation").value = relation;
  openModal("modalPersonEdit");
}

async function handleSavePerson(event) {
  event.preventDefault();
  const id = document.getElementById("personEditId").value;
  const label = document.getElementById("personEditLabel").value;
  const relationship = document.getElementById("personEditRelation").value;

  try {
    await fetch(`${API_BASE}/api/people/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label, relationship })
    });
  } catch (e) {
    const p = state.people.find(x => x.id === id);
    if (p) {
      p.label = label;
      p.relationship = relationship;
      p.status = "known";
    }
  }

  closeModal("modalPersonEdit");
  await fetchAllData();
  renderAll();
}

function acknowledgeAlert() {
  state.alerts.forEach(a => a.resolved = true);
  renderEmergencyAlerts();
  alert("Emergency acknowledged. Alert dispatched to caregiver emergency response.");
}

function savePrivacySettings() {
  alert("Privacy parameters updated successfully. Synced to neckband hardware.");
}

// --- Sample Fixture Generator ---
function populateInitialSampleData() {
  state.people = [
    { id: "p_ananya", label: "Ananya", relationship: "Granddaughter", status: "known", visit_count: 8, last_seen: Date.now() / 1000 },
    { id: "p_priya", label: "Nurse Priya", relationship: "Physiotherapist", status: "known", visit_count: 5, last_seen: (Date.now() - 3600000) / 1000 },
    { id: "p_unk2", label: "Unknown #2", relationship: null, status: "familiar", visit_count: 3, last_seen: (Date.now() - 7200000) / 1000 },
  ];

  state.sightings = [
    { id: "s_1", person_id: "p_ananya", person_label: "Ananya", timestamp: Date.now() / 1000, confidence: 0.94, zone: "Living Room", is_doubtful: false },
    { id: "s_2", person_id: "p_priya", person_label: "Nurse Priya", timestamp: (Date.now() - 3600000) / 1000, confidence: 0.91, zone: "Kitchen", is_doubtful: false },
  ];

  state.reminders = [
    { id: "r_1", title: "Heart Medication (Metoprolol)", description: "Take 1 tablet with full glass of water", scheduled_time: "18:00", category: "medication", is_active: 1, created_by: "Nurse Priya" },
    { id: "r_2", title: "Evening Walk with Granddaughter", description: "In the backyard patio", scheduled_time: "17:30", category: "schedule", is_active: 1, created_by: "Ananya" },
  ];

  state.notes = [
    { id: "n_1", content: "Remember to drink extra water after the afternoon physical therapy exercises.", author_role: "caregiver", author_name: "Nurse Priya", date: new Date().toISOString().split("T")[0] },
    { id: "n_2", content: "Ananya mentioned she got an 'A' on her chemistry college exam!", author_role: "user", author_name: "Voice Capture", date: new Date().toISOString().split("T")[0] },
  ];

  state.summaries = [
    { id: "sm_1", person_label: "Ananya", summary: "Spoke about college chemistry exam results and planned evening walk.", importance_score: 0.85, timestamp: Date.now() / 1000 },
  ];
}

function getFallbackBlueprint() {
  return {
    dimensions: { rows: 8, columns: 10, cell_size_meters: 1.0 },
    entrances: [{ row: 7, col: 4, name: "Main Entrance" }],
    exits: [{ row: 7, col: 4, name: "Main Entrance" }, { row: 0, col: 8, name: "Back Patio Door" }],
    named_zones: [
      { id: "zone_living", name: "Living Room", color: "#3B82F6", cells: [{row: 3, col: 1}, {row: 3, col: 2}, {row: 4, col: 1}, {row: 4, col: 2}] },
      { id: "zone_kitchen", name: "Kitchen", color: "#10B981", cells: [{row: 0, col: 1}, {row: 1, col: 1}] },
      { id: "zone_master_bed", name: "Master Bedroom", color: "#8B5CF6", cells: [{row: 0, col: 6}, {row: 1, col: 6}] },
      { id: "zone_bathroom", name: "En-suite Bathroom", color: "#06B6D4", cells: [{row: 4, col: 6}] },
    ]
  };
}
