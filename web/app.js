/**
 * app.js — ClauseCatcher UI logic. Plain ES module, no framework, no build
 * step, no CDN. Talks to the FastAPI backend (same origin) over REST for
 * setup/report and over WebSocket for the live call.
 *
 * Layout of this file: DOM refs -> small render helpers -> REST calls ->
 * mic capture pipeline -> playback pipeline -> WS message handling ->
 * event wiring. Run with ?selftest=1 to execute dsp.js unit tests instead
 * of wiring up the UI (see runSelfTest at the bottom).
 */
import {
  int16ToFloat32,
  int16ArrayToBase64,
  base64ToInt16Array,
  nextScheduleTime,
} from "./dsp.js";

// ---------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------
const $ = (id) => document.getElementById(id);

const els = {
  pdfInput: $("pdf-input"),
  demoBtn: $("demo-contract-btn"),
  contractStatus: $("contract-status"),
  clauseList: $("clause-list"),
  consentCheckbox: $("consent-checkbox"),
  startCallBtn: $("start-call-btn"),
  setupSection: $("setup-section"),
  callSection: $("call-section"),
  reportSection: $("report-section"),
  endCallBtn: $("end-call-btn"),
  sttPill: $("stt-pill"),
  voicePill: $("voice-pill"),
  speakingIndicator: $("speaking-indicator"),
  simulateInput: $("simulate-input"),
  simulateBtn: $("simulate-btn"),
  askSelect: $("ask-select"),
  askBtn: $("ask-btn"),
  transcriptLog: $("transcript-log"),
  alertList: $("alert-list"),
  clauseCard: $("clause-card"),
  toastRegion: $("toast-region"),
  reportBody: $("report-body"),
  newSessionBtn: $("new-session-btn"),
};

// ---------------------------------------------------------------------
// State
// ---------------------------------------------------------------------
let contractClauses = [];
let sessionId = null;
let ws = null;
let agentSpeaking = false;
let callActive = false;
let endReportTimer = null;

let micStream = null;
let micContext = null;
let workletNode = null;

let playbackCtx = null;
let playbackNextStart = 0;

// ---------------------------------------------------------------------
// Small render helpers
// ---------------------------------------------------------------------
function showToast(message, isError = true) {
  const toast = document.createElement("div");
  toast.className = isError ? "toast toast--error" : "toast";
  toast.textContent = message;
  els.toastRegion.appendChild(toast);
  setTimeout(() => toast.remove(), 6000);
}

function renderClauseList(clauses) {
  els.clauseList.innerHTML = "";
  for (const clause of clauses) {
    const li = document.createElement("li");
    li.className = "clause-list__item";
    const num = document.createElement("span");
    num.className = "clause-list__number";
    num.textContent = clause.section_number;
    const title = document.createElement("span");
    title.className = "clause-list__title";
    title.textContent = clause.title;
    li.append(num, title);
    els.clauseList.appendChild(li);
  }
  els.contractStatus.textContent = `${clauses.length} clause${clauses.length === 1 ? "" : "s"} loaded.`;
}

function populateAskSelect(clauses) {
  els.askSelect.innerHTML = "";
  for (const clause of clauses) {
    const opt = document.createElement("option");
    opt.value = clause.section_number;
    opt.textContent = `${clause.section_number} — ${clause.title}`;
    els.askSelect.appendChild(opt);
  }
}

function updateStartButtonState() {
  els.startCallBtn.disabled = !(contractClauses.length > 0 && els.consentCheckbox.checked);
}

function setPill(el, text, state) {
  el.textContent = text;
  el.dataset.state = state; // "idle" | "ready" | "speaking" | "error"
}

function appendTranscriptLine(text, final) {
  const lines = els.transcriptLog.querySelectorAll(".transcript-line--partial");
  const last = lines[lines.length - 1];
  if (!final && last) {
    last.textContent = text;
    return;
  }
  const line = document.createElement("p");
  line.className = final ? "transcript-line" : "transcript-line transcript-line--partial";
  line.textContent = text;
  els.transcriptLog.appendChild(line);
  els.transcriptLog.scrollTop = els.transcriptLog.scrollHeight;
}

function prependAlertCard({ section_number, title, literal_text, sentence, t }) {
  const card = document.createElement("li");
  card.className = "alert-card";
  const heading = document.createElement("div");
  heading.className = "alert-card__heading";
  heading.textContent = `Contradicts ${section_number}${title ? " — " + title : ""}`;
  const quote = document.createElement("blockquote");
  quote.className = "alert-card__clause";
  quote.textContent = literal_text;
  const said = document.createElement("p");
  said.className = "alert-card__sentence";
  said.textContent = `Rep said: "${sentence}"`;
  const time = document.createElement("time");
  time.className = "alert-card__time";
  const when = t ? new Date(t) : new Date();
  time.textContent = when.toLocaleTimeString();
  card.append(heading, quote, said, time);
  els.alertList.prepend(card);
}

function renderClauseCard({ section_number, title, literal_text }) {
  els.clauseCard.hidden = false;
  els.clauseCard.innerHTML = "";
  const heading = document.createElement("div");
  heading.className = "clause-card__heading";
  heading.textContent = `${section_number} — ${title}`;
  const quote = document.createElement("blockquote");
  quote.className = "clause-card__text";
  quote.textContent = literal_text;
  els.clauseCard.append(heading, quote);
}

function fieldRow(label, value) {
  const row = document.createElement("div");
  row.className = "report-field";
  const dt = document.createElement("span");
  dt.className = "report-field__label";
  dt.textContent = label;
  const dd = document.createElement("span");
  dd.className = "report-field__value";
  dd.textContent = value;
  row.append(dt, dd);
  return row;
}

function renderReport(report) {
  els.reportBody.innerHTML = "";

  els.reportBody.append(
    fieldRow("Transcript turns", String(report.transcript_count ?? "—")),
    fieldRow("Started", report.started_at ? new Date(report.started_at).toLocaleString() : "—"),
    fieldRow("Ended", report.ended_at ? new Date(report.ended_at).toLocaleString() : "—"),
  );

  // Optional fields the server may add later (e.g. estimated cost, a
  // spoken-verbatim check) are rendered generically if present, so this
  // page doesn't need to change when the server report grows.
  const knownKeys = new Set([
    "contract_clauses_referenced",
    "contradictions",
    "transcript_count",
    "started_at",
    "ended_at",
  ]);
  for (const [key, value] of Object.entries(report)) {
    if (knownKeys.has(key) || value === null || typeof value === "object") continue;
    els.reportBody.appendChild(fieldRow(key.replace(/_/g, " "), String(value)));
  }

  const contradictions = report.contradictions || [];
  const heading = document.createElement("h3");
  heading.textContent = `Contradictions (${contradictions.length})`;
  els.reportBody.appendChild(heading);

  if (contradictions.length === 0) {
    const p = document.createElement("p");
    p.textContent = "No contradictions detected during this call.";
    els.reportBody.appendChild(p);
  } else {
    const list = document.createElement("ul");
    list.className = "report-contradictions";
    for (const c of contradictions) {
      const li = document.createElement("li");
      li.className = "alert-card";
      const heading2 = document.createElement("div");
      heading2.className = "alert-card__heading";
      heading2.textContent = `Section ${c.section_number}`;
      const quote = document.createElement("blockquote");
      quote.className = "alert-card__clause";
      quote.textContent = c.literal_text;
      const said = document.createElement("p");
      said.className = "alert-card__sentence";
      said.textContent = `Rep said: "${c.sentence}"`;
      const time = document.createElement("time");
      time.className = "alert-card__time";
      time.textContent = c.t ? new Date(c.t).toLocaleTimeString() : "";
      li.append(heading2, quote, said, time);
      list.appendChild(li);
    }
    els.reportBody.appendChild(list);
  }
}

// ---------------------------------------------------------------------
// REST calls
// ---------------------------------------------------------------------
async function fetchJson(url, options) {
  const resp = await fetch(url, options);
  let body = null;
  try {
    body = await resp.json();
  } catch {
    /* empty body is fine for some endpoints */
  }
  if (!resp.ok) {
    const detail = (body && body.detail) || resp.statusText;
    throw new Error(detail);
  }
  return body;
}

async function loadDemoContract() {
  try {
    const body = await fetchJson("/api/contract/demo", { method: "POST" });
    onContractLoaded(body.clauses);
  } catch (err) {
    showToast(`Could not load demo contract: ${err.message}`);
  }
}

async function uploadContract(file) {
  const form = new FormData();
  form.append("file", file);
  try {
    const body = await fetchJson("/api/contract", { method: "POST", body: form });
    onContractLoaded(body.clauses);
  } catch (err) {
    showToast(`Could not read contract PDF: ${err.message}`);
  }
}

function onContractLoaded(clauses) {
  contractClauses = clauses;
  renderClauseList(clauses);
  populateAskSelect(clauses);
  updateStartButtonState();
}

async function sendConsent(accepted) {
  try {
    await fetchJson("/api/consent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ accepted }),
    });
  } catch (err) {
    showToast(`Could not record consent: ${err.message}`);
  }
}

async function startSession() {
  try {
    const body = await fetchJson("/api/session/start", { method: "POST" });
    return body.session_id;
  } catch (err) {
    showToast(`Could not start session: ${err.message}`);
    return null;
  }
}

async function fetchReportFallback() {
  try {
    const report = await fetchJson(`/api/session/${sessionId}/end`, { method: "POST" });
    onSessionEnded(report);
  } catch (err) {
    showToast(`Could not fetch call report: ${err.message}`);
  }
}

// ---------------------------------------------------------------------
// Mic capture pipeline
// ---------------------------------------------------------------------
async function startMicCapture() {
  micStream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
  });
  micContext = new (window.AudioContext || window.webkitAudioContext)();
  await micContext.audioWorklet.addModule("audio-worklet.js");
  const source = micContext.createMediaStreamSource(micStream);
  workletNode = new AudioWorkletNode(micContext, "mic-downsampler");
  workletNode.port.onmessage = (event) => {
    if (!callActive || agentSpeaking) return; // don't transcribe our own agent's voice
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(event.data); // ArrayBuffer of Int16 PCM16 @ 16kHz
    }
  };
  // Don't connect the worklet to destination — we only want to read mic
  // data, not play it back (that would echo the caller to themselves).
  source.connect(workletNode);
}

function stopMicCapture() {
  if (workletNode) {
    workletNode.port.onmessage = null;
    workletNode.disconnect();
    workletNode = null;
  }
  if (micContext) {
    micContext.close().catch(() => {});
    micContext = null;
  }
  if (micStream) {
    micStream.getTracks().forEach((t) => t.stop());
    micStream = null;
  }
}

// ---------------------------------------------------------------------
// Playback pipeline (agent voice, 24kHz PCM16 over WS as base64)
// ---------------------------------------------------------------------
function playAgentAudioChunk(base64, sampleRate) {
  if (!playbackCtx) {
    playbackCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate });
    playbackNextStart = playbackCtx.currentTime;
  }
  const int16 = base64ToInt16Array(base64);
  const float32 = int16ToFloat32(int16);
  const buffer = playbackCtx.createBuffer(1, float32.length, sampleRate);
  buffer.copyToChannel(float32, 0);
  const source = playbackCtx.createBufferSource();
  source.buffer = buffer;
  source.connect(playbackCtx.destination);
  const startAt = nextScheduleTime(playbackNextStart, playbackCtx.currentTime);
  source.start(startAt);
  playbackNextStart = startAt + buffer.duration;
}

function stopPlayback() {
  if (playbackCtx) {
    playbackCtx.close().catch(() => {});
    playbackCtx = null;
    playbackNextStart = 0;
  }
}

// ---------------------------------------------------------------------
// WebSocket
// ---------------------------------------------------------------------
function connectWs(id) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/ws/session/${id}`);

  ws.onopen = () => {
    setPill(els.sttPill, "STT: connecting", "idle");
    startMicCapture().catch((err) => {
      showToast(`Microphone unavailable: ${err.message}. Use "Simulate rep line" instead.`);
    });
  };

  ws.onmessage = (event) => {
    if (typeof event.data !== "string") return; // server only sends JSON text frames
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }
    handleServerMessage(msg);
  };

  ws.onerror = () => showToast("Connection to ClauseCatcher server had an error.");

  ws.onclose = () => {
    setPill(els.sttPill, "STT: offline", "error");
    setPill(els.voicePill, "Voice: offline", "error");
  };
}

function handleServerMessage(msg) {
  switch (msg.type) {
    case "status":
      if (msg.stt) setPill(els.sttPill, `STT: ${msg.stt}`, msg.stt === "ready" ? "ready" : "idle");
      if (msg.voice) setPill(els.voicePill, `Voice: ${msg.voice}`, msg.voice === "ready" ? "ready" : "idle");
      break;
    case "transcript":
      appendTranscriptLine(msg.text, !!msg.final);
      break;
    case "alert":
      prependAlertCard(msg);
      break;
    case "clause":
      renderClauseCard(msg);
      break;
    case "agent_speaking":
      agentSpeaking = msg.state === "start";
      els.speakingIndicator.hidden = !agentSpeaking;
      setPill(els.voicePill, agentSpeaking ? "Voice: speaking" : "Voice: ready", agentSpeaking ? "speaking" : "ready");
      break;
    case "agent_audio":
      playAgentAudioChunk(msg.pcm16_b64, msg.sample_rate || 24000);
      break;
    case "error":
      showToast(msg.message || "Server error");
      break;
    case "session_ended":
      onSessionEnded(msg.report);
      break;
    default:
      break;
  }
}

// ---------------------------------------------------------------------
// Call lifecycle
// ---------------------------------------------------------------------
async function handleStartCall() {
  els.startCallBtn.disabled = true;
  const id = await startSession();
  if (!id) {
    els.startCallBtn.disabled = false;
    return;
  }
  sessionId = id;
  callActive = true;
  els.setupSection.hidden = true;
  els.callSection.hidden = false;
  els.reportSection.hidden = true;
  els.transcriptLog.innerHTML = "";
  els.alertList.innerHTML = "";
  els.clauseCard.hidden = true;
  connectWs(id);
}

function handleEndCall() {
  if (!callActive) return;
  callActive = false;
  agentSpeaking = false;
  els.endCallBtn.disabled = true;

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "stop" }));
    // Fallback in case the server doesn't send session_ended: fetch the
    // report over REST ourselves after a short grace period.
    endReportTimer = setTimeout(fetchReportFallback, 1500);
  } else {
    fetchReportFallback();
  }
}

function onSessionEnded(report) {
  clearTimeout(endReportTimer);
  stopMicCapture();
  stopPlayback();
  if (ws) {
    ws.onclose = null; // already handled here; avoid double UI updates
    ws.close();
    ws = null;
  }
  els.callSection.hidden = true;
  els.reportSection.hidden = false;
  els.endCallBtn.disabled = false;
  renderReport(report || {});
}

function resetForNewSession() {
  sessionId = null;
  els.reportSection.hidden = true;
  els.setupSection.hidden = false;
  els.clauseList.innerHTML = "";
  contractClauses = [];
  els.contractStatus.textContent = "No contract loaded yet.";
  els.consentCheckbox.checked = false;
  updateStartButtonState();
}

// ---------------------------------------------------------------------
// Event wiring
// ---------------------------------------------------------------------
function init() {
  els.demoBtn.addEventListener("click", loadDemoContract);
  els.pdfInput.addEventListener("change", () => {
    const file = els.pdfInput.files[0];
    if (file) uploadContract(file);
  });
  els.consentCheckbox.addEventListener("change", () => {
    sendConsent(els.consentCheckbox.checked);
    updateStartButtonState();
  });
  els.startCallBtn.addEventListener("click", handleStartCall);
  els.endCallBtn.addEventListener("click", handleEndCall);
  els.newSessionBtn.addEventListener("click", resetForNewSession);

  els.simulateBtn.addEventListener("click", () => {
    const text = els.simulateInput.value.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "transcript", text }));
    appendTranscriptLine(text, true);
    els.simulateInput.value = "";
  });
  els.simulateInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") els.simulateBtn.click();
  });

  els.askBtn.addEventListener("click", () => {
    const section = els.askSelect.value;
    if (!section || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "ask", section_number: section }));
  });

  updateStartButtonState();
}

// ---------------------------------------------------------------------
// Self-test entry point (?selftest=1) — see dev-check.html for the same
// tests with visible output; this just lets `app.js` be checked directly.
// ---------------------------------------------------------------------
async function runSelfTest() {
  const { runAll } = await import("./dsp.selftest.js");
  const results = runAll();
  document.body.innerHTML = `<pre>${results.map((r) => `${r.pass ? "PASS" : "FAIL"} ${r.name}${r.detail ? " — " + r.detail : ""}`).join("\n")}</pre>`;
}

if (new URLSearchParams(location.search).get("selftest") === "1") {
  runSelfTest();
} else if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
