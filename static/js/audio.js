/**
 * audio.js
 * Native Web Audio API sound generator for TMT-A Spatial Memory Experiment.
 * Provides latency-free, zero-asset audio feedback for correct target selections,
 * error blips, and completion fanfares.
 */

class WebAudioManager {
  constructor() {
    this.ctx = null;
    this.isMuted = false;
  }

  _initContext() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        this.ctx = new AudioCtx();
      }
    }
    if (this.ctx && this.ctx.state === "suspended") {
      this.ctx.resume();
    }
  }

  playTone(frequency, durationMs, type = "sine", volume = 0.18) {
    if (this.isMuted) return;
    try {
      this._initContext();
      if (!this.ctx) return;

      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      osc.type = type;
      osc.frequency.setValueAtTime(frequency, this.ctx.currentTime);

      // Smooth attack and release to avoid clicks
      const now = this.ctx.currentTime;
      const durationSec = durationMs / 1000.0;
      gain.gain.setValueAtTime(0.001, now);
      gain.gain.exponentialRampToValueAtTime(volume, now + 0.008);
      gain.gain.exponentialRampToValueAtTime(0.001, now + durationSec);

      osc.connect(gain);
      gain.connect(this.ctx.destination);

      osc.start(now);
      osc.stop(now + durationSec + 0.02);
    } catch (e) {
      console.warn("Audio playback warning:", e);
    }
  }

  playCorrectBeep() {
    // 1150 Hz confirmation beep (standard for unlit modes)
    this.playTone(1150, 70, "sine", 0.18);
  }

  playErrorTone() {
    // 380 Hz subtle error blip
    this.playTone(380, 85, "triangle", 0.22);
  }

  playFinishFanfare() {
    // Ascending 4-tone completion fanfare
    const freqs = [660, 880, 1175, 1568];
    freqs.forEach((f, idx) => {
      setTimeout(() => {
        this.playTone(f, 85, "sine", 0.22);
      }, idx * 75);
    });
  }
}

// Global singleton instance
window.soundManager = new WebAudioManager();

