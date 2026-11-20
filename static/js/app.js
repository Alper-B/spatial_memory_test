/**
 * app.js
 * Comprehensive Client-Side Controller for TMT-A Spatial Memory Experiment.
 * Implements strict experimental protocol with zero degrees of freedom:
 *   1. Phase 1: Mandatory Practice Phase (4 Trials: Mode 1 -> 2 -> 3 -> 4)
 *      with detailed educational tutorial modals before each mode.
 *   2. Phase 2: Formal Experiment (16 Randomized Rounds: 4 per mode)
 *      counterbalanced with strict cancellation and re-queue rules.
 *   3. Phase 3: Completion & ZIP Package Export for researcher submission.
 */

class TMTSpatialMemoryApp {
  constructor() {
    this.canvas = document.getElementById("experimentCanvas");
    this.ctx = this.canvas.getContext("2d");

    // Session & Protocol Tracking
    this.sessionId = null;
    this.anonymousId = "Anon-Loading";
    this.phase = "PRACTICE"; // "PRACTICE" | "PRACTICE_COMPLETE" | "EXPERIMENT" | "COMPLETED"
    this.practiceSequence = [1, 2, 3, 4];
    this.practiceIndex = 0; // 0 to 3

    // Formal Experiment Queue (16 rounds: 4 of each mode, randomized)
    this.experimentQueue = [];
    this.completedExperimentRounds = 0;
    this.totalExperimentRounds = 16;
    this.modeQuotas = { 1: 0, 2: 0, 3: 0, 4: 0 };
    this.targetQuotaPerMode = 4;
    this.sessionResults = []; // stores all submitted run records

    // Active Round State
    this.activeMode = 1;
    this.isPractice = true;
    this.targetList = [];
    this.startTarget = 10;
    this.endTarget = 19;
    this.targetCount = 10;
    this.layout = {};
    this.initialLayout = {};

    this.currentStepIndex = 0;
    this.isStarted = false;
    this.isCompleted = false;
    this.hasSubmitted = false;

    // High Precision Timers
    this.startPerfTime = 0;
    this.lastTargetPerfTime = 0;
    this.stepTimesMs = [];
    this.stepRecords = [];
    this.totalErrors = 0;
    this.currentStepErrors = 0;
    this.hudInterval = null;
    this.nodeRadius = 24;

    // Backend specs
    this.serverConfig = null;
    this.modeSpecs = null;

    // Cache DOM Elements
    this._cacheDOMElements();
    this._bindEvents();
  }

  _cacheDOMElements() {
    // Header & Protocol HUD
    this.protocolStatusBadge = document.getElementById("protocolStatusBadge");
    this.protocolPhaseText = document.getElementById("protocolPhaseText");
    this.anonymousIdValEl = document.getElementById("anonymousIdVal");
    this.sessionDisplayIdEl = document.getElementById("sessionDisplayId");
    this.targetRangeValEl = document.getElementById("targetRangeVal");
    this.restartSessionBtn = document.getElementById("restartSessionBtn");

    // Progress bar
    this.progressStepTitleEl = document.getElementById("progressStepTitle");
    this.progressCompletedNumEl = document.getElementById("progressCompletedNum");
    this.progressTotalNumEl = document.getElementById("progressTotalNum");
    this.progressPercentNumEl = document.getElementById("progressPercentNum");
    this.protocolProgressBarEl = document.getElementById("protocolProgressBar");

    // Mode Quota elements
    this.quotaCountEls = {
      1: document.getElementById("quotaCount1"),
      2: document.getElementById("quotaCount2"),
      3: document.getElementById("quotaCount3"),
      4: document.getElementById("quotaCount4"),
    };
    this.statusTagEls = {
      1: document.getElementById("statusTag1"),
      2: document.getElementById("statusTag2"),
      3: document.getElementById("statusTag3"),
      4: document.getElementById("statusTag4"),
    };
    this.modeCards = {
      1: document.getElementById("modeCard1"),
      2: document.getElementById("modeCard2"),
      3: document.getElementById("modeCard3"),
      4: document.getElementById("modeCard4"),
    };

    // HUD Elements
    this.hudNextTargetEl = document.getElementById("hudNextTarget");
    this.hudStepTimerEl = document.getElementById("hudStepTimer");
    this.hudTotalTimerEl = document.getElementById("hudTotalTimer");
    this.hudErrorsEl = document.getElementById("hudErrors");
    this.hudRoundPhaseEl = document.getElementById("hudRoundPhase");
    this.startBtn = document.getElementById("startTestBtn");
    this.cancelBtn = document.getElementById("resetTestBtn");

    // Canvas overlay
    this.overlay = document.getElementById("canvasOverlay");
    this.overlayPhaseTag = document.getElementById("overlayPhaseTag");
    this.overlayModeTitle = document.getElementById("overlayModeTitle");
    this.overlayModeDesc = document.getElementById("overlayModeDesc");
    this.overlayFirstTargetNum = document.getElementById("overlayFirstTargetNum");
    this.overlaySequenceText = document.getElementById("overlaySequenceText");
    this.overlayStartBtn = document.getElementById("overlayStartBtn");
    this.overlayReviewTutorialBtn = document.getElementById("overlayReviewTutorialBtn");
    this.cornerFirstTargetNum = document.getElementById("cornerFirstTargetNum");
    this.cornerFirstTargetSub = document.getElementById("cornerFirstTargetSub");

    // Modals
    this.tutorialModal = document.getElementById("tutorialModal");
    this.tutProceedBtn = document.getElementById("tutProceedBtn");
    this.practiceCompleteModal = document.getElementById("practiceCompleteModal");
    this.beginExperimentBtn = document.getElementById("beginExperimentBtn");
    this.cancelConfirmModal = document.getElementById("cancelConfirmModal");
    this.cancelModalConfirmBtn = document.getElementById("cancelModalConfirmBtn");
    this.cancelModalResumeBtn = document.getElementById("cancelModalResumeBtn");
    this.resultsModal = document.getElementById("resultsModal");
    this.nextRunBtn = document.getElementById("nextRunBtn");
    this.closeModalBtn = document.getElementById("closeModalBtn");
    this.experimentCompleteModal = document.getElementById("experimentCompleteModal");
    this.downloadZipBtn = document.getElementById("downloadZipBtn");
    this.startFreshSessionBtn = document.getElementById("startFreshSessionBtn");
  }

  async init() {
    this._resizeCanvas();
    window.addEventListener("resize", () => {
      this._resizeCanvas();
      this.draw();
    });

    try {
      // 1. Fetch server config & client anonymous ID
      const res = await fetch("/api/config");
      const data = await res.json();
      if (data.status === "success") {
        this.serverConfig = data.config;
        this.modeSpecs = data.modes;
        if (data.anonymous_id) {
          this.anonymousId = data.anonymous_id;
          if (this.anonymousIdValEl) {
            this.anonymousIdValEl.textContent = data.anonymous_id;
          }
        }
      }

      // 2. Check local persistence to resume active session if one exists
      const savedState = this._loadLocalState();
      if (savedState && savedState.sessionId) {
        this._restoreSessionState(savedState);
      } else {
        // Initialize brand new session
        await this._startNewSession();
      }

      // Setup active round
      await this._prepareCurrentRound();
    } catch (err) {
      console.error("Initialization error:", err);
      this._showToast("Initialization error. Using fallback offline mode.", "error");
      this.sessionId = `session_offline_${Date.now()}`;
      this._initDefaultExperimentQueue();
      await this.fetchNewTargetRange();
    }
  }

  async _startNewSession() {
    try {
      const res = await fetch("/api/session/start", { method: "POST" });
      const data = await res.json();
      if (data.status === "success") {
        this.sessionId = data.session_id;
        this.anonymousId = data.anonymous_id || this.anonymousId;
        this.experimentQueue = data.experiment_queue || this._generateShuffledQueue();
      } else {
        throw new Error(data.message || "Failed to start session");
      }
    } catch (e) {
      console.warn("Backend session start failed, generating locally:", e);
      const safeAnon = this.anonymousId.replace(/[^a-zA-Z0-9]/g, "").toLowerCase();
      this.sessionId = `session_${safeAnon}_${Date.now()}`;
      this.experimentQueue = this._generateShuffledQueue();
    }

    this.phase = "PRACTICE";
    this.practiceIndex = 0;
    this.completedExperimentRounds = 0;
    this.modeQuotas = { 1: 0, 2: 0, 3: 0, 4: 0 };
    this.sessionResults = [];
    this.hasSubmitted = false;
    this._saveLocalState();

    if (this.sessionDisplayIdEl) {
      this.sessionDisplayIdEl.textContent = this.sessionId;
    }

    // Trigger initial Tutorial Modal for Practice Round 1
    setTimeout(() => {
      this._showTutorialModal(1, 1);
    }, 450);
  }

  _generateShuffledQueue() {
    // 4 rounds each of Mode 1, 2, 3, 4 -> 16 items
    const queue = [1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4];
    // Fisher-Yates shuffle
    for (let i = queue.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [queue[i], queue[j]] = [queue[j], queue[i]];
    }
    return queue;
  }

  _rebuildRemainingQueue() {
    const queue = [];
    for (let m = 1; m <= 4; m++) {
      const done = this.modeQuotas[m] || 0;
      const needed = Math.max(0, this.targetQuotaPerMode - done);
      for (let i = 0; i < needed; i++) {
        queue.push(m);
      }
    }
    for (let i = queue.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [queue[i], queue[j]] = [queue[j], queue[i]];
    }
    return queue;
  }

  _initDefaultExperimentQueue() {
    this.experimentQueue = this._generateShuffledQueue();
  }

  _saveLocalState() {
    const state = {
      sessionId: this.sessionId,
      anonymousId: this.anonymousId,
      phase: this.phase,
      practiceIndex: this.practiceIndex,
      experimentQueue: this.experimentQueue,
      completedExperimentRounds: this.completedExperimentRounds,
      modeQuotas: this.modeQuotas,
      sessionResults: this.sessionResults,
    };
    try {
      localStorage.setItem("tmt_spatial_memory_state", JSON.stringify(state));
    } catch (e) {
      // Storage quota or private mode
    }
  }

  _loadLocalState() {
    try {
      const raw = localStorage.getItem("tmt_spatial_memory_state");
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  _clearLocalState() {
    try {
      localStorage.removeItem("tmt_spatial_memory_state");
    } catch (e) {}
  }

  _restoreSessionState(saved) {
    this.sessionId = saved.sessionId;
    this.anonymousId = saved.anonymousId || this.anonymousId;
    this.phase = saved.phase || "PRACTICE";
    this.practiceIndex = saved.practiceIndex || 0;
    this.completedExperimentRounds = saved.completedExperimentRounds || 0;
    this.modeQuotas = saved.modeQuotas || { 1: 0, 2: 0, 3: 0, 4: 0 };
    this.sessionResults = saved.sessionResults || [];

    // Ensure valid non-empty queue if in experiment phase
    if (saved.experimentQueue && Array.isArray(saved.experimentQueue) && saved.experimentQueue.length > 0) {
      this.experimentQueue = saved.experimentQueue;
    } else {
      this.experimentQueue = this._rebuildRemainingQueue();
    }

    // Always reset submission flag on restore so rounds never lock
    this.hasSubmitted = false;

    if (this.sessionDisplayIdEl) {
      this.sessionDisplayIdEl.textContent = this.sessionId;
    }
    if (this.anonymousIdValEl) {
      this.anonymousIdValEl.textContent = this.anonymousId;
    }

    if (this.phase === "PRACTICE_COMPLETE") {
      this.practiceCompleteModal.classList.add("open");
    } else if (this.phase === "COMPLETED" || this.completedExperimentRounds >= this.totalExperimentRounds) {
      this.phase = "COMPLETED";
      this._openExperimentCompleteModal();
    }
  }

  _bindEvents() {
    // Start Buttons
    this.startBtn.addEventListener("click", () => this.startTest());
    if (this.overlayStartBtn) {
      this.overlayStartBtn.addEventListener("click", () => this.startTest());
    }

    // Cancel Button -> Opens confirmation modal
    this.cancelBtn.addEventListener("click", () => {
      if (this.isStarted && !this.isCompleted) {
        this._openCancelConfirmModal();
      }
    });

    // Cancel confirmation actions
    if (this.cancelModalResumeBtn) {
      this.cancelModalResumeBtn.addEventListener("click", () => {
        this.cancelConfirmModal.classList.remove("open");
      });
    }

    if (this.cancelModalConfirmBtn) {
      this.cancelModalConfirmBtn.addEventListener("click", () => {
        this._confirmCancelRound();
      });
    }

    // Canvas click
    this.canvas.addEventListener("pointerdown", (e) => this._handleCanvasClick(e));

    // Tutorial Proceed
    if (this.tutProceedBtn) {
      this.tutProceedBtn.addEventListener("click", () => {
        this.tutorialModal.classList.remove("open");
      });
    }

    // Overlay Review Tutorial
    if (this.overlayReviewTutorialBtn) {
      this.overlayReviewTutorialBtn.addEventListener("click", () => {
        const step = this.phase === "PRACTICE" ? this.practiceIndex + 1 : null;
        this._showTutorialModal(this.activeMode, step);
      });
    }

    // Transition from Practice to Experiment
    if (this.beginExperimentBtn) {
      this.beginExperimentBtn.addEventListener("click", async () => {
        this.practiceCompleteModal.classList.remove("open");
        this.phase = "EXPERIMENT";
        this.hasSubmitted = false;
        this._saveLocalState();
        await this._prepareCurrentRound();
      });
    }

    // Results Modal actions
    if (this.nextRunBtn) {
      this.nextRunBtn.addEventListener("click", async () => {
        this._closeModal();
        await this._advanceToNextRound();
      });
    }

    if (this.closeModalBtn) {
      this.closeModalBtn.addEventListener("click", async () => {
        this._closeModal();
        await this._advanceToNextRound();
      });
    }

    // Download ZIP button
    if (this.downloadZipBtn) {
      this.downloadZipBtn.addEventListener("click", () => {
        this._downloadResultsZip();
      });
    }

    // Restart session button in header
    if (this.restartSessionBtn) {
      this.restartSessionBtn.addEventListener("click", async () => {
        if (confirm("Restart session from Trial 1? Any unsubmitted progress will be reset.")) {
          this._clearLocalState();
          await this._startNewSession();
          await this._prepareCurrentRound();
        }
      });
    }

    // Start fresh session button on completion screen
    if (this.startFreshSessionBtn) {
      this.startFreshSessionBtn.addEventListener("click", async () => {
        if (confirm("Start a brand new session? This will reset all current progress.")) {
          this._clearLocalState();
          this.experimentCompleteModal.classList.remove("open");
          await this._startNewSession();
          await this._prepareCurrentRound();
        }
      });
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
    this.nodeRadius = Math.max(20, Math.min(32, Math.min(rect.width, rect.height) * 0.042));
  }

  async _prepareCurrentRound() {
    this.hasSubmitted = false; // Reset submission guard for every new round

    if (this.phase === "PRACTICE") {
      this.isPractice = true;
      this.activeMode = this.practiceSequence[this.practiceIndex];
    } else if (this.phase === "EXPERIMENT") {
      this.isPractice = false;
      // Sanity check queue
      if (!this.experimentQueue || !Array.isArray(this.experimentQueue) || this.experimentQueue.length === 0) {
        if (this.completedExperimentRounds < this.totalExperimentRounds) {
          this.experimentQueue = this._rebuildRemainingQueue();
        }
      }

      if (this.experimentQueue.length > 0) {
        this.activeMode = this.experimentQueue[0];
      } else {
        this.phase = "COMPLETED";
        this._openExperimentCompleteModal();
        return;
      }
    } else if (this.phase === "COMPLETED") {
      this._openExperimentCompleteModal();
      return;
    }

    this._updateProtocolUI();
    await this.fetchNewTargetRange();
    this.resetTest();
  }

  _updateProtocolUI() {
    // 1. Header Phase Text
    if (this.protocolPhaseText) {
      if (this.phase === "PRACTICE") {
        this.protocolPhaseText.textContent = `Practice Phase: Trial ${this.practiceIndex + 1} of 4`;
      } else if (this.phase === "EXPERIMENT") {
        this.protocolPhaseText.textContent = `Formal Experiment: Round ${this.completedExperimentRounds + 1} of 16`;
      } else if (this.phase === "COMPLETED") {
        this.protocolPhaseText.textContent = `Experiment Complete (16/16)`;
      }
    }

    // 2. Progress Bar
    const progressPct =
      this.phase === "PRACTICE"
        ? Math.round((this.practiceIndex / 4) * 20) // Practice is first 20%
        : Math.round(20 + (this.completedExperimentRounds / this.totalExperimentRounds) * 80);

    if (this.protocolProgressBarEl) {
      this.protocolProgressBarEl.style.width = `${progressPct}%`;
    }
    if (this.progressPercentNumEl) {
      this.progressPercentNumEl.textContent = `${progressPct}%`;
    }
    if (this.progressCompletedNumEl) {
      this.progressCompletedNumEl.textContent = String(this.completedExperimentRounds);
    }
    if (this.progressTotalNumEl) {
      this.progressTotalNumEl.textContent = String(this.totalExperimentRounds);
    }

    if (this.progressStepTitleEl) {
      if (this.phase === "PRACTICE") {
        const spec = this.modeSpecs ? this.modeSpecs[this.activeMode] : null;
        const name = spec ? spec.title : `Mode ${this.activeMode}`;
        this.progressStepTitleEl.innerHTML = `🎓 <strong>Practice Phase:</strong> Trial ${this.practiceIndex + 1} of 4 (${name})`;
      } else if (this.phase === "EXPERIMENT") {
        const spec = this.modeSpecs ? this.modeSpecs[this.activeMode] : null;
        const name = spec ? spec.title : `Mode ${this.activeMode}`;
        this.progressStepTitleEl.innerHTML = `🔬 <strong>Formal Experiment:</strong> Round ${this.completedExperimentRounds + 1} of 16 (${name})`;
      } else {
        this.progressStepTitleEl.innerHTML = `🏆 <strong>Experiment Complete!</strong> All 16 rounds verified.`;
      }
    }

    // 3. Mode Quota Cards & Active Highlight
    for (let m = 1; m <= 4; m++) {
      const card = this.modeCards[m];
      const countEl = this.quotaCountEls[m];
      const statusEl = this.statusTagEls[m];

      if (countEl) {
        countEl.textContent = `${this.modeQuotas[m]} / ${this.targetQuotaPerMode}`;
      }

      if (card) {
        card.classList.toggle("active", m === this.activeMode && this.phase !== "COMPLETED");
        card.classList.toggle("completed-mode", this.modeQuotas[m] >= this.targetQuotaPerMode);
      }

      if (statusEl) {
        if (this.modeQuotas[m] >= this.targetQuotaPerMode) {
          statusEl.textContent = "Complete ✓";
          statusEl.className = "mode-status-tag done";
        } else if (m === this.activeMode && this.phase !== "COMPLETED") {
          statusEl.textContent = "Active Now";
          statusEl.className = "mode-status-tag active";
        } else {
          statusEl.textContent = "Pending";
          statusEl.className = "mode-status-tag";
        }
      }
    }

    // 4. Overlay & HUD tags
    if (this.hudRoundPhaseEl) {
      this.hudRoundPhaseEl.textContent =
        this.phase === "PRACTICE"
          ? `Trial ${this.practiceIndex + 1}/4`
          : `Round ${this.completedExperimentRounds + 1}/16`;
    }

    if (this.overlayPhaseTag) {
      this.overlayPhaseTag.textContent =
        this.phase === "PRACTICE"
          ? `🎓 MANDATORY PRACTICE TRIAL ${this.practiceIndex + 1} OF 4`
          : `🔬 FORMAL EXPERIMENT &bull; ROUND ${this.completedExperimentRounds + 1} OF 16`;
    }

    if (this.modeSpecs && this.modeSpecs[this.activeMode]) {
      const spec = this.modeSpecs[this.activeMode];
      if (this.overlayModeTitle) this.overlayModeTitle.textContent = spec.title;
      if (this.overlayModeDesc) this.overlayModeDesc.textContent = spec.description;
    }
  }

  _showTutorialModal(modeNumber, trialStep = null) {
    const tutData = this._getTutorialData(modeNumber);
    if (!tutData) return;

    const badgeEl = document.getElementById("tutStepBadge");
    const titleEl = document.getElementById("tutTitle");
    const subtitleEl = document.getElementById("tutSubtitle");
    const visualContentEl = document.getElementById("tutVisualContent");
    const objTextEl = document.getElementById("tutObjectiveText");
    const cogTextEl = document.getElementById("tutCognitiveText");
    const stratTextEl = document.getElementById("tutStrategyText");
    const rulesListEl = document.getElementById("tutRulesList");

    if (badgeEl) {
      badgeEl.textContent = trialStep ? `PRACTICE TRIAL ${trialStep} OF 4` : `MODE ${modeNumber} PROTOCOL`;
    }
    if (titleEl) titleEl.textContent = tutData.title;
    if (subtitleEl) subtitleEl.textContent = tutData.subtitle;
    if (visualContentEl) visualContentEl.innerHTML = tutData.visualHtml;
    if (objTextEl) objTextEl.textContent = tutData.objective;
    if (cogTextEl) cogTextEl.textContent = tutData.cognitive;
    if (stratTextEl) stratTextEl.textContent = tutData.strategy;

    if (rulesListEl) {
      rulesListEl.innerHTML = "";
      tutData.rules.forEach((rule) => {
        const li = document.createElement("li");
        li.innerHTML = rule;
        rulesListEl.appendChild(li);
      });
    }

    this.tutorialModal.classList.add("open");
  }

  _getTutorialData(mode) {
    const data = {
      1: {
        title: "Mode 1: Normal Static & Lit",
        subtitle: "Full Cognitive Decomposition: Spatial Memory + Visual Marking Active",
        objective: "Click sequential targets in ascending order (e.g. 10 → 11 → 12) as fast as possible.",
        cognitive: "Your brain relies on both spatial memory (remembering positions seen during visual scanning) and bottom-up pop-out cues (green completed targets stand out clearly).",
        strategy: "Scan ahead while clicking. When completed targets turn green, immediately eliminate them from your visual search area.",
        visualHtml: `
          <div class="visual-preview-pill">
            <div class="visual-circle-preview visual-circle-green">10</div>
            <span>Completed & Lit (Green)</span>
          </div>
          <span style="color:#64748b; font-weight:800;">&rarr;</span>
          <div class="visual-preview-pill">
            <div class="visual-circle-preview visual-circle-white">11</div>
            <span>Active Target</span>
          </div>
          <span style="color:#64748b; font-weight:800;">&rarr;</span>
          <div class="visual-preview-pill">
            <div class="visual-circle-preview visual-circle-white">12</div>
            <span>Remaining Target</span>
          </div>
        `,
        rules: [
          "<strong>Static Layout:</strong> Target positions stay completely fixed throughout the round.",
          "<strong>Visual Marking:</strong> Correctly clicked targets light up bright green.",
          "<strong>Trail Path:</strong> A vivid green dashed line connects consecutive completed targets.",
          "<strong>Audio Feedback:</strong> A crisp confirmation beep sounds on every correct hit.",
        ],
      },
      2: {
        title: "Mode 2: Memory Only (Static + Unlit)",
        subtitle: "Spatial Working Memory Isolated: Visual Pop-Out Disabled",
        objective: "Click sequential targets in ascending numerical order as fast as possible.",
        cognitive: "Completed targets DO NOT light up green—they remain identical white! You must rely purely on your internal spatial working memory to remember which targets you have already clicked and where future targets are located.",
        strategy: "Memorize locations of surrounding numbers when scanning. Since visited circles stay identical, keep an active mental map of completed items.",
        visualHtml: `
          <div class="visual-preview-pill">
            <div class="visual-circle-preview visual-circle-white">10</div>
            <span>Completed (Stays White!)</span>
          </div>
          <span style="color:#64748b; font-weight:800;">&rarr;</span>
          <div class="visual-preview-pill">
            <div class="visual-circle-preview visual-circle-white">11</div>
            <span>Active Target (White)</span>
          </div>
          <span style="color:#64748b; font-weight:800;">&rarr;</span>
          <div class="visual-preview-pill">
            <div class="visual-circle-preview visual-circle-white">12</div>
            <span>Remaining (White)</span>
          </div>
        `,
        rules: [
          "<strong>Static Positions:</strong> Target positions remain in fixed coordinates.",
          "<strong>Unlit Targets:</strong> Correctly clicked targets remain white and look identical to unvisited targets.",
          "<strong>No Trails:</strong> No connection lines are drawn.",
          "<strong>Audio Confirmation:</strong> A high-frequency beep confirms each correct hit. Keep sound enabled!",
        ],
      },
      3: {
        title: "Mode 3: Bottom-Up Only (Shuffled Remaining + Lit)",
        subtitle: "Visual Marking Isolated: Spatial Memory Wiped",
        objective: "Click sequential targets in ascending numerical order as fast as possible.",
        cognitive: "Completed targets turn green and stay in place, decreasing clutter. HOWEVER, after EVERY correct click, ALL uncompleted targets instantly shuffle to new random coordinates, wiping out your spatial memory of future target locations!",
        strategy: "Do not waste cognitive effort trying to memorize future target locations, because they move instantly when you click! Focus on spotting the next target number once the layout shifts.",
        visualHtml: `
          <div class="visual-preview-pill">
            <div class="visual-circle-preview visual-circle-green">10</div>
            <span>Completed (Fixed Green)</span>
          </div>
          <span style="color:#64748b; font-weight:800;">+</span>
          <div class="visual-preview-pill" style="border-color: rgba(59, 130, 246, 0.4);">
            <div class="visual-circle-preview visual-circle-white">11</div>
            <span>Shuffles Location on Click!</span>
          </div>
        `,
        rules: [
          "<strong>Dynamic Reshuffling:</strong> After every correct click, ALL remaining uncompleted targets move to new positions.",
          "<strong>Completed Stay Fixed:</strong> Visited targets stay green in their original locations.",
          "<strong>Visual Distractor Reduction:</strong> Green targets serve as markers indicating which areas to ignore.",
          "<strong>Green Trail:</strong> Connects completed targets.",
        ],
      },
      4: {
        title: "Mode 4: Control Baseline (Fully Shuffled + Unlit)",
        subtitle: "Pure Visual Search: Zero Spatial Memory & Zero Visual Cues",
        objective: "Click sequential targets in ascending numerical order as fast as possible.",
        cognitive: "Both spatial memory and visual marking pop-out cues are completely eliminated. After every hit, ALL targets on screen shuffle to new positions, and NONE light up. This provides the scientific baseline for raw visual search speed.",
        strategy: "Rapidly scan the screen for the current target number. Listen for the audio confirmation beep.",
        visualHtml: `
          <div class="visual-preview-pill" style="border-color: rgba(239, 68, 68, 0.4);">
            <div class="visual-circle-preview visual-circle-white">ALL</div>
            <span>ALL Targets Reshuffle on Every Click</span>
          </div>
          <span style="color:#64748b; font-weight:800;">&bull;</span>
          <div class="visual-preview-pill">
            <span>None Turn Green</span>
          </div>
        `,
        rules: [
          "<strong>Full Layout Reshuffle:</strong> ALL circles on the screen move to new random positions on every click.",
          "<strong>Zero Visual Marking:</strong> All circles remain identical white circles.",
          "<strong>No Trails:</strong> Pure visual scanning test.",
          "<strong>Audio Confirmation:</strong> Beeps confirm each correct hit.",
        ],
      },
    };

    return data[mode];
  }

  _openCancelConfirmModal() {
    const spec = this.modeSpecs ? this.modeSpecs[this.activeMode] : null;
    const name = spec ? spec.title : `Mode ${this.activeMode}`;
    const subtitleEl = document.getElementById("cancelModalSubtitle");
    const modeNameEl = document.getElementById("cancelModalModeName");

    if (subtitleEl) {
      subtitleEl.textContent =
        this.phase === "PRACTICE"
          ? `Practice Trial ${this.practiceIndex + 1} will be restarted.`
          : `Round ${this.completedExperimentRounds + 1} will be re-queued.`;
    }
    if (modeNameEl) {
      modeNameEl.textContent = name;
    }

    this.cancelConfirmModal.classList.add("open");
  }

  _confirmCancelRound() {
    this.cancelConfirmModal.classList.remove("open");

    // Abort active round
    this.isStarted = false;
    this.isCompleted = false;
    this.hasSubmitted = false;
    if (this.hudInterval) {
      clearInterval(this.hudInterval);
      this.hudInterval = null;
    }

    if (this.phase === "PRACTICE") {
      this._showToast(`Practice Trial ${this.practiceIndex + 1} cancelled. Restarting trial.`, "error");
    } else if (this.phase === "EXPERIMENT") {
      // Re-insert cancelled mode into the queue!
      if (this.experimentQueue.length > 0) {
        const cancelledMode = this.experimentQueue.shift();
        this.experimentQueue.push(cancelledMode);
      }
      this._saveLocalState();
      this._showToast(
        `Round cancelled. Mode ${this.activeMode} has been re-queued to maintain 16 completed runs.`,
        "error"
      );
    }

    this._prepareCurrentRound();
  }

  async fetchNewTargetRange() {
    try {
      const res = await fetch("/api/new_target_range");
      const data = await res.json();
      if (data.status === "success") {
        this.startTarget = data.start_target;
        this.endTarget = data.end_target;
        this.targetCount = data.target_count;
        this.targetList = data.targets;

        this._updateTargetRangeIndicators();
        this._setupLayout();
      }
    } catch (err) {
      console.warn("Failed to fetch target range from API, generating fallback:", err);
      const start = Math.floor(Math.random() * 80) + 10;
      this.startTarget = start;
      this.endTarget = start + 9;
      this.targetCount = 10;
      this.targetList = Array.from({ length: 10 }, (_, i) => String(start + i));
      this._updateTargetRangeIndicators();
      this._setupLayout();
    }
  }

  _updateTargetRangeIndicators() {
    if (this.targetRangeValEl) {
      this.targetRangeValEl.textContent = `${this.startTarget} \u2192 ${this.endTarget} (${this.targetCount} targets)`;
    }

    if (this.cornerFirstTargetNum) this.cornerFirstTargetNum.textContent = this.startTarget;
    if (this.cornerFirstTargetSub) this.cornerFirstTargetSub.textContent = `Sequence: ${this.startTarget} \u2192 ${this.endTarget}`;

    if (this.overlayFirstTargetNum) this.overlayFirstTargetNum.textContent = this.startTarget;
    if (this.overlaySequenceText) {
      this.overlaySequenceText.textContent = `Sequence: ${this.startTarget} to ${this.endTarget} (${this.targetCount} targets total)`;
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

    // Reset submission guard for the newly starting test
    this.hasSubmitted = false;

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

    // Fresh layout for this run
    this._setupLayout();

    // Start timing
    this.startPerfTime = window.performance.now();
    this.lastTargetPerfTime = this.startPerfTime;
    this.startIsoTime = new Date().toISOString();

    // Hide overlay
    this.overlay.classList.add("hidden");
    this.startBtn.disabled = true;
    this.cancelBtn.disabled = false;

    // Start HUD stopwatch
    if (this.hudInterval) clearInterval(this.hudInterval);
    this.hudInterval = setInterval(() => this._updateHUDTimers(), 40);

    this._updateHUD();
    this.draw();
  }

  resetTest() {
    this.isStarted = false;
    this.isCompleted = false;
    this.hasSubmitted = false;
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
    this.cancelBtn.disabled = true;

    this.hudStepTimerEl.textContent = "0.00s";
    this.hudTotalTimerEl.textContent = "0.00s";
    this.hudErrorsEl.textContent = "0";

    const nextT = this.targetList && this.targetList.length > 0 ? this.targetList[0] : "-";
    this.hudNextTargetEl.textContent = nextT;

    this._updateTargetRangeIndicators();
    this.draw();
  }

  _updateHUDTimers() {
    if (!this.isStarted || this.isCompleted) return;
    const now = window.performance.now();
    const stepElapsedSec = (now - this.lastTargetPerfTime) / 1000.0;
    const totalElapsedSec = (now - this.startPerfTime) / 1000.0;

    this.hudStepTimerEl.textContent = `${stepElapsedSec.toFixed(2)}s`;
    this.hudTotalTimerEl.textContent = `${totalElapsedSec.toFixed(2)}s`;
  }

  _updateHUD() {
    if (this.currentStepIndex < this.targetList.length) {
      this.hudNextTargetEl.textContent = this.targetList[this.currentStepIndex];
    } else {
      this.hudNextTargetEl.textContent = "DONE";
    }
    this.hudErrorsEl.textContent = String(this.totalErrors);
  }

  _handleCanvasClick(event) {
    if (!this.isStarted || this.isCompleted) return;

    const rect = this.canvas.getBoundingClientRect();
    const clickX = event.clientX - rect.left;
    const clickY = event.clientY - rect.top;

    // Check hit against target nodes
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

      // Audio feedback
      if (window.soundManager) {
        window.soundManager.playCorrectBeep();
      }

      this.currentStepIndex++;
      this.currentStepErrors = 0;
      this.lastTargetPerfTime = now;

      // Mode-specific Layout Reshuffling:
      // Mode 1 & 2: Static (no reshuffle)
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

      // Check if round is finished
      if (this.currentStepIndex >= this.targetList.length) {
        this._finishRound(now);
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

  async _finishRound(finishPerfTime) {
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

    // 1. Advance queue and round counter immediately if in formal experiment
    if (this.phase === "EXPERIMENT") {
      if (this.experimentQueue.length > 0) {
        this.experimentQueue.shift();
      }
      this.completedExperimentRounds++;
      this.modeQuotas[this.activeMode] = (this.modeQuotas[this.activeMode] || 0) + 1;
      this._saveLocalState();
      this._updateProtocolUI();
    }

    // 2. Submit results to server
    await this.submitResults();

    // 3. Show round results modal
    setTimeout(() => {
      this._openResultsModal(totalDurationMs);
    }, 350);
  }

  draw() {
    const w = this.displayWidth;
    const h = this.displayHeight;
    this.ctx.clearRect(0, 0, w, h);

    if (!this.targetList || this.targetList.length === 0) return;

    // Draw dark background grid pattern
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

    // 1. Draw Trail Lines (Modes 1 and 3)
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

  _openResultsModal(totalDurationMs) {
    const badgeEl = document.getElementById("modalRoundBadge");
    const modeTitleEl = document.getElementById("modalModeTitle");
    const totalTimeEl = document.getElementById("modalTotalTime");
    const meanTimeEl = document.getElementById("modalMeanTime");
    const errorsEl = document.getElementById("modalErrors");
    const anonIdEl = document.getElementById("modalAnonIdVal");

    if (badgeEl) {
      badgeEl.textContent =
        this.phase === "PRACTICE"
          ? `Practice Trial ${this.practiceIndex + 1} of 4 Complete`
          : `Formal Experiment: Round ${this.completedExperimentRounds} of 16 Complete`;
    }

    const spec = this.modeSpecs ? this.modeSpecs[this.activeMode] : null;
    if (modeTitleEl) modeTitleEl.textContent = spec ? spec.title : `Mode ${this.activeMode}`;
    if (totalTimeEl) totalTimeEl.textContent = `${(totalDurationMs / 1000.0).toFixed(2)}s`;

    const meanMs =
      this.stepTimesMs.length > 0
        ? this.stepTimesMs.reduce((a, b) => a + b, 0) / this.stepTimesMs.length
        : 0;
    if (meanTimeEl) meanTimeEl.textContent = `${meanMs.toFixed(1)} ms`;
    if (errorsEl) errorsEl.textContent = String(this.totalErrors);
    if (anonIdEl) anonIdEl.textContent = this.anonymousId;

    // Steps table
    const tbody = document.getElementById("modalStepsTbody");
    if (tbody) {
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
    }

    // Next run button text
    if (this.nextRunBtn) {
      this.nextRunBtn.disabled = false;
      if (this.phase === "PRACTICE") {
        if (this.practiceIndex + 1 < 4) {
          this.nextRunBtn.textContent = `Proceed to Practice Trial ${this.practiceIndex + 2} \u2192`;
        } else {
          this.nextRunBtn.textContent = "Finish Practice & Enter Formal Experiment \u2192";
        }
      } else {
        if (this.completedExperimentRounds < this.totalExperimentRounds) {
          this.nextRunBtn.textContent = `Proceed to Round ${this.completedExperimentRounds + 1} of 16 \u2192`;
        } else {
          this.nextRunBtn.textContent = "View Final Experiment Summary & Download ZIP \u2192";
        }
      }
    }

    this._renderModalMiniChart();
    this.resultsModal.classList.add("open");
  }

  _closeModal() {
    this.resultsModal.classList.remove("open");
  }

  async _advanceToNextRound() {
    this.hasSubmitted = false;

    if (this.phase === "PRACTICE") {
      this.practiceIndex++;
      if (this.practiceIndex < 4) {
        this._saveLocalState();
        const nextMode = this.practiceSequence[this.practiceIndex];
        this._showTutorialModal(nextMode, this.practiceIndex + 1);
        await this._prepareCurrentRound();
      } else {
        // All 4 practice trials done!
        this.phase = "PRACTICE_COMPLETE";
        this._saveLocalState();
        this.practiceCompleteModal.classList.add("open");
      }
    } else if (this.phase === "EXPERIMENT") {
      if (this.completedExperimentRounds < this.totalExperimentRounds) {
        this._saveLocalState();
        await this._prepareCurrentRound();
      } else {
        this.phase = "COMPLETED";
        this._saveLocalState();
        this._openExperimentCompleteModal();
      }
    }
  }

  async submitResults() {
    if (this.hasSubmitted) return true;
    if (!this.stepTimesMs || this.stepTimesMs.length === 0) return false;

    // Use current completed experiment count as round_number
    const roundNum = this.phase === "EXPERIMENT" ? this.completedExperimentRounds : null;
    const trialIdx = this.phase === "PRACTICE" ? this.practiceIndex + 1 : null;

    const payload = {
      session_id: this.sessionId,
      is_practice: this.phase === "PRACTICE",
      trial_index: trialIdx,
      round_number: roundNum,
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

    this.hasSubmitted = true;
    this.sessionResults.push(payload);
    this._saveLocalState();

    try {
      const res = await fetch("/api/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (data.status === "success") {
        const saveStatusEl = document.getElementById("modalSaveStatus");
        if (saveStatusEl) {
          saveStatusEl.style.display = "inline-flex";
        }
        return true;
      } else {
        console.warn("Submit notice:", data.message);
        return false;
      }
    } catch (err) {
      console.warn("Submit network error, stored locally in session:", err);
      return true;
    }
  }

  _openExperimentCompleteModal() {
    // Populate mode breakdown table
    const tbody = document.getElementById("completionTableBody");
    if (tbody) {
      tbody.innerHTML = "";
      for (let m = 1; m <= 4; m++) {
        const spec = this.modeSpecs ? this.modeSpecs[m] : null;
        const modeRuns = this.sessionResults.filter((r) => !r.is_practice && r.mode === m);
        const lats = modeRuns.flatMap((r) => r.step_times_ms || []);
        const avgLat = lats.length > 0 ? (lats.reduce((a, b) => a + b, 0) / lats.length).toFixed(1) : "--";
        const totalErr = modeRuns.reduce((a, b) => a + (b.total_errors || 0), 0);

        // Slope calculation
        let slopeStr = "--";
        if (modeRuns.length > 0) {
          const allSteps = modeRuns.map((r) => r.step_times_ms).filter((s) => Array.isArray(s) && s.length > 0);
          if (allSteps.length > 0) {
            const minLen = Math.min(...allSteps.map((s) => s.length));
            if (minLen >= 2) {
              const avgPerStep = [];
              for (let i = 0; i < minLen; i++) {
                avgPerStep.push(allSteps.reduce((sum, s) => sum + s[i], 0) / allSteps.length);
              }
              const xs = Array.from({ length: minLen }, (_, i) => i + 1);
              const n = minLen;
              const sx = xs.reduce((a, b) => a + b, 0);
              const sy = avgPerStep.reduce((a, b) => a + b, 0);
              const sxx = xs.reduce((a, b) => a + b * b, 0);
              const sxy = xs.reduce((a, b, i) => a + b * avgPerStep[i], 0);
              const denom = n * sxx - sx * sx;
              const slope = denom !== 0 ? (n * sxy - sx * sy) / denom : 0;
              slopeStr = `${slope > 0 ? "+" : ""}${slope.toFixed(1)} ms/tgt`;
            }
          }
        }

        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><strong>Mode ${m}: ${spec ? spec.short_name : `Mode ${m}`}</strong></td>
          <td><span style="color:#4ade80; font-weight:700;">${modeRuns.length} / 4 Runs ✓</span></td>
          <td>${avgLat} ms</td>
          <td style="font-family:var(--font-mono); font-weight:700; color:#38bdf8;">${slopeStr}</td>
          <td>${totalErr}</td>
        `;
        tbody.appendChild(tr);
      }
    }

    this.experimentCompleteModal.classList.add("open");
  }

  _downloadResultsZip() {
    const url = `/api/export_session_zip?session_id=${encodeURIComponent(this.sessionId)}`;
    const a = document.createElement("a");
    a.href = url;
    a.download = `spatial_memory_experiment_${this.sessionId}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    const statusEl = document.getElementById("downloadStatusText");
    if (statusEl) {
      statusEl.textContent = "✓ ZIP File Downloaded! Please send to your researcher.";
      statusEl.className = "download-status-done";
    }

    this._showToast("ZIP archive downloaded successfully!", "success");
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
