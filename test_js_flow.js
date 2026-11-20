/**
 * test_js_flow.js
 * Headless verification of TMTSpatialMemoryApp round progression,
 * queue advancement, cancellation, and completion in Node.js.
 */

// Mock minimal DOM and browser globals
const mockElements = {};
function getOrCreateMockEl(id) {
  if (!mockElements[id]) {
    mockElements[id] = {
      id,
      textContent: "",
      innerHTML: "",
      style: {},
      classList: {
        classes: new Set(),
        add(c) { this.classes.add(c); },
        remove(c) { this.classes.delete(c); },
        toggle(c, v) { if (v) this.classes.add(c); else this.classes.delete(c); },
        contains(c) { return this.classes.has(c); }
      },
      disabled: false,
      appendChild(c) { if (!this.children) this.children = []; this.children.push(c); },
      addEventListener(evt, fn) { this[`on_${evt}`] = fn; },
      click() { if (this.on_click) this.on_click(); },
      parentElement: {
        clientWidth: 800,
        clientHeight: 600,
        getBoundingClientRect: () => ({ width: 800, height: 600, left: 0, top: 0 })
      },
      getContext: () => ({
        resetTransform: () => {},
        scale: () => {},
        clearRect: () => {},
        beginPath: () => {},
        moveTo: () => {},
        lineTo: () => {},
        stroke: () => {},
        arc: () => {},
        fill: () => {},
        fillText: () => {},
        setLineDash: () => {},
      })
    };
  }
  return mockElements[id];
}

global.document = {
  getElementById: (id) => getOrCreateMockEl(id),
  querySelectorAll: () => [],
  createElement: (tag) => ({
    tagName: tag,
    style: {},
    classList: { add() {}, remove() {} },
    appendChild() {},
    innerHTML: ""
  }),
  body: { appendChild() {}, removeChild() {} },
  addEventListener: () => {}
};

global.window = {
  addEventListener: () => {},
  performance: { now: () => Date.now() },
  devicePixelRatio: 1,
  soundManager: {
    _initContext: () => {},
    playCorrectBeep: () => {},
    playErrorTone: () => {},
    playFinishFanfare: () => {}
  }
};

global.localStorage = {
  data: {},
  getItem(k) { return this.data[k] || null; },
  setItem(k, v) { this.data[k] = String(v); },
  removeItem(k) { delete this.data[k]; }
};

global.fetch = async (url, opts) => {
  if (url === "/api/config") {
    return {
      json: async () => ({
        status: "success",
        anonymous_id: "Anon-TEST1234",
        config: {},
        modes: {
          1: { title: "Mode 1", short_name: "Normal" },
          2: { title: "Mode 2", short_name: "Memory" },
          3: { title: "Mode 3", short_name: "Visual" },
          4: { title: "Mode 4", short_name: "Baseline" }
        }
      })
    };
  }
  if (url === "/api/session/start") {
    return {
      json: async () => ({
        status: "success",
        session_id: "session_mock_123",
        experiment_queue: [1, 2, 3, 4, 1, 2, 3, 4, 1, 2, 3, 4, 1, 2, 3, 4]
      })
    };
  }
  if (url === "/api/new_target_range") {
    return {
      json: async () => ({
        status: "success",
        start_target: 10,
        end_target: 19,
        target_count: 10,
        targets: ["10", "11", "12", "13", "14", "15", "16", "17", "18", "19"]
      })
    };
  }
  if (url === "/api/submit") {
    return {
      json: async () => ({
        status: "success",
        filename: "test.json"
      })
    };
  }
  return { json: async () => ({ status: "success" }) };
};

// Mock WebSpatialLayoutManager
global.WebSpatialLayoutManager = {
  generateInitialLayout: (targets) => {
    const l = {};
    targets.forEach((t, i) => { l[t] = [10 + i * 8, 20 + i * 5]; });
    return l;
  },
  shuffleUncompletedTargets: (layout) => layout,
  shuffleAllTargets: (targets) => {
    const l = {};
    targets.forEach((t, i) => { l[t] = [15 + i * 7, 25 + i * 6]; });
    return l;
  }
};

// Load app.js code by reading file and executing in scope
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const appCode = fs.readFileSync(path.join(__dirname, "static", "js", "app.js"), "utf-8");

vm.runInThisContext(appCode);

async function runTests() {
  console.log("Starting JS State Machine Simulation...");
  const app = new TMTSpatialMemoryApp();
  await app.init();

  if (app.phase !== "PRACTICE") throw new Error("Expected initial phase to be PRACTICE");
  if (app.practiceIndex !== 0) throw new Error("Expected practiceIndex 0");
  console.log("✓ Initialized in PRACTICE phase, trial 1 of 4");

  // Complete 4 practice trials
  for (let t = 0; t < 4; t++) {
    app.startTest();
    app.currentStepIndex = 10;
    app.stepTimesMs = [500, 500, 500, 500, 500, 500, 500, 500, 500, 500];
    await app._finishRound(Date.now());
    await app._advanceToNextRound();
  }

  if (app.phase !== "PRACTICE_COMPLETE") {
    throw new Error(`Expected phase PRACTICE_COMPLETE after 4 trials, got ${app.phase}`);
  }
  console.log("✓ Successfully completed all 4 practice trials and reached PRACTICE_COMPLETE");

  // Transition to formal experiment
  mockElements["beginExperimentBtn"].click();
  if (app.phase !== "EXPERIMENT") {
    throw new Error(`Expected phase EXPERIMENT, got ${app.phase}`);
  }
  if (app.completedExperimentRounds !== 0) {
    throw new Error(`Expected 0 completed rounds initially, got ${app.completedExperimentRounds}`);
  }
  console.log("✓ Entered EXPERIMENT phase at Round 1 of 16");

  // --- ROUND 1 OF 16 ---
  const firstMode = app.activeMode;
  app.startTest();
  app.currentStepIndex = 10;
  app.stepTimesMs = [600, 600, 600, 600, 600, 600, 600, 600, 600, 600];
  await app._finishRound(Date.now());

  // Verify that Round 1 is marked complete and completedExperimentRounds advanced!
  if (app.completedExperimentRounds !== 1) {
    throw new Error(`STUCK ON LOOP! completedExperimentRounds is ${app.completedExperimentRounds}, expected 1`);
  }
  if (app.modeQuotas[firstMode] !== 1) {
    throw new Error(`Expected mode quota 1 for mode ${firstMode}, got ${app.modeQuotas[firstMode]}`);
  }
  console.log("✓ Round 1 finished: completedExperimentRounds is now 1 (NO LOOP!)");

  // Advance to Round 2
  await app._advanceToNextRound();
  if (app.completedExperimentRounds !== 1) {
    throw new Error(`completedExperimentRounds should remain 1 preparing round 2, got ${app.completedExperimentRounds}`);
  }
  console.log(`✓ Advanced to Round 2 of 16 (Mode ${app.activeMode})`);

  // --- ROUND 2: TEST CANCELLATION ---
  const modeBeforeCancel = app.activeMode;
  const queueLenBeforeCancel = app.experimentQueue.length;
  app.startTest();
  app._confirmCancelRound(); // Cancel round 2

  if (app.completedExperimentRounds !== 1) {
    throw new Error(`Cancellation should NOT increment completed rounds! Got ${app.completedExperimentRounds}`);
  }
  if (app.experimentQueue[app.experimentQueue.length - 1] !== modeBeforeCancel) {
    throw new Error("Cancelled mode was not pushed to back of queue!");
  }
  console.log(`✓ Cancellation verified: Mode ${modeBeforeCancel} re-queued, completed rounds stayed at 1`);

  // Now finish all remaining rounds (from 1 to 16)
  while (app.completedExperimentRounds < 16) {
    const curRound = app.completedExperimentRounds + 1;
    app.startTest();
    app.currentStepIndex = 10;
    app.stepTimesMs = [550, 550, 550, 550, 550, 550, 550, 550, 550, 550];
    await app._finishRound(Date.now());

    if (app.completedExperimentRounds !== curRound) {
      throw new Error(`Expected completed rounds ${curRound}, got ${app.completedExperimentRounds}`);
    }
    await app._advanceToNextRound();
  }

  if (app.phase !== "COMPLETED") {
    throw new Error(`Expected phase COMPLETED after 16 rounds, got ${app.phase}`);
  }
  if (app.completedExperimentRounds !== 16) {
    throw new Error(`Expected 16 completed rounds, got ${app.completedExperimentRounds}`);
  }

  for (let m = 1; m <= 4; m++) {
    if (app.modeQuotas[m] !== 4) {
      throw new Error(`Mode ${m} quota expected 4, got ${app.modeQuotas[m]}`);
    }
  }

  console.log("✓ All 16 rounds completed sequentially! Mode quotas strictly 4/4 each.");
  console.log("✓ ALL JS PROTOCOL SIMULATION TESTS PASSED PERFECTLY!");
}

runTests().catch((err) => {
  console.error("TEST FAILED:", err);
  process.exit(1);
});
