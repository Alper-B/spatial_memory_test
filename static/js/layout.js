/**
 * layout.js
 * Client-side Spatial Layout Manager for TMT-A Spatial Memory Experiment.
 * Implements the fully random "sprinkled on the floor" algorithm with collision avoidance.
 * All coordinates are normalized in percentage [0, 100] for responsive canvas scaling.
 */

class WebSpatialLayoutManager {
  static computeDefaultSpacing(count) {
    const c = Math.max(1, count);
    return Math.max(4.0, Math.min(7.5, 36.0 / Math.sqrt(c)));
  }

  static placeSprinkledPositions(count, existingPositions = [], minSpacing = null, margin = 7.0) {
    const totalCount = existingPositions.length + count;
    const spacing = minSpacing !== null ? minSpacing : this.computeDefaultSpacing(totalCount);
    const floorSpacing = Math.max(3.8, spacing * 0.75);

    const newPositions = [];
    const maxAttempts = 3500;

    for (let i = 0; i < count; i++) {
      let placed = false;
      let curSpacing = spacing;

      for (let attempt = 0; attempt < maxAttempts; attempt++) {
        if (attempt > 1200) {
          curSpacing = Math.max(floorSpacing, curSpacing * 0.99);
        }

        const x = margin + Math.random() * (100.0 - 2 * margin);
        const y = margin + Math.random() * (100.0 - 2 * margin);

        // Keep top-left corner clear so targets never hide behind the "First Target" corner badge
        if (x < 19.0 && y < 21.0) {
          continue;
        }

        const collidesExisting = existingPositions.some(
          ([ex, ey]) => Math.hypot(x - ex, y - ey) < curSpacing
        );
        const collidesNew = newPositions.some(
          ([nx, ny]) => Math.hypot(x - nx, y - ny) < curSpacing
        );

        if (!collidesExisting && !collidesNew) {
          newPositions.push([parseFloat(x.toFixed(2)), parseFloat(y.toFixed(2))]);
          placed = true;
          break;
        }
      }

      if (!placed) {
        // Fallback clamping
        const fallbackX = margin + Math.random() * (100.0 - 2 * margin);
        const fallbackY = margin + Math.random() * (100.0 - 2 * margin);
        newPositions.push([parseFloat(fallbackX.toFixed(2)), parseFloat(fallbackY.toFixed(2))]);
      }
    }

    return newPositions;
  }

  static generateInitialLayout(targets, minSpacing = null, margin = 7.0) {
    const positions = this.placeSprinkledPositions(targets.length, [], minSpacing, margin);

    // Shuffle positions to decouple sequence index from spatial location (zero proximity correlation)
    const shuffledPositions = [...positions];
    for (let i = shuffledPositions.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [shuffledPositions[i], shuffledPositions[j]] = [shuffledPositions[j], shuffledPositions[i]];
    }

    const layout = {};
    targets.forEach((t, idx) => {
      layout[String(t)] = shuffledPositions[idx];
    });

    return layout;
  }

  static shuffleUncompletedTargets(layout, completedTargets, uncompletedTargets, margin = 7.0) {
    const newLayout = {};
    const fixedPositions = [];

    // Lock completed targets in place
    completedTargets.forEach((t) => {
      const strT = String(t);
      if (layout[strT]) {
        newLayout[strT] = layout[strT];
        fixedPositions.push(layout[strT]);
      }
    });

    // Generate fresh non-overlapping positions for remaining targets
    const newPositions = this.placeSprinkledPositions(
      uncompletedTargets.length,
      fixedPositions,
      null,
      margin
    );

    // Randomize assignment to uncompleted targets
    for (let i = newPositions.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [newPositions[i], newPositions[j]] = [newPositions[j], newPositions[i]];
    }

    uncompletedTargets.forEach((t, idx) => {
      newLayout[String(t)] = newPositions[idx];
    });

    return newLayout;
  }

  static shuffleAllTargets(targets, margin = 7.0) {
    return this.generateInitialLayout(targets, null, margin);
  }
}

window.WebSpatialLayoutManager = WebSpatialLayoutManager;

