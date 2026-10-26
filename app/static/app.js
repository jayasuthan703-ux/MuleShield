/* ============================================================
   MuleShield frontend — Home page, hash router, /api/analyze flow
   No external libraries, no network calls beyond our own API.
   ============================================================ */

"use strict";

const $ = (id) => document.getElementById(id);

/* ---------- Sample messages (invented, for the demo) ---------- */

const SAMPLES = {
  en:
    "Hi! Part-time job for students. Money will come into your bank account " +
    "and you just forward it to another account the same day. 10% commission " +
    "for you. No experience needed, instant payout. It's just for a few days " +
    "so keep it secret and don't tell anyone.",
  ta:
    "உங்க வங்கிக் கணக்கை சில நாட்கள் மட்டும் எனக்கு வாடகைக்கு கொடுங்க. " +
    "பணம் வந்ததும் உடனே அனுப்பிடணும், கமிஷன் தர்றேன். யாருக்கும் சொல்லாதீங்க.",
  ok:
    "Hey, are you coming to the canteen at 1? I will pay for my thali now, " +
    "send me your share whenever you get time.",
};

const MAX_CHARS = 5000;
const REPORT_MAX_CHARS = 7000;

/* ---------- Helpers ---------- */

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Build the message HTML with matched snippets wrapped in <mark>. */
function highlight(text, snippets) {
  const ranges = [];
  const haystack = text.toLowerCase();

  for (const raw of snippets || []) {
    // Snippets from the API may be truncated with "..." — match the prefix.
    const needle = String(raw).toLowerCase().replace(/\.\.\.$/, "").trim();
    if (!needle) continue;
    let from = 0;
    while (from <= haystack.length - needle.length) {
      const i = haystack.indexOf(needle, from);
      if (i === -1) break;
      ranges.push([i, i + needle.length]);
      from = i + 1;
    }
  }

  if (!ranges.length) return escapeHtml(text);

  // Merge overlapping ranges so we never emit nested markup.
  ranges.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const merged = [ranges[0]];
  for (let i = 1; i < ranges.length; i++) {
    const last = merged[merged.length - 1];
    if (ranges[i][0] <= last[1]) last[1] = Math.max(last[1], ranges[i][1]);
    else merged.push(ranges[i]);
  }

  let out = "";
  let pos = 0;
  for (const [start, end] of merged) {
    out += escapeHtml(text.slice(pos, start));
    out += "<mark>" + escapeHtml(text.slice(start, end)) + "</mark>";
    pos = end;
  }
  out += escapeHtml(text.slice(pos));
  return out;
}

/* ---------- Result rendering ---------- */

function renderResult(data, rawText) {
  const level = String(data.level || "Low");
  const levelClass = "level-" + level.toLowerCase();

  // Gauge + badge
  const gauge = $("gauge");
  gauge.className = "gauge " + levelClass;
  gauge.style.setProperty("--score", Number(data.risk_score) || 0);
  $("gaugeScore").textContent = Number(data.risk_score) || 0;
  gauge.setAttribute(
    "aria-label",
    `Risk score ${data.risk_score} out of 100, ${level} risk`
  );

  const badge = $("levelBadge");
  badge.className = "level-badge " + levelClass;
  badge.textContent = level.toUpperCase() + " RISK";

  // Highlighted message
  const snippets = (data.matched_signals || []).map((s) => s.snippet);
  $("highlightedText").innerHTML = highlight(rawText, snippets);

  const note = $("resultNote");
  if (data.note && String(data.note).startsWith("truncated")) {
    note.textContent = "Only the first 5,000 characters were analysed.";
    note.hidden = false;
  } else {
    note.hidden = true;
  }

  // Why flagged cards
  const wrap = $("signalsList");
  const signals = data.matched_signals || [];
  if (!signals.length) {
    wrap.innerHTML =
      '<article class="signal-card signal-ok">' +
      '<div class="signal-head"><span class="signal-index">&#10003;</span>' +
      "<h4>No red flags matched</h4></div>" +
      '<p class="signal-expl">None of the money-mule patterns were found in this ' +
      "message. Stay alert anyway: scammers keep rewriting their scripts.</p>" +
      "</article>";
  } else {
    wrap.innerHTML = signals
      .map(
        (s, i) => `
      <article class="signal-card">
        <div class="signal-head">
          <span class="signal-index">${i + 1}</span>
          <h4>${escapeHtml(s.name)}</h4>
          <span class="signal-weight">+${escapeHtml(s.weight)}</span>
        </div>
        <p class="signal-snippet">“${escapeHtml(s.snippet)}”</p>
        <p class="signal-expl">${escapeHtml(s.explanation)}</p>
      </article>`
      )
      .join("");
  }

  // Legal summary + actions + privacy
  $("legalSummary").textContent = data.legal_risk_summary || "";
  $("actionsList").innerHTML = (data.recommended_actions || [])
    .map((a) => `<li>${escapeHtml(a)}</li>`)
    .join("");
  $("resultPrivacy").textContent =
    data.privacy_note || "We analyse only what you submit. Nothing is stored.";

  const card = $("result");
  card.classList.remove("level-low", "level-medium", "level-high");
  card.classList.add(levelClass);
  card.hidden = false;
  card.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------- Analyse flow ---------- */

function showInputError(message) {
  const el = $("inputError");
  el.textContent = message;
  el.hidden = false;
  setTimeout(() => (el.hidden = true), 4000);
}

async function analyze() {
  const text = $("messageInput").value;
  if (!text.trim()) {
    showInputError("Paste a message first — or pick one of the samples.");
    return;
  }

  const btn = $("analyzeBtn");
  btn.disabled = true;
  btn.classList.add("loading");
  btn.querySelector(".btn-label").textContent = "Analysing";

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    renderResult(data, text);
  } catch (err) {
    showInputError("Could not reach the API — is the server running?");
  } finally {
    btn.disabled = false;
    btn.classList.remove("loading");
    btn.querySelector(".btn-label").textContent = "Analyse message";
  }
}

/* ---------- Simulator: "What happens if you say yes" ---------- */

const SIM_STEPS = [
  {
    short: "Offer",
    status: "Unverified offer",
    tone: "warn",
    title: "A message from a contact",
    narrative:
      "A contact from your circle offers you part-time work: money will arrive " +
      "in your bank account, you forward it on, and you keep a share. They say " +
      "it takes just a few days and ask you not to mention it to anyone.",
    balance: 1250,
    delta: null,
    state: null,
  },
  {
    short: "Money in",
    status: "Funds received",
    tone: "warn",
    title: "Money you didn't earn",
    narrative:
      "₹40,000 lands in your account from someone you have never met. Within " +
      "minutes the recruiter messages you, asking you to send most of it on " +
      "straight away.",
    balance: 41250,
    delta: { text: "+₹40,000 received", dir: "up" },
    state: null,
  },
  {
    short: "Forwarded",
    status: "Funds forwarded",
    tone: "warn",
    title: "You forward it",
    narrative:
      "You transfer ₹39,200 to the UPI ID they send and keep ₹800 as your " +
      "share. The money is out of your account within minutes; the record of " +
      "that transfer stays associated with your name.",
    balance: 2050,
    delta: { text: "−₹39,200 forwarded", dir: "down" },
    state: null,
  },
  {
    short: "Frozen",
    status: "Account frozen",
    tone: "bad",
    title: "The account freezes",
    narrative:
      "A few days later the person who lost the money reports it. Your bank " +
      "pauses your account while it checks the trail — and your own savings in " +
      "that account are paused with it.",
    balance: 2050,
    delta: null,
    state: { text: "Frozen", tone: "frozen" },
  },
  {
    short: "Bank notice",
    status: "Under bank review",
    tone: "bad",
    title: "The bank asks questions",
    narrative:
      "The bank's team asks you to explain the two transfers: where the money " +
      "came from and who asked you to move it. Your UPI, card and net-banking " +
      "access stay paused while the review is open.",
    balance: 2050,
    delta: null,
    state: { text: "Frozen", tone: "frozen" },
  },
  {
    short: "Police",
    status: "Police questioning",
    tone: "bad",
    title: "Police questioning",
    narrative:
      "The original complaint is under investigation, so officers ask you the " +
      "same questions. You share the chat messages and explain that you were " +
      "offered this as student work. Keeping the records and answering plainly " +
      "helps establish what happened.",
    balance: 2050,
    delta: null,
    state: { text: "Frozen", tone: "frozen" },
  },
  {
    short: "Impact",
    status: "After-effects",
    tone: "bad",
    title: "The long tail",
    narrative:
      "Once the checks are completed your account is unlocked, but some " +
      "effects linger: large transfers from your account may face extra checks " +
      "for a while, and opening new accounts or loans can take longer than " +
      "usual. The money you forwarded is often not recovered. The ₹800 you " +
      "kept was small beside the time it takes to sort all this out.",
    balance: 2050,
    delta: null,
    state: { text: "Restricted", tone: "restricted" },
  },
];

const SIM_MAX_BALANCE = 41250;
const sim = { i: 0, branch: false, shown: SIM_STEPS[0].balance, raf: 0, fallback: 0 };

function formatRupee(n) {
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

function animateSimBalance(target) {
  const from = sim.shown;
  cancelAnimationFrame(sim.raf);
  clearTimeout(sim.fallback);
  const start = performance.now();
  const dur = 650;

  const frame = (now) => {
    const t = Math.min(1, (now - start) / dur);
    const eased = 1 - Math.pow(1 - t, 3);
    sim.shown = from + (target - from) * eased;
    $("simBalance").textContent = formatRupee(sim.shown);
    if (t < 1) sim.raf = requestAnimationFrame(frame);
    else {
      sim.shown = target;
      $("simBalance").textContent = formatRupee(target);
    }
  };
  sim.raf = requestAnimationFrame(frame);
  // Fallback in case rAF is throttled (hidden tab / hidden section).
  sim.fallback = setTimeout(() => {
    sim.shown = target;
    $("simBalance").textContent = formatRupee(target);
  }, dur + 120);
}

function renderSimStepper() {
  $("simStepper").innerHTML = SIM_STEPS.map((s, idx) => {
    const cls = idx < sim.i ? "done" : idx === sim.i ? "current" : "";
    const mark = idx < sim.i ? "&#10003;" : idx + 1;
    return (
      `<li class="sim-dot ${cls}" ${idx === sim.i ? 'aria-current="step"' : ""}>` +
      `<span class="sim-dot-mark">${mark}</span>` +
      `<span class="sim-dot-label">${escapeHtml(s.short)}</span></li>`
    );
  }).join("");
}

function replayEnterAnim(el) {
  el.classList.remove("sim-enter");
  void el.offsetWidth; // restart the CSS animation
  el.classList.add("sim-enter");
}

function renderSim() {
  const step = SIM_STEPS[sim.i];
  const last = sim.i === SIM_STEPS.length - 1;

  // Sections: risky path vs safe branch
  $("simStep").hidden = sim.branch;
  $("simStepper").hidden = sim.branch;
  $("simBranch").hidden = !sim.branch;
  replayEnterAnim(sim.branch ? $("simBranch") : $("simStep"));

  // Status indicator
  const statusEl = $("simStatus");
  statusEl.className = "sim-status " + (sim.branch ? "ok" : step.tone);
  $("simStatusText").textContent = sim.branch ? "Account normal" : step.status;

  // Step copy
  $("simKicker").textContent = `Step ${sim.i + 1} of ${SIM_STEPS.length}`;
  $("simTitle").textContent = step.title;
  $("simNarrative").textContent = step.narrative;
  renderSimStepper();

  // Balance, delta chip, state chip, bar
  const state = sim.branch ? null : step.state;
  const delta = sim.branch ? null : step.delta;
  const balance = sim.branch ? SIM_STEPS[0].balance : step.balance;

  animateSimBalance(balance);

  const deltaEl = $("simDelta");
  deltaEl.hidden = !delta;
  if (delta) {
    deltaEl.textContent = delta.text;
    deltaEl.className = "sim-balance-delta " + delta.dir;
  }

  const stateEl = $("simState");
  stateEl.hidden = !state;
  if (state) {
    stateEl.textContent = state.text;
    stateEl.className = "sim-balance-state " + state.tone;
  }

  const valueEl = $("simBalance");
  valueEl.className =
    "sim-balance-value" + (state ? " " + state.tone : "");

  const barEl = $("simBar");
  barEl.className = "sim-balance-fill" + (state ? " " + state.tone : "");
  barEl.style.width = (balance / SIM_MAX_BALANCE) * 100 + "%";

  // Controls
  $("simBack").hidden = sim.branch;
  $("simNext").hidden = sim.branch;
  $("simBack").disabled = sim.i === 0;
  $("simNext").disabled = last;
  $("simRefuse").hidden = sim.branch || sim.i !== 0;
}

function initSimulator() {
  $("simNext").addEventListener("click", () => {
    if (sim.i < SIM_STEPS.length - 1) sim.i += 1;
    renderSim();
  });
  $("simBack").addEventListener("click", () => {
    if (sim.i > 0) sim.i -= 1;
    renderSim();
  });
  $("simReplay").addEventListener("click", () => {
    sim.i = 0;
    sim.branch = false;
    renderSim();
  });
  $("simRefuse").addEventListener("click", () => {
    sim.branch = true;
    renderSim();
  });
  renderSim();
}

/* ---------- Anonymous report + campus alerts (module 3) ---------- */

function updateReportCounter() {
  const len = $("reportText").value.length;
  const el = $("reportCharCount");
  el.textContent = `${len.toLocaleString()} / ${REPORT_MAX_CHARS.toLocaleString()} characters`;
  el.classList.toggle("over", len > REPORT_MAX_CHARS);
}

function showReportError(message) {
  const el = $("reportError");
  el.textContent = message;
  el.hidden = false;
  setTimeout(() => (el.hidden = true), 5000);
}

function renderReportResult(data) {
  $("reportMessage").textContent = data.message || "";

  // Masked indicators (or an explanatory empty state).
  const masks = data.masked_indicators || [];
  const maskWrap = $("reportIndicators");
  if (masks.length) {
    maskWrap.innerHTML = masks
      .map((m) => `<span class="mask-chip">${escapeHtml(m)}</span>`)
      .join("");
    maskWrap.classList.remove("empty");
  } else {
    maskWrap.innerHTML =
      '<p class="mask-empty">No phone number, UPI ID, link or handle was ' +
      "found in the text — the report is stored with just the campus tag.</p>";
    maskWrap.classList.add("empty");
  }

  // Clustering outcome.
  const box = $("reportCluster");
  const cluster = data.matched_cluster;
  if (cluster && cluster.active) {
    box.className = "cluster-box active";
    box.innerHTML =
      `<span class="cluster-badge">ACTIVE CAMPUS ALERT</span>` +
      `<p>Your report joins <strong>${cluster.count - 1}</strong> other report(s) ` +
      `about the same indicator. Campus tags: ` +
      `<strong>${escapeHtml((cluster.campus_tags || []).join(", "))}</strong>. ` +
      `First seen ${escapeHtml(fmtDate(cluster.first_seen))}.</p>`;
  } else if (cluster) {
    box.className = "cluster-box watching";
    box.innerHTML =
      `<span class="cluster-badge">WATCHING — ${cluster.count} report(s)</span>` +
      `<p>These reports match on a masked indicator. <strong>3</strong> matching ` +
      `reports raise an active campus alert for everyone.</p>`;
  } else {
    box.className = "cluster-box new";
    box.innerHTML =
      `<span class="cluster-badge">NEW — NO MATCH YET</span>` +
      `<p>Stored anonymously. If others report the same indicator, it will ` +
      `cluster here and can become an active alert.</p>`;
  }

  $("reportPrivacyNote").textContent = data.privacy || "";

  const card = $("reportResult");
  card.hidden = false;
  card.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function submitReport() {
  const text = $("reportText").value;
  if (!text.trim()) {
    showReportError("Paste the message you received so we can extract its indicators.");
    return;
  }

  const btn = $("reportSubmitBtn");
  btn.disabled = true;
  btn.classList.add("loading");
  btn.querySelector(".btn-label").textContent = "Sending";

  let serverDetail = "";
  try {
    const res = await fetch("/api/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        campus_tag: $("reportCampus").value.trim(),
      }),
    });
    if (!res.ok) {
      try {
        const body = await res.json();
        if (typeof body.detail === "string") serverDetail = body.detail;
      } catch {
        /* non-JSON error body - fall through to the generic message */
      }
      throw new Error("http");
    }
    renderReportResult(await res.json());
  } catch (err) {
    showReportError(
      serverDetail || "Could not send the report — is the server running?"
    );
  } finally {
    btn.disabled = false;
    btn.classList.remove("loading");
    btn.querySelector(".btn-label").textContent = "Send anonymous report";
  }
}

/* ---------- Campus alerts page ---------- */

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return String(iso);
  return d.toLocaleString(undefined, {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

function renderAlerts(data) {
  const stats = $("alertStats");
  const clusters = data.clusters || [];
  stats.innerHTML = `
    <span class="stat-pill stat-active">${data.active_alerts} active</span>
    <span class="stat-pill stat-watching">${data.watching} watching</span>
    <span class="stat-pill">${data.total_reports} reports</span>
    <span class="stat-pill">alert at ${data.min_for_alert}+ matches</span>`;

  const grid = $("alertsGrid");
  $("alertsEmpty").hidden = clusters.length > 0;

  grid.innerHTML = clusters
    .map((c) => {
      const masks = (c.masked_indicators || [])
        .map((m) => `<span class="mask-chip">${escapeHtml(m)}</span>`)
        .join("");
      const tags = (c.campus_tags || [])
        .map((t) => `<span class="tag-chip">${escapeHtml(t)}</span>`)
        .join("");
      const stateClass = c.active ? "active" : "watching";
      const badge = c.active
        ? '<span class="cluster-badge">ACTIVE CAMPUS ALERT</span>'
        : `<span class="cluster-badge watch">WATCHING — NEEDS ${data.min_for_alert}</span>`;
      const links = (c.linked_by || []).map(escapeHtml).join(" · ") || "indicator";
      return `
      <article class="alert-card ${stateClass}">
        <div class="alert-card-top">
          ${badge}
          <span class="alert-count">${c.count} report${c.count === 1 ? "" : "s"}</span>
        </div>
        <div class="mask-list">${masks}</div>
        <div class="alert-meta">
          <div><span>First seen</span><strong>${escapeHtml(fmtDate(c.first_seen))}</strong></div>
          <div><span>Last seen</span><strong>${escapeHtml(fmtDate(c.last_seen))}</strong></div>
          <div><span>Linked by</span><strong>${links}</strong></div>
        </div>
        ${tags ? `<div class="alert-tags">${tags}</div>` : ""}
        <button class="btn btn-ghost summary-btn" type="button" data-cid="${escapeHtml(c.cluster_id)}" aria-expanded="false" aria-controls="summary-${escapeHtml(c.cluster_id)}">
          Generate report summary
        </button>
        <div class="summary-box" id="summary-${escapeHtml(c.cluster_id)}" hidden></div>
      </article>`;
    })
    .join("");

  grid.querySelectorAll(".summary-btn").forEach((btn) => {
    btn.addEventListener("click", () => toggleSummary(btn.dataset.cid, clusters, btn));
  });
}

function buildSummary(c) {
  const lines = [
    "INCIDENT SUMMARY — for cybercrime.gov.in",
    "Generated by MuleShield (anonymous, demo data)",
    "==================================================",
    "Matching reports in this cluster: " + c.count,
    "Status: " + (c.active ? "ACTIVE CAMPUS ALERT" : "Watch (below alert threshold)"),
    "First seen: " + fmtDate(c.first_seen),
    "Last seen:  " + fmtDate(c.last_seen),
    "Linked by:  " + ((c.linked_by || []).join(", ") || "indicator"),
    "Campus tags: " + ((c.campus_tags || []).join(", ") || "unspecified"),
    "",
    "Masked indicators (originals are never stored):",
    ...(c.masked_indicators || []).map((m) => "  - " + m),
    "",
    "--------------------------------------------------",
    "REPORTER DETAILS (leave blank — report is anonymous)",
    "Name:        ______________________________",
    "Contact:     ______________________________",
    "College/ID:  ______________________________",
    "--------------------------------------------------",
    "",
    "NOTE: Indicator values above are masked for privacy. Provide the full",
    "phone number / UPI ID / link to the cybercrime portal only if you are",
    "an authorised investigator. Students should file their own complaint",
    "at https://cybercrime.gov.in or call 1930.",
  ];
  return lines.join("\n");
}

/** Copy text to the clipboard with a selectable-text fallback.
 *  Returns "clipboard" | "selection" | "failed". */
async function copyToClipboard(text, fallbackNode) {
  try {
    await navigator.clipboard.writeText(text);
    return "clipboard";
  } catch {
    if (fallbackNode) {
      const range = document.createRange();
      range.selectNodeContents(fallbackNode);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      return "selection";
    }
    return "failed";
  }
}

function toggleSummary(cid, clusters, button) {
  const box = $("summary-" + cid);
  if (!box) return;
  const opening = box.hidden;
  box.hidden = !opening;
  if (button) button.setAttribute("aria-expanded", String(opening));
  if (!opening) return;
  const cluster = clusters.find((c) => c.cluster_id === cid);
  if (!cluster) return;
  box.innerHTML = "";
  const pre = document.createElement("pre");
  pre.className = "summary-pre";
  pre.textContent = buildSummary(cluster);
  const copyBtn = document.createElement("button");
  copyBtn.className = "btn btn-primary copy-btn";
  copyBtn.type = "button";
  copyBtn.textContent = "Copy summary";
  copyBtn.addEventListener("click", async () => {
    const outcome = await copyToClipboard(buildSummary(cluster), pre);
    copyBtn.textContent =
      outcome === "clipboard"
        ? "✓ Copied"
        : outcome === "selection"
          ? "Selected — press Ctrl+C"
          : "Copy failed — select the text manually";
    if (outcome === "clipboard") {
      setTimeout(() => (copyBtn.textContent = "Copy summary"), 2000);
    }
  });
  box.appendChild(pre);
  box.appendChild(copyBtn);
}

async function loadAlerts() {
  $("alertsGrid").innerHTML =
    '<p class="loading-inline">Loading current campus alerts…</p>';
  $("alertStats").innerHTML =
    '<span class="stat-pill">Loading…</span>';
  try {
    const res = await fetch("/api/alerts");
    if (!res.ok) throw new Error("bad status");
    renderAlerts(await res.json());
  } catch {
    $("alertsGrid").innerHTML = "";
    $("alertStats").innerHTML =
      '<span class="stat-pill stat-active">Could not load alerts — is the server running?</span>';
  }
}

function initReport() {
  $("reportText").addEventListener("input", updateReportCounter);
  $("reportSubmitBtn").addEventListener("click", submitReport);
  $("reportAgainBtn").addEventListener("click", () => {
    $("reportResult").hidden = true;
    $("reportText").value = "";
    $("reportCampus").value = "";
    updateReportCounter();
    $("reportText").focus();
  });
  $("reportClearBtn").addEventListener("click", () => {
    $("reportText").value = "";
    $("reportCampus").value = "";
    $("reportResult").hidden = true;
    updateReportCounter();
    $("reportText").focus();
  });
  $("alertsRefreshBtn").addEventListener("click", loadAlerts);
  updateReportCounter();
}

/* ---------- Bank anomaly dashboard (module 4) ---------- */

let bankData = null;
let flowChart = null;

const fmtMoney = (v) =>
  "₹" + Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const fmtPct1 = (v) => (Number(v || 0) * 100).toFixed(1) + "%";
const fmtPct0 = (v) => Math.round(Number(v || 0) * 100) + "%";
const fmtMins = (v) =>
  Number(v) > 0 ? Number(v).toFixed(0) + " min" : "—";

function levelBadge(level) {
  const map = { high: ["level-high", "HIGH"], watch: ["level-medium", "WATCH"], normal: ["level-low", "NORMAL"] };
  const [cls, text] = map[level] || map.normal;
  return `<span class="level-badge ${cls}">${text}</span>`;
}

function renderBankTable(data) {
  bankData = data;
  $("bankStats").innerHTML = `
    <span class="stat-pill">${data.total_accounts} accounts</span>
    <span class="stat-pill stat-active">${data.flagged_accounts} flagged</span>
    <span class="stat-pill stat-watching">${data.watch_accounts} watch</span>
    <span class="stat-pill">flag ≥ ${data.flag_threshold}</span>
    <span class="stat-pill">${escapeHtml(data.model)}</span>`;

  if (!data.accounts || !data.accounts.length) {
    $("bankTableBody").innerHTML =
      '<tr><td colspan="9" class="loading-inline">No scored accounts yet — ' +
      "run <code>python data/generate_transactions.py</code> and restart the server.</td></tr>";
    return;
  }

  const rows = data.accounts
    .map(
      (a) => `
      <tr class="bank-row" data-account="${escapeHtml(a.account_id)}" tabindex="0">
        <td class="col-rank">${a.rank}</td>
        <td class="col-acct">${escapeHtml(a.account_id)}</td>
        <td class="col-score"><span class="score-num ${a.level}">${a.score}</span></td>
        <td>${levelBadge(a.level)}</td>
        <td>${a.credit_count}</td>
        <td>${a.unique_senders}</td>
        <td>${fmtPct0(a.pass_through_ratio)}</td>
        <td>${fmtMins(a.avg_forward_minutes)}</td>
        <td>${fmtPct1(a.retained_ratio)}</td>
      </tr>`
    )
    .join("");
  $("bankTableBody").innerHTML = rows;

  $("bankTableBody").querySelectorAll(".bank-row").forEach((row) => {
    const pick = () => selectBankAccount(row.dataset.account);
    row.addEventListener("click", pick);
    row.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); }
    });
  });

  if (data.accounts.length) selectBankAccount(data.accounts[0].account_id);
}

function renderScoreBars(detail) {
  const bar = (label, value, cls, right) => `
    <div class="score-bar-row">
      <span class="score-bar-label">${label}</span>
      <span class="score-bar-track"><span class="score-bar-fill ${cls}" style="width:${Math.min(100, value)}%"></span></span>
      <span class="score-bar-val">${right}</span>
    </div>`;
  $("scoreBars").innerHTML =
    `<div class="final-score"><span>Final score</span><strong class="${detail.level}">${detail.score}</strong></div>` +
    bar("Isolation Forest", detail.model_score, "fill-model", detail.model_score.toFixed(1)) +
    bar("Rule points", detail.rule_score, "fill-rule", detail.rule_score + " / 100");
}

function renderRuleHits(detail) {
  const hits = detail.rule_hits || [];
  $("ruleHits").innerHTML = hits.length
    ? hits
        .map(
          (h) => `
      <article class="signal-card">
        <div class="signal-head">
          <span class="signal-index">!</span>
          <h4>${escapeHtml(h.rule.replace(/_/g, " "))}</h4>
          <span class="signal-weight">+${h.points}</span>
        </div>
        <p class="signal-expl">${escapeHtml(h.detail)}</p>
      </article>`
        )
        .join("")
    : '<p class="signal-ok-note">No mule rules fired for this account.</p>';
}

function renderFeatureList(detail) {
  const f = detail;
  const items = [
    ["Credits / day", f.credits_per_day],
    ["Unique senders", f.unique_senders],
    ["Pass-through ratio", fmtPct1(f.pass_through_ratio)],
    ["Avg time to forward", fmtMins(f.avg_forward_minutes)],
    ["Retained balance", fmtPct1(f.retained_ratio) + " (" + fmtMoney(f.end_balance) + ")"],
    ["New-device share", fmtPct0(f.new_device_ratio)],
    ["New-location share", fmtPct0(f.new_location_ratio)],
    ["Busiest-day credits", f.max_daily_credits],
    ["Total credits", f.credit_count + " (" + fmtMoney(f.total_credit_amount) + ")"],
    ["Transactions", f.txn_count],
  ];
  $("featureList").innerHTML = items
    .map(([k, v]) => `<div><dt>${k}</dt><dd>${escapeHtml(String(v))}</dd></div>`)
    .join("");
}

function renderFlowChart(detail) {
  const flow = detail.flow || {};
  const ctx = $("flowChart");
  if (flowChart) { flowChart.destroy(); flowChart = null; }
  if (typeof Chart === "undefined") {
    $("flowNote").textContent = "Chart library failed to load.";
    return;
  }
  flowChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: flow.labels || [],
      datasets: [
        {
          label: "Credits in",
          data: flow.credits || [],
          backgroundColor: "rgba(45, 212, 191, 0.75)",
          borderColor: "#2dd4bf",
          borderWidth: 1,
        },
        {
          label: "Debits out",
          data: flow.debits || [],
          backgroundColor: "rgba(248, 113, 113, 0.75)",
          borderColor: "#f87171",
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      // Paint immediately: the animated ticker stalls when the window is
      // not in the foreground, and instant bars are better for demos.
      animation: false,
      plugins: {
        legend: { labels: { color: "#93a4c3" } },
        tooltip: {
          callbacks: { label: (c) => `${c.dataset.label}: ${fmtMoney(c.parsed.y)}` },
        },
      },
      scales: {
        x: { ticks: { color: "#93a4c3", maxRotation: 60, autoSkip: true }, grid: { color: "rgba(30,45,77,0.5)" } },
        y: {
          ticks: { color: "#93a4c3", callback: (v) => fmtMoney(v) },
          grid: { color: "rgba(30,45,77,0.5)" },
        },
      },
    },
  });

  const note = detail.summary || "";
  $("flowNote").textContent =
    `${flow.grain === "hour" ? "Hourly" : "Daily"} buckets. ${note}`;
}

async function selectBankAccount(accountId) {
  $("bankTableBody").querySelectorAll(".bank-row").forEach((r) =>
    r.classList.toggle("selected", r.dataset.account === accountId)
  );
  try {
    const res = await fetch("/api/anomalies/" + encodeURIComponent(accountId));
    if (!res.ok) throw new Error("bad status");
    const detail = await res.json();
    $("detailAccount").textContent = detail.account_id;
    $("detailLevel").innerHTML = levelBadge(detail.level);
    // Unhide first: Chart.js cannot size a canvas inside a hidden container.
    $("bankDetail").hidden = false;
    renderScoreBars(detail);
    renderRuleHits(detail);
    renderFeatureList(detail);
    renderFlowChart(detail);
  } catch {
    $("bankError").textContent = "Could not load account details.";
    $("bankError").hidden = false;
  }
}

async function loadBank() {
  $("bankTableBody").innerHTML =
    '<tr><td colspan="9" class="loading-inline">Scoring 210 synthetic accounts…</td></tr>';
  try {
    const res = await fetch("/api/anomalies");
    if (!res.ok) throw new Error("bad status");
    renderBankTable(await res.json());
    $("bankError").hidden = true;
  } catch {
    $("bankTableBody").innerHTML = "";
    $("bankError").textContent =
      "Could not load anomalies — is the server running?";
    $("bankError").hidden = false;
  }
}

/* ---------- Learn page (module 5) ---------- */

const RED_FLAGS = [
  "“Money will land in your account, you just forward it” — receiving and transferring the funds is the job itself.",
  "A commission or percentage offered for letting someone else use your bank account or UPI.",
  "“Keep this between us” / “don't tell anyone” — secrecy is part of the script.",
  "Time pressure: “only a few days”, “instant payout”, “today only”.",
  "“No experience needed, students preferred, work from home” — qualification that is too easy.",
  "Requests for your OTP, UPI PIN, card CVV or screenshots of your banking app screen.",
  "Being asked to “rent” or “share” your account, card or KYC documents for money.",
  "A small “registration fee” or first deposit demanded before any work or payout.",
  "A new number or handle that refuses a live call or any verification.",
  "Links with misspelled domains, shortened URLs, or “claim your reward” pages.",
  "Money offered for forwarding “prize money”, refunds, or someone else's salary or loan credits.",
];

function renderChecklist() {
  const list = $("checklist");
  list.innerHTML = RED_FLAGS.map(
    (text, i) => `
      <li>
        <input type="checkbox" id="flag${i}">
        <label for="flag${i}">${escapeHtml(text)}</label>
      </li>`
  ).join("");
  list.addEventListener("change", updateChecklistProgress);
  updateChecklistProgress();
}

function updateChecklistProgress() {
  const boxes = Array.from(
    document.querySelectorAll('#checklist input[type="checkbox"]')
  );
  const ticked = boxes.filter((b) => b.checked).length;
  const total = boxes.length;
  const note = $("checklistNote");

  $("checklistProgress").textContent = `${ticked} of ${total} spotted`;

  if (ticked === 0) {
    note.textContent =
      "Nothing ticked yet — open the checklist against a real message and " +
      "see how many signs it carries.";
    note.classList.remove("all-hit");
  } else if (ticked === total) {
    note.textContent =
      "That's every red flag. If one message carries several of these, " +
      "don't reply — analyse it, then report it anonymously.";
    note.classList.add("all-hit");
  } else {
    note.textContent =
      `${ticked} sign${ticked === 1 ? "" : "s"} spotted so far. ` +
      "Two or more together in one message are a strong warning.";
    note.classList.remove("all-hit");
  }
}

function buildShareText(alerts) {
  const clusters = alerts.clusters || [];
  const active = clusters.filter((c) => c.active);
  const lines = ["⚠ CAMPUS ALERT — money-mule recruitment attempts"];

  if (!clusters.length) {
    lines.push(
      "",
      "No alerts are active right now. Share this instead:",
      "A message that offers you money to receive funds in your account and",
      "forward them — even from a known number — is a mule recruitment attempt.",
      "Don't reply, never share OTP/UPI PIN, and don't let anyone else's money",
      "pass through your account."
    );
  } else {
    lines.push(
      "",
      `${active.length} ACTIVE alert${active.length === 1 ? "" : "s"} from ` +
        `${alerts.total_reports} anonymous student report(s)` +
        (active.length < clusters.length
          ? ` · ${clusters.length - active.length} more cluster(s) watching`
          : "") +
        ":"
    );
    for (const c of clusters.slice(0, 4)) {
      const masks = (c.masked_indicators || []).join(", ") || "no shared indicator";
      const tags = (c.campus_tags || []).length
        ? ` [${c.campus_tags.join(", ")}]`
        : "";
      lines.push(
        `• ${c.count} report(s)${c.active ? " — ACTIVE" : " — watching"}: ${masks}${tags}`
      );
    }
    lines.push(
      "",
      "What to do:",
      "• Do not reply, and do not accept money into your account.",
      "• Never share OTP, UPI PIN or card details with anyone.",
      "• Check the message with MuleShield, then report it anonymously.",
      "• Money already received? Stop, keep the chat, tell your bank / call 1930."
    );
  }
  lines.push(
    "",
    "Shared via MuleShield — masked indicators only, no messages stored.",
    "Demo on synthetic data. Illustrative information, not legal advice."
  );
  return lines.join("\n");
}

async function loadShareText() {
  const pre = $("shareText");
  pre.textContent = "Loading current alerts…";
  try {
    const res = await fetch("/api/alerts");
    if (!res.ok) throw new Error("bad status");
    pre.textContent = buildShareText(await res.json());
  } catch {
    pre.textContent = buildShareText({ clusters: [], total_reports: 0 });
  }
}

function initLearn() {
  renderChecklist();

  $("shareCopyBtn").addEventListener("click", async () => {
    const btn = $("shareCopyBtn");
    const label = btn.querySelector(".btn-label");
    btn.disabled = true;
    const outcome = await copyToClipboard($("shareText").textContent, $("shareText"));
    label.textContent =
      outcome === "clipboard"
        ? "✓ Copied"
        : outcome === "selection"
          ? "Selected — press Ctrl+C"
          : "Copy failed — select the text manually";
    btn.disabled = false;
    if (outcome === "clipboard") {
      setTimeout(() => (label.textContent = "Copy alert text"), 2500);
    }
  });

  $("shareRefreshBtn").addEventListener("click", async () => {
    const btn = $("shareRefreshBtn");
    btn.disabled = true;
    btn.textContent = "↻ Refreshing…";
    await loadShareText();
    btn.textContent = "↻ Refresh";
    btn.disabled = false;
  });
}

/* ---------- Hash router ---------- */

const ROUTES = ["/", "/simulator", "/report", "/alerts", "/bank", "/learn"];

function route() {
  const hash = location.hash.replace(/^#/, "") || "/";
  const path = ROUTES.includes(hash) ? hash : "/";
  const pageId = "page-" + (path === "/" ? "home" : path.slice(1));

  document.querySelectorAll(".page").forEach((p) => (p.hidden = true));
  const page = $(pageId);
  if (page) page.hidden = false;

  document.querySelectorAll(".nav-links a").forEach((a) => {
    const isCurrent = a.dataset.route === path;
    a.classList.toggle("active", isCurrent);
    if (isCurrent) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });

  // Load data for pages that fetch on entry.
  if (path === "/alerts") loadAlerts();
  if (path === "/bank") loadBank();
  if (path === "/learn") loadShareText();

  $("navLinks").classList.remove("open");
  $("navToggle").setAttribute("aria-expanded", "false");
  window.scrollTo({ top: 0 });
}

/* ---------- Wiring ---------- */

document.addEventListener("DOMContentLoaded", () => {
  $("analyzeBtn").addEventListener("click", analyze);

  $("clearBtn").addEventListener("click", () => {
    $("messageInput").value = "";
    $("result").hidden = true;
    updateCounter();
    $("messageInput").focus();
  });

  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      $("messageInput").value = SAMPLES[chip.dataset.sample] || "";
      updateCounter();
      $("messageInput").focus();
    });
  });

  $("messageInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) analyze();
  });

  $("messageInput").addEventListener("input", updateCounter);

  $("navToggle").addEventListener("click", () => {
    const links = $("navLinks");
    const open = links.classList.toggle("open");
    $("navToggle").setAttribute("aria-expanded", String(open));
  });

  window.addEventListener("hashchange", route);
  route();
  updateCounter();
  initSimulator();
  initReport();
  initLearn();
});

function updateCounter() {
  const len = $("messageInput").value.length;
  const el = $("charCount");
  el.textContent = `${len.toLocaleString()} / 5,000 characters`;
  el.classList.toggle("over", len > MAX_CHARS);
}
