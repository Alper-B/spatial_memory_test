/**
 * app.js
 * Main application controller for the TMT-A Spatial Memory Experiment Webapp.
 * Controls canvas rendering, event handling, sub-millisecond step timing,
 * mode mechanics, and AJAX communication with the Flask backend.
 */

class TMTSpatialMemoryApp {
  constructor() {
    this.canvas = document.getElementById("experimentCanvas");
    this.ctx = this.canvas.getContext("2d");

    // Experiment State
    this.activeMode = 1;
    this.targetList = [];
    this.startTarget = 1;
    this.endTarget = 6;
    this.targetCount = 6;
    this.layout = {}; // target -> [pctX, pctY]
    this.initialLayout = {};

    this.currentStepIndex = 0; // index in this.targetList
    this.isStarted = false;
    this.isCompleted = false;

    // High Precision Timers
    this.startPerfTime = 0;
    this.lastTargetPerfTime = 0;
    this.stepTimesMs = [];
    this.stepRecords = [];
    this.totalErrors = 0;
    this.currentStepErrors = 0;
    this.hudInterval = null;

    // Node rendering dimensions (auto computed from canvas size)
    this.nodeRadius = 24;

    // Config cache from backend
    this.serverConfig = null;
    this.modeSpecs = null;

    // DOM Elements
    this.overlay = document.getElementById("canvasOverlay");
    this.startBtn = document.getElementById("startTestBtn");
    this.resetBtn = document.getElementById("resetTestBtn");
    this.participantInput = document.getElementById("participantName");
    this.nextTargetEl = document.getElementById("hudNextTarget");
    this.stepTimerEl = document.getElementById("hudStepTimer");
    this.totalTimerEl = document.getElementById("hudTotalTimer");
    this.errorsEl = document.getElementById("hudErrors");
    this.targetRangeValEl = document.getElementById("targetRangeVal");
    this.refreshRangeBtn = document.getElementById("refreshRangeBtn");

    // Modal Elements
    this.resultsModal = document.getElementById("resultsModal");
    this.submitBtn = document.getElementById("submitResultsBtn");
    this.nextRunBtn = document.getElementById("nextRunBtn");
    this.closeModalBtn = document.getElementById("closeModalBtn");

    this._bindEvents();
  }

  async init() {
    this._resizeCanvas();
    window.addEventListener("resize", () => {
      this._resizeCanvas();
      this.draw();
    });

    try {
      // 1. Fetch server config
      const res = await fetch("/api/config");
      const data = await res.json();
      if (data.status === "success") {
        this.serverConfig = data.config;
        this.modeSpecs = data.modes;
        this.activeMode = this.serverConfig.default_mode || 1;
      }

      // Check URL query parameters (e.g. ?mode=2&name=ParticipantA&count=6)
      const urlParams = new URLSearchParams(window.location.search);
      const paramMode = parseInt(urlParams.get("mode"), 10);
      if ([1, 2, 3, 4].includes(paramMode)) {
        this.activeMode = paramMode;
      }

      const paramName = urlParams.get("name") || urlParams.get("participant");
      if (paramName && this.participantInput) {
        this.participantInput.value = paramName;
      }

      this._updateModeUI(this.activeMode);

      // 2. Fetch initial target range (passes URL query parameters if present)
      await this.fetchNewTargetRange();
    } catch (err) {
      console.error("Initialization error:", err);
      // Fallback defaults
      this.targetList = ["10", "11", "12", "13", "14", "15"];
      this.startTarget = 10;
      this.endTarget = 15;
      this.targetCount = 6;
      this._updateTargetRangeIndicators();
      this._setupLayout();
    }
  }

  _bindEvents() {
    // Mode switcher cards
    document.querySelectorAll(".mode-card").forEach((card) => {
      card.addEventListener("click", () => {
        if (this.isStarted && !this.isCompleted) {
          if (!confirm("A test is currently in progress. Switching mode will reset the test. Proceed?")) {
            return;
          }
        }
        const m = parseInt(card.getAttribute("data-mode"), 10);
        this.setMode(m);
      });
    });

    // Start Button
    this.startBtn.addEventListener("click", () => this.startTest());

    // Reset Button
    this.resetBtn.addEventListener("click", () => this.resetTest());

    // Refresh Target Range Button
    if (this.refreshRangeBtn) {
      this.refreshRangeBtn.addEventListener("click", () => {
        if (!this.isStarted || this.isCompleted) {
          this.fetchNewTargetRange();
        }
      });
    }

    // Canvas click
    this.canvas.addEventListener("pointerdown", (e) => this._handleCanvasClick(e));

    // Results Modal actions
    if (this.submitBtn) {
      this.submitBtn.addEventListener("click", () => this.submitResults());
    }
    if (this.nextRunBtn) {
      this.nextRunBtn.addEventListener("click", () => {
        this._closeModal();
        this.fetchNewTargetRange().then(() => this.resetTest());
      });
    }
    if (this.closeModalBtn) {
      this.closeModalBtn.addEventListener("click", () => this._closeModal());
    }
  }

  _resizeCanvas() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.ctx.resetTransform?.();
    this.ctx.scale(dpr, dpr);

    this.displayWidth = rect.width;
    this.displayHeight = rect.height;

    // Dynamic target circle radius based on canvas size
    this.nodeRadius = Math.max(20, Math.min(32, Math.min(rect.width, rect.height) * 0.042));
  }

  async fetchNewTargetRange() {
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const queryParams = new URLSearchParams();
      if (urlParams.get("count")) queryParams.set("count", urlParams.get("count"));
      if (urlParams.get("min")) queryParams.set("min", urlParams.get("min"));
      if (urlParams.get("max")) queryParams.set("max", urlParams.get("max"));

      const url = queryParams.toString() ? `/api/new_target_range?${queryParams.toString()}` : "/api/new_target_range";
      const res = await fetch(url);
      const data = await res.json();
      if (data.status === "success") {
        this.startTarget = data.start_target;
        this.endTarget = data.end_target;
        this.targetCount = data.target_count;
        this.targetList = data.targets;

        this._updateTargetRangeIndicators();
        this._setupLayout();
        this.resetTest();
      }
    } catch (err) {
      console.error("Failed to fetch target range:", err);
    }
  }

  _updateTargetRangeIndicators() {
    if (this.targetRangeValEl) {
      this.targetRangeValEl.textContent = `${this.startTarget} -> ${this.endTarget} (${this.targetCount} targets)`;
    }

    const cornerNumEl = document.getElementById("cornerFirstTargetNum");
    const cornerSubEl = document.getElementById("cornerFirstTargetSub");
    if (cornerNumEl) cornerNumEl.textContent = this.startTarget;
    if (cornerSubEl) cornerSubEl.textContent = `Sequence: ${this.startTarget} \u2192 ${this.endTarget}`;

    const overlayFirstTargetEl = document.getElementById("overlayFirstTargetNum");
    const overlaySeqEl = document.getElementById("overlaySequenceText");
    if (overlayFirstTargetEl) overlayFirstTargetEl.textContent = this.startTarget;
    if (overlaySeqEl) overlaySeqEl.textContent = `Sequence: ${this.startTarget} to ${this.endTarget} (${this.targetCount} targets total)`;
  }

  setMode(modeNumber) {
    this.activeMode = modeNumber;
    this._updateModeUI(modeNumber);
    this.resetTest();
  }

  _updateModeUI(modeNumber) {
    document.querySelectorAll(".mode-card").forEach((c) => {
      const m = parseInt(c.getAttribute("data-mode"), 10);
      c.classList.toggle("active", m === modeNumber);
    });

    if (this.modeSpecs && this.modeSpecs[modeNumber]) {
      const spec = this.modeSpecs[modeNumber];
      const titleEl = document.getElementById("overlayModeTitle");
      const descEl = document.getElementById("overlayModeDesc");
      if (titleEl) titleEl.textContent = spec.title;
      if (descEl) descEl.textContent = spec.description;
    }
  }

  _setupLayout() {
    if (!this.targetList || this.targetList.length === 0) return;
    this.layout = WebSpatialLayoutManager.generateInitialLayout(this.targetList);
    this.initialLayout = { ...this.layout };
    this.draw();
  }

  startTest() {
    if (!this.targetList || this.targetList.length === 0) return;

    // Activate Web Audio context on user gesture
    if (window.soundManager) {
      window.soundManager._initContext();
    }

    this.isStarted = true;
    this.isCompleted = false;
    this.currentStepIndex = 0;
    this.totalErrors = 0;
    this.currentStepErrors = 0;
    this.stepTimesMs = [];
    this.stepRecords = [];

    // Layout reshuffle or fresh sprinkle for this run
    this._setupLayout();

    // Start timing
    this.startPerfTime = window.performance.now();
    this.lastTargetPerfTime = this.startPerfTime;
    this.startIsoTime = new Date().toISOString();

    // Hide overlay
    this.overlay.classList.add("hidden");
    this.startBtn.disabled = true;
    this.resetBtn.disabled = false;

    // Start HUD stopwatch loop
    if (this.hudInterval) clearInterval(this.hudInterval);
    this.hudInterval = setInterval(() => this._updateHUDTimers(), 40);

    this._updateHUD();
    this.draw();
  }

  resetTest() {
    this.isStarted = false;
    this.isCompleted = false;
    this.currentStepIndex = 0;
    this.totalErrors = 0;
    this.currentStepErrors = 0;
    this.stepTimesMs = [];
    this.stepRecords = [];

    if (this.hudInterval) {
      clearInterval(this.hudInterval);
      this.hudInterval = null;
    }

    this.overlay.classList.remove("hidden");
    this.startBtn.disabled = false;
    this.resetBtn.disabled = true;

    this.stepTimerEl.textContent = "0.00s";
    this.totalTimerEl.textContent = "0.00s";
    this.errorsEl.textContent = "0";

    const nextT = this.targetList && this.targetList.length > 0 ? this.targetList[0] : "-";
    this.nextTargetEl.textContent = nextT;

    this._updateTargetRangeIndicators();
    this.draw();
  }

  _updateHUDTimers() {
    if (!this.isStarted || this.isCompleted) return;
    const now = window.performance.now();
    const stepElapsedSec = (now - this.lastTargetPerfTime) / 1000.0;
    const totalElapsedSec = (now - this.startPerfTime) / 1000.0;

    this.stepTimerEl.textContent = `${stepElapsedSec.toFixed(2)}s`;
    this.totalTimerEl.textContent = `${totalElapsedSec.toFixed(2)}s`;
  }

  _updateHUD() {
    if (this.currentStepIndex < this.targetList.length) {
      this.nextTargetEl.textContent = this.targetList[this.currentStepIndex];
    } else {
      this.nextTargetEl.textContent = "DONE";
    }
    this.errorsEl.textContent = String(this.totalErrors);
  }

  _handleCanvasClick(event) {
    if (!this.isStarted || this.isCompleted) return;

    const rect = this.canvas.getBoundingClientRect();
    const clickX = event.clientX - rect.left;
    const clickY = event.clientY - rect.top;

    // Check hit against any target circle
    let hitTarget = null;
    for (const [targetStr, [pctX, pctY]] of Object.entries(this.layout)) {
      const centerX = (pctX / 100.0) * this.displayWidth;
      const centerY = (pctY / 100.0) * this.displayHeight;
      const dist = Math.hypot(clickX - centerX, clickY - centerY);
      if (dist <= this.nodeRadius * 1.25) {
        hitTarget = targetStr;
        break;
      }
    }

    const expectedTarget = this.targetList[this.currentStepIndex];

    if (hitTarget === expectedTarget) {
      // --- CORRECT HIT ---
      const now = window.performance.now();
      const stepLatencyMs = now - this.lastTargetPerfTime;
      const cumulativeMs = now - this.startPerfTime;

      this.stepTimesMs.push(parseFloat(stepLatencyMs.toFixed(2)));
      this.stepRecords.push({
        target: expectedTarget,
        target_num: parseInt(expectedTarget, 10) || this.currentStepIndex + 1,
        step_index: this.currentStepIndex + 1,
        step_time_ms: parseFloat(stepLatencyMs.toFixed(2)),
        cumulative_time_ms: parseFloat(cumulativeMs.toFixed(2)),
        errors_in_step: this.currentStepErrors,
      });

      // Audio feedback (1150 Hz confirmation beep)
      if (window.soundManager) {
        window.soundManager.playCorrectBeep();
      }

      this.currentStepIndex++;
      this.currentStepErrors = 0;
      this.lastTargetPerfTime = now;

      // Handle Reshuffling depending on active mode rules:
      // Mode 1: Static (no reshuffle)
      // Mode 2: Static (no reshuffle)
      // Mode 3: Shuffled remaining (completed stay, uncompleted reshuffle)
      // Mode 4: Fully shuffled (all reshuffle)
      if (this.activeMode === 3) {
        const completed = this.targetList.slice(0, this.currentStepIndex);
        const uncompleted = this.targetList.slice(this.currentStepIndex);
        this.layout = WebSpatialLayoutManager.shuffleUncompletedTargets(
          this.layout,
          completed,
          uncompleted
        );
      } else if (this.activeMode === 4) {
        this.layout = WebSpatialLayoutManager.shuffleAllTargets(this.targetList);
      }

      // Check if finished
      if (this.currentStepIndex >= this.targetList.length) {
        this._finishTest(now);
      } else {
        this._updateHUD();
        this.draw();
      }
    } else {
      // --- MISCLICK / INCORRECT TARGET ---
      this.currentStepErrors++;
      this.totalErrors++;
      if (window.soundManager) {
        window.soundManager.playErrorTone();
      }
      this._updateHUD();
    }
  }

  _finishTest(finishPerfTime) {
    this.isCompleted = true;
    if (this.hudInterval) {
      clearInterval(this.hudInterval);
      this.hudInterval = null;
    }

    const totalDurationMs = finishPerfTime - this.startPerfTime;
    this.totalDurationMs = totalDurationMs;

    if (window.soundManager) {
      window.soundManager.playFinishFanfare();
    }

    this._updateHUD();
    this.draw();

    // Show Results Modal
    setTimeout(() => {
      this._openModal(totalDurationMs);
    }, 350);
  }

  draw() {
    const w = this.displayWidth;
    const h = this.displayHeight;
    this.ctx.clearRect(0, 0, w, h);

    if (!this.targetList || this.targetList.length === 0) return;

    // Draw background grid lines (subtle dark tech pattern)
    this.ctx.strokeStyle = "rgba(55, 65, 81, 0.25)";
    this.ctx.lineWidth = 1;
    const gridSpacing = 40;
    for (let x = 0; x < w; x += gridSpacing) {
      this.ctx.beginPath();
      this.ctx.moveTo(x, 0);
      this.ctx.lineTo(x, h);
      this.ctx.stroke();
    }
    for (let y = 0; y < h; y += gridSpacing) {
      this.ctx.beginPath();
      this.ctx.moveTo(0, y);
      this.ctx.lineTo(w, y);
      this.ctx.stroke();
    }

    const isVisualMarkingActive = this.activeMode === 1 || this.activeMode === 3;

    // 1. Draw Trail Lines (only for modes with visual marking: Mode 1 and Mode 3)
    if (isVisualMarkingActive && this.currentStepIndex > 1) {
      this.ctx.strokeStyle = "rgba(34, 197, 94, 0.65)";
      this.ctx.lineWidth = 3.5;
      this.ctx.setLineDash([4, 4]);

      this.ctx.beginPath();
      for (let i = 0; i < this.currentStepIndex; i++) {
        const tStr = this.targetList[i];
        const [pctX, pctY] = this.layout[tStr];
        const cx = (pctX / 100.0) * w;
        const cy = (pctY / 100.0) * h;
        if (i === 0) {
          this.ctx.moveTo(cx, cy);
        } else {
          this.ctx.lineTo(cx, cy);
        }
      }
      this.ctx.stroke();
      this.ctx.setLineDash([]);
    }

    // 2. Draw Target Nodes
    for (let i = 0; i < this.targetList.length; i++) {
      const tStr = this.targetList[i];
      const pos = this.layout[tStr];
      if (!pos) continue;

      const cx = (pos[0] / 100.0) * w;
      const cy = (pos[1] / 100.0) * h;
      const isCompleted = i < this.currentStepIndex;

      let fillColor = "#ffffff";
      let strokeColor = "#1e293b";
      let textColor = "#0f172a";
      let shadowColor = "rgba(0, 0, 0, 0.35)";

      if (isCompleted) {
        if (isVisualMarkingActive) {
          // Completed & Lit (Modes 1 & 3): Bright vivid green
          fillColor = "#22c55e";
          strokeColor = "#16a34a";
          textColor = "#ffffff";
          shadowColor = "rgba(34, 197, 94, 0.5)";
        } else {
          // Completed & Unlit (Modes 2 & 4): Looks IDENTICAL to uncompleted targets!
          fillColor = "#ffffff";
          strokeColor = "#1e293b";
          textColor = "#0f172a";
        }
      }

      // Drop shadow
      this.ctx.shadowColor = shadowColor;
      this.ctx.shadowBlur = 8;
      this.ctx.shadowOffsetX = 0;
      this.ctx.shadowOffsetY = 2;

      // Circle
      this.ctx.beginPath();
      this.ctx.arc(cx, cy, this.nodeRadius, 0, Math.PI * 2);
      this.ctx.fillStyle = fillColor;
      this.ctx.fill();

      // Border
      this.ctx.shadowBlur = 0;
      this.ctx.lineWidth = 2.5;
      this.ctx.strokeStyle = strokeColor;
      this.ctx.stroke();

      // Number label
      this.ctx.fillStyle = textColor;
      this.ctx.font = `bold ${Math.round(this.nodeRadius * 0.95)}px ui-sans-serif, system-ui, sans-serif`;
      this.ctx.textAlign = "center";
      this.ctx.textBaseline = "middle";
      this.ctx.fillText(tStr, cx, cy);
    }
  }

  _openModal(totalDurationMs) {
    document.getElementById("modalTotalTime").textContent = `${(totalDurationMs / 1000.0).toFixed(2)}s`;

    const meanMs =
      this.stepTimesMs.length > 0
        ? this.stepTimesMs.reduce((a, b) => a + b, 0) / this.stepTimesMs.length
        : 0;
    document.getElementById("modalMeanTime").textContent = `${meanMs.toFixed(1)} ms`;
    document.getElementById("modalErrors").textContent = String(this.totalErrors);

    const modeTitle = this.modeSpecs ? this.modeSpecs[this.activeMode]?.short_name : `Mode ${this.activeMode}`;
    document.getElementById("modalModeTitle").textContent = modeTitle;

    // Populate steps table
    const tbody = document.getElementById("modalStepsTbody");
    tbody.innerHTML = "";
    this.stepRecords.forEach((step) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${step.target}</strong></td>
        <td>${step.step_time_ms.toFixed(1)} ms</td>
        <td>${(step.cumulative_time_ms / 1000.0).toFixed(2)} s</td>
        <td>${step.errors_in_step}</td>
      `;
      tbody.appendChild(tr);
    });

    // Draw mini latency plot inside modal
    this._renderModalMiniChart();

    this.resultsModal.classList.add("open");
  }

  _closeModal() {
    this.resultsModal.classList.remove("open");
  }

  _renderModalMiniChart() {
    const canvas = document.getElementById("modalChartCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.parentElement.clientWidth - 28;
    const h = 170;

    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.resetTransform?.();
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, w, h);

    if (this.stepTimesMs.length < 2) {
      ctx.fillStyle = "#64748b";
      ctx.font = "12px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Complete at least 2 steps to view latency curve", w / 2, h / 2);
      return;
    }

    const margin = { top: 20, right: 25, bottom: 30, left: 55 };
    const plotW = w - margin.left - margin.right;
    const plotH = h - margin.top - margin.bottom;

    const maxVal = Math.max(...this.stepTimesMs) * 1.15;
    const minVal = Math.max(0, Math.min(...this.stepTimesMs) * 0.85);

    // Grid lines & Y-axis labels
    ctx.strokeStyle = "rgba(75, 85, 99, 0.3)";
    ctx.lineWidth = 1;
    ctx.fillStyle = "#94a3b8";
    ctx.font = "10px monospace";
    ctx.textAlign = "right";

    const yTicks = 4;
    for (let i = 0; i <= yTicks; i++) {
      const val = minVal + (i / yTicks) * (maxVal - minVal);
      const y = margin.top + plotH - (i / yTicks) * plotH;
      ctx.beginPath();
      ctx.moveTo(margin.left, y);
      ctx.lineTo(margin.left + plotW, y);
      ctx.stroke();
      ctx.fillText(`${Math.round(val)}ms`, margin.left - 6, y + 3);
    }

    // Points coordinates
    const points = this.stepTimesMs.map((val, idx) => {
      const x = margin.left + (idx / (this.stepTimesMs.length - 1)) * plotW;
      const y = margin.top + plotH - ((val - minVal) / (maxVal - minVal)) * plotH;
      return [x, y];
    });

    // Draw empirical curve
    ctx.beginPath();
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 2.5;
    points.forEach(([x, y], idx) => {
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Draw markers
    points.forEach(([x, y]) => {
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fillStyle = "#38bdf8";
      ctx.fill();
      ctx.strokeStyle = "#0f172a";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });

    // Fit trendline
    const n = points.length;
    const xs = points.map((_, i) => i + 1);
    const ys = this.stepTimesMs;
    const sx = xs.reduce((a, b) => a + b, 0);
    const sy = ys.reduce((a, b) => a + b, 0);
    const sxx = xs.reduce((a, b) => a + b * b, 0);
    const sxy = xs.reduce((a, b, i) => a + b * ys[i], 0);
    const denom = n * sxx - sx * sx;
    const slope = denom !== 0 ? (n * sxy - sx * sy) / denom : 0;
    const intercept = (sy - slope * sx) / n;

    const trendY1 = margin.top + plotH - ((slope * 1 + intercept - minVal) / (maxVal - minVal)) * plotH;
    const trendY2 = margin.top + plotH - ((slope * n + intercept - minVal) / (maxVal - minVal)) * plotH;

    ctx.beginPath();
    ctx.strokeStyle = "#f59e0b";
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 4]);
    ctx.moveTo(points[0][0], trendY1);
    ctx.lineTo(points[points.length - 1][0], trendY2);
    ctx.stroke();
    ctx.setLineDash([]);

    // Trend label
    ctx.fillStyle = "#f59e0b";
    ctx.textAlign = "left";
    ctx.font = "11px monospace";
    ctx.fillText(`Slope: ${slope > 0 ? "+" : ""}${slope.toFixed(1)} ms/target`, margin.left + 8, margin.top + 14);
  }

  async submitResults() {
    const rawName = (this.participantInput?.value || "").trim() || "anonymous";

    this.submitBtn.disabled = true;
    this.submitBtn.textContent = "Submitting & Hashing...";

    const payload = {
      name: rawName,
      mode: this.activeMode,
      step_times_ms: this.stepTimesMs,
      steps: this.stepRecords,
      total_duration_ms: this.totalDurationMs,
      total_errors: this.totalErrors,
      start_target: this.startTarget,
      end_target: this.endTarget,
      target_count: this.targetCount,
      targets: this.targetList,
      initial_layout: this.initialLayout,
      canvas_size: { width: this.displayWidth, height: this.displayHeight },
      start_iso_time: this.startIsoTime,
    };

    try {
      const res = await fetch("/api/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (data.status === "success") {
        this._showToast(`Saved! Anonymized ID: ${data.anonymous_id}`, "success");
        this.submitBtn.textContent = "Saved Successfully";
        this.submitBtn.classList.remove("btn-primary");
        this.submitBtn.classList.add("btn-secondary");
      } else {
        this._showToast(`Submission failed: ${data.message}`, "error");
        this.submitBtn.disabled = false;
        this.submitBtn.textContent = "Try Again";
      }
    } catch (err) {
      console.error("Submit error:", err);
      this._showToast("Network error submitting results", "error");
      this.submitBtn.disabled = false;
      this.submitBtn.textContent = "Try Again";
    }
  }

  _showToast(msg, type = "success") {
    let toast = document.getElementById("toastNotification");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "toastNotification";
      toast.className = "toast";
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.className = `toast show ${type}`;
    setTimeout(() => {
      toast.classList.remove("show");
    }, 4000);
  }
}

// Boot on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  window.tmtApp = new TMTSpatialMemoryApp();
  window.tmtApp.init();
});

