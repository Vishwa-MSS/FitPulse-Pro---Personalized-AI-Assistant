/**
 * workout_game.js — FitPulse Workout Game  v4
 * =============================================
 * Reference: main.py GestureButton + FallingGame + WorkoutScreen pattern
 *
 * ARCHITECTURE (mirrors main.py exactly, translated to browser canvas):
 *  - GestureButton class: index-finger hover fills progress arc → fires click
 *  - Exercise-specific games: each workout type has its own themed mini-game
 *  - Split screen: LEFT = Flappy/themed game, RIGHT = live pose detection mirror
 *  - Rep detection polls window.repCounter (set by script.js)
 *
 * EXERCISE GAMES:
 *   bicep_curl    → CATCH GAME: wrist circles catch falling dumbbells
 *   lateral_raise → FLAPPY BIRD: arms control bird height through pipes
 *   squat         → SQUAT JUMP: character jumps over obstacles with squat reps
 *   shoulder_press→ SPACE SHOOTER: press up = shoot, rep = fire bullet
 *   pushup        → PLATFORM PUSH: pushup powers character across platforms
 *   deadlift      → LIFT METER: deadlift fills power meter to break barriers
 *   DEFAULT       → CATCH GAME fallback
 *
 * GESTURE CONTROL (from main.py GestureButton pattern):
 *   Index finger UP → point cursor at on-screen buttons
 *   Hover over button for 0.6s → fires click (progress arc fills)
 *   Works on: Stop Workout, Reset Counter, Switch Exercise buttons
 */

(function () {
  'use strict';

  // ══════════════════════════════════════════════════════════
  //  CONSTANTS
  // ══════════════════════════════════════════════════════════
  const GW = 420;   // game panel width px
  const GH = 520;   // game panel height px

  // ══════════════════════════════════════════════════════════
  //  GESTURE BUTTON (mirrors main.py GestureButton exactly)
  //  Hover with index finger → progress arc → fires
  // ══════════════════════════════════════════════════════════
  class GestureButton {
    constructor(x, y, w, h, label, color = '#3b5fe2', textColor = '#fff') {
      this.x = x; this.y = y; this.w = w; this.h = h;
      this.label = label; this.color = color; this.textColor = textColor;
      this.hoverFrames = 0;
      this.hoverThreshold = 28;  // ~0.9s at 30fps — same as main.py 18 frames at 30fps
      this.highlight = 0;
      this.triggered = false;
    }

    contains(px, py) {
      return px >= this.x && px <= this.x + this.w &&
        py >= this.y && py <= this.y + this.h;
    }

    // fingertip: {x, y} normalised 0..1 or null
    // canvasW/H: size of canvas element on screen
    updateHover(fingertip, canvasW, canvasH) {
      if (!fingertip) { this.hoverFrames = Math.max(0, this.hoverFrames - 1); this.highlight *= 0.9; return false; }
      // Map normalised fingertip to canvas px
      const px = (1 - fingertip.x) * canvasW;  // mirror X
      const py = fingertip.y * canvasH;
      if (this.contains(px, py)) {
        this.hoverFrames++;
        this.highlight = Math.min(1, this.hoverFrames / this.hoverThreshold);
        if (this.hoverFrames >= this.hoverThreshold) {
          this.hoverFrames = 0;
          return true;  // FIRED
        }
      } else {
        this.hoverFrames = Math.max(0, this.hoverFrames - 1);
        this.highlight = Math.max(0, this.highlight - 0.05);
      }
      return false;
    }

    draw(ctx) {
      const { x, y, w, h, label, color, textColor, hoverFrames, hoverThreshold, highlight } = this;

      // Background — brighten on hover
      ctx.save();
      const r = 8;
      ctx.beginPath();
      ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y);
      ctx.arcTo(x + w, y, x + w, y + r, r);
      ctx.lineTo(x + w, y + h - r); ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
      ctx.lineTo(x + r, y + h); ctx.arcTo(x, y + h, x, y + h - r, r);
      ctx.lineTo(x, y + r); ctx.arcTo(x, y, x + r, y, r);
      ctx.closePath();

      // Parse hex color and brighten
      let col = color;
      if (highlight > 0) {
        ctx.shadowColor = color;
        ctx.shadowBlur = 12 * highlight;
      }
      ctx.fillStyle = col;
      ctx.globalAlpha = 0.85 + 0.15 * highlight;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.shadowBlur = 0;

      // Border
      ctx.strokeStyle = `rgba(255,255,255,${0.3 + 0.5 * highlight})`;
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Label
      ctx.fillStyle = textColor;
      ctx.font = `bold ${Math.round(11 + 1 * highlight)}px "Segoe UI",sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, x + w / 2, y + h / 2);

      // Progress arc (from main.py cv2.ellipse pattern)
      if (hoverFrames > 0) {
        const frac = hoverFrames / hoverThreshold;
        const cx = x + w / 2, cy = y + h / 2;
        const rr = Math.min(w, h) / 2 - 4;
        ctx.beginPath();
        ctx.arc(cx, cy, rr, -Math.PI / 2, -Math.PI / 2 + frac * Math.PI * 2);
        ctx.strokeStyle = '#00ffc8';
        ctx.lineWidth = 3;
        ctx.stroke();
      }

      ctx.restore();
    }
  }

  // ══════════════════════════════════════════════════════════
  //  EXERCISE-SPECIFIC GAME ENGINES
  // ══════════════════════════════════════════════════════════

  // ── CATCH GAME (Bicep Curl / default) ─────────────────────
  // Falling dumbbells — wrists are the catchers (from main.py FallingGame)
  class CatchGame {
    constructor() {
      this.objects = [];
      this.score = 0;
      this.missed = 0;
      this.spawnTimer = 0;
      this.spawnInterval = 55;
      this.catcherPoints = [];  // wrist positions from pose
    }

    spawn() {
      const types = ['dumbbell', 'star', 'coin'];
      const colors = ['#00c8ff', '#ffd700', '#00ff9c'];
      const t = Math.floor(Math.random() * types.length);
      this.objects.push({
        x: 40 + Math.random() * (GW - 80),
        y: -20,
        type: types[t],
        color: colors[t],
        speed: 2.5 + Math.random() * 3.5 + this.score * 0.02,
        caught: false,
      });
    }

    update(repEvent) {
      if (repEvent) { this.spawn(); this.spawn(); }
      this.spawnTimer++;
      this.spawnInterval = Math.max(18, 55 - Math.floor(this.score / 4));
      if (this.spawnTimer >= this.spawnInterval) { this.spawn(); this.spawnTimer = 0; }

      const alive = [];
      for (const o of this.objects) {
        o.y += o.speed;
        let caught = false;
        for (const cp of this.catcherPoints) {
          if (!cp) continue;
          const dx = o.x - cp.x, dy = o.y - cp.y;
          if (Math.sqrt(dx * dx + dy * dy) < 38) { this.score++; caught = true; break; }
        }
        if (o.y > GH - 35 && !caught) { this.missed++; }
        else if (!caught) alive.push(o);
      }
      this.objects = alive;
    }

    draw(ctx) {
      // Sky gradient
      const sky = ctx.createLinearGradient(0, 0, 0, GH);
      sky.addColorStop(0, '#0a1628'); sky.addColorStop(1, '#1a2a4a');
      ctx.fillStyle = sky; ctx.fillRect(0, 0, GW, GH);

      // Ground
      ctx.fillStyle = '#1a4a1a'; ctx.fillRect(0, GH - 35, GW, 35);
      ctx.fillStyle = '#2a6a2a'; ctx.fillRect(0, GH - 35, GW, 6);

      // Objects
      for (const o of this.objects) this._drawObj(ctx, o);

      // Catchers
      for (const cp of this.catcherPoints) {
        if (!cp) continue;
        ctx.beginPath(); ctx.arc(cp.x, cp.y, 32, 0, Math.PI * 2);
        ctx.strokeStyle = '#ffd700'; ctx.lineWidth = 2; ctx.stroke();
        ctx.beginPath(); ctx.arc(cp.x, cp.y, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#ffd700'; ctx.fill();
      }

      // HUD
      ctx.fillStyle = 'rgba(0,0,0,0.7)'; ctx.fillRect(0, 0, GW, 44);
      ctx.fillStyle = '#00ff9c'; ctx.font = 'bold 18px monospace';
      ctx.textAlign = 'left'; ctx.fillText(`SCORE: ${this.score}`, 12, 28);
      ctx.fillStyle = '#ff6b6b'; ctx.textAlign = 'right';
      ctx.fillText(`MISSED: ${this.missed}`, GW - 12, 28);

      // Tip
      ctx.fillStyle = 'rgba(0,0,0,0.5)'; ctx.fillRect(0, GH - 35, GW, 35);
      ctx.fillStyle = '#94a3b8'; ctx.font = '11px "Segoe UI",sans-serif';
      ctx.textAlign = 'center'; ctx.fillText('Catch dumbbells with your wrists!', GW / 2, GH - 14);
    }

    _drawObj(ctx, o) {
      const { x, y, color, type } = o;
      ctx.save(); ctx.fillStyle = color; ctx.strokeStyle = '#fff';
      if (type === 'dumbbell') {
        ctx.lineWidth = 3;
        ctx.beginPath(); ctx.arc(x - 13, y, 9, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        ctx.beginPath(); ctx.arc(x + 13, y, 9, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        ctx.fillRect(x - 3, y - 4, 6, 8);
        ctx.strokeRect(x - 3, y - 4, 6, 8);
      } else if (type === 'star') {
        ctx.beginPath();
        for (let i = 0; i < 5; i++) {
          const a = (i * 4 * Math.PI / 5) - Math.PI / 2;
          const r = i % 2 === 0 ? 14 : 6;
          i === 0 ? ctx.moveTo(x + r * Math.cos(a), y + r * Math.sin(a))
            : ctx.lineTo(x + r * Math.cos(a), y + r * Math.sin(a));
        }
        ctx.closePath(); ctx.fill();
      } else {
        ctx.beginPath(); ctx.arc(x, y, 11, 0, Math.PI * 2);
        ctx.fill(); ctx.stroke();
        ctx.fillStyle = '#fff'; ctx.font = 'bold 11px monospace';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText('$', x, y);
      }
      ctx.restore();
    }

    reset() { this.objects = []; this.score = 0; this.missed = 0; this.spawnTimer = 0; }
  }

  // ── FLAPPY BIRD GAME (Lateral Raise) ──────────────────────
  // DIRECT ARM-TO-BIRD MAPPING (matches reference video):
  //   Arms raised to shoulder height → bird flies HIGH
  //   Arms down → bird falls LOW
  //   Bird Y position = 1:1 mapping of arm raise angle
  //   NO gravity/tap mechanic - pure positional control
  //
  // Uses window._lateralRaiseNorm (0=arms down, 1=arms at shoulder)
  // set by script.js analyzeLateralRaiseAccurate()
  class FlappyGame {
    constructor() {
      this.birdY = GH * 0.7;   // start lower
      this.targetY = GH * 0.7;
      this.pipes = [];
      this.score = 0;
      this.best = 0;
      try { this.best = parseInt(localStorage.getItem('fp_flappy_best') || '0'); } catch (e) { }
      this.dead = false;
      this.frame = 0;
      this.gndX = 0;
      this.cloudX = [80, 220, 360];
      this.cloudY = [60, 100, 80];
      // Grace period before pipes spawn (frames)
      this.gracePeriod = 90;
      // Speed increases with score
      this.pipeSpeed = 2.8;
      // Gap size (px between top/bottom pipe)
      this.gapH = 160;
      // Last norm value for display
      this.lastNorm = 0.5;
    }

    // armNorm: 0=arms down, 1=arms at shoulder height (from window._lateralRaiseNorm)
    // armAngle: raw angle in degrees (fallback if norm not available)
    update(armAngle, repEvent) {
      if (this.dead) return;
      this.frame++;
      this.gndX = (this.gndX - this.pipeSpeed) % 48;
      this.cloudX = this.cloudX.map((x, i) => (x - 0.5 - i * 0.15 + GW * 2) % (GW + 200) - 100);

      // ── CORE: Read normalised arm raise ──────────────────
      // Priority: window._lateralRaiseNorm (set by script.js) → fallback to angle
      let norm;
      if (typeof window._lateralRaiseNorm === 'number') {
        norm = window._lateralRaiseNorm;           // 0=down, 1=up — direct from pose
      } else {
        // Fallback: lateral raise angle range is ~10° (down) to ~90° (shoulder level)
        norm = Math.min(1, Math.max(0, (armAngle - 10) / 80));
      }
      this.lastNorm = norm;

      // Map: arms UP (norm=1) → bird HIGH on screen (small Y)
      //      arms DOWN (norm=0) → bird LOW on screen (large Y)
      const topMargin = 50, botMargin = 65;
      this.targetY = topMargin + (1 - norm) * (GH - topMargin - botMargin);

      // Smooth lerp so bird follows arm without jitter
      // Faster lerp = more responsive, matches real-time movement
      this.birdY += (this.targetY - this.birdY) * 0.18;

      // Spawn pipes (not during grace period)
      if (this.frame > this.gracePeriod && this.frame % 120 === 0) {
        const margin = 60;
        const minTop = margin;
        const maxTop = GH - 65 - this.gapH - margin;
        const topH = minTop + Math.random() * (maxTop - minTop);
        this.pipes.push({ x: GW, topH, botY: topH + this.gapH, passed: false });
        // Speed up slightly
        this.pipeSpeed = Math.min(5.5, 2.8 + this.score * 0.08);
        // Shrink gap slightly (harder over time, but keep minimum 120px)
        this.gapH = Math.max(120, 160 - this.score * 2);
      }

      // Move pipes
      for (let i = this.pipes.length - 1; i >= 0; i--) {
        this.pipes[i].x -= this.pipeSpeed;
        if (this.pipes[i].x + 58 < 0) { this.pipes.splice(i, 1); continue; }
        if (!this.pipes[i].passed && this.pipes[i].x + 58 < 80) {
          this.pipes[i].passed = true; this.score++;
          if (this.score > this.best) {
            this.best = this.score;
            try { localStorage.setItem('fp_flappy_best', this.best); } catch (e) { }
          }
        }
      }

      // Restart on rep event when dead
      if (repEvent && this.dead) { this.reset(); return; }

      // Collision (skip grace period)
      if (this.frame > this.gracePeriod + 10) {
        if (this.birdY < 18 || this.birdY > GH - 55) { this.dead = true; return; }
        const bL = 80 - 15, bR = 80 + 15, bT = this.birdY - 15, bB = this.birdY + 15;
        for (const p of this.pipes) {
          if (bR > p.x && bL < p.x + 58) {
            if (bT < p.topH || bB > p.botY) { this.dead = true; return; }
          }
        }
      }
    }

    draw(ctx, armAngle) {
      // Sky gradient - bright daytime like reference video
      const sky = ctx.createLinearGradient(0, 0, 0, GH);
      sky.addColorStop(0, '#5dc8f5'); sky.addColorStop(0.7, '#a8e6f0'); sky.addColorStop(1, '#c8f2a8');
      ctx.fillStyle = sky; ctx.fillRect(0, 0, GW, GH);

      // Clouds
      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      for (let i = 0; i < this.cloudX.length; i++) {
        const cx = this.cloudX[i], cy = this.cloudY[i];
        ctx.beginPath(); ctx.ellipse(cx, cy, 40, 18, 0, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.ellipse(cx + 28, cy + 5, 28, 14, 0, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.ellipse(cx - 24, cy + 6, 22, 12, 0, 0, Math.PI * 2); ctx.fill();
      }

      // Pipes
      for (const p of this.pipes) {
        this._drawPipe(ctx, p.x, 0, 58, p.topH, true);
        this._drawPipe(ctx, p.x, p.botY, 58, GH - 55 - p.botY, false);
        // Gap highlight line
        ctx.strokeStyle = 'rgba(255,255,100,0.3)'; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
        ctx.beginPath(); ctx.moveTo(p.x, p.topH); ctx.lineTo(p.x + 58, p.botY); ctx.stroke();
        ctx.setLineDash([]);
      }

      // Ground (scrolling)
      ctx.fillStyle = '#4a9e20'; ctx.fillRect(0, GH - 55, GW, 55);
      ctx.fillStyle = '#c8914a'; ctx.fillRect(0, GH - 38, GW, 38);
      ctx.fillStyle = '#5cb800';
      for (let gx = this.gndX; gx < GW + 48; gx += 48) ctx.fillRect(gx, GH - 55, 22, 8);

      // Bird
      this._drawBird(ctx, 80, this.birdY);

      // ── ARM RAISE INDICATOR (left side bar like reference video) ──
      const barX = 10, barY = 55, barW = 22, barH = GH - 120;
      ctx.fillStyle = 'rgba(0,0,0,0.4)'; ctx.fillRect(barX, barY, barW, barH);
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 1; ctx.strokeRect(barX, barY, barW, barH);
      // Fill from bottom (arms down=empty, arms up=full)
      const norm = this.lastNorm;
      const fillH = barH * norm;
      const barGrad = ctx.createLinearGradient(0, barY + barH, 0, barY);
      barGrad.addColorStop(0, '#ef4444'); barGrad.addColorStop(0.5, '#f59e0b'); barGrad.addColorStop(1, '#22c55e');
      ctx.fillStyle = barGrad; ctx.fillRect(barX, barY + barH - fillH, barW, fillH);
      // Labels
      ctx.fillStyle = '#fff'; ctx.font = 'bold 9px sans-serif'; ctx.textAlign = 'center';
      ctx.fillText('UP', barX + barW / 2, barY - 6);
      ctx.fillText('ARM', barX + barW / 2, barY + barH + 12);
      // Current level dot
      const dotY = barY + barH - fillH;
      ctx.beginPath(); ctx.arc(barX + barW / 2, dotY, 5, 0, Math.PI * 2);
      ctx.fillStyle = '#fff'; ctx.fill();
      ctx.strokeStyle = '#ffd700'; ctx.lineWidth = 2; ctx.stroke();

      // Bird target line (shows where bird is heading)
      if (!this.dead && this.frame > this.gracePeriod) {
        ctx.setLineDash([3, 5]);
        ctx.strokeStyle = 'rgba(255,215,0,0.4)'; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(80, this.birdY); ctx.lineTo(GW, this.birdY); ctx.stroke();
        ctx.setLineDash([]);
      }

      // HUD
      ctx.fillStyle = 'rgba(0,0,0,0.65)'; ctx.fillRect(0, 0, GW, 44);
      ctx.fillStyle = '#fbbf24'; ctx.font = 'bold 18px monospace'; ctx.textAlign = 'left';
      ctx.fillText(`SCORE: ${this.score}`, 40, 28);
      ctx.fillStyle = '#10b981'; ctx.textAlign = 'right';
      ctx.fillText(`BEST: ${this.best}`, GW - 12, 28);

      // Arm guide text
      if (!this.dead) {
        ctx.fillStyle = norm > 0.6 ? '#22c55e' : norm > 0.3 ? '#f59e0b' : '#ef4444';
        ctx.font = 'bold 11px "Segoe UI",sans-serif'; ctx.textAlign = 'center';
        const guide = norm > 0.7 ? '🙌 Arms up! Bird flies!' : norm < 0.25 ? '👐 Raise arms!' : '↕ Control the bird!';
        ctx.fillText(guide, GW / 2, 38);
      }

      // Grace period overlay
      if (this.frame <= this.gracePeriod && !this.dead) {
        ctx.fillStyle = 'rgba(0,0,0,0.55)'; ctx.fillRect(0, GH / 2 - 55, GW, 110);
        ctx.fillStyle = '#fff'; ctx.font = 'bold 20px "Segoe UI",sans-serif'; ctx.textAlign = 'center';
        ctx.fillText('🙌 Raise arms to fly!', GW / 2, GH / 2 - 12);
        ctx.fillStyle = '#fbbf24'; ctx.font = '13px "Segoe UI",sans-serif';
        ctx.fillText('Arms to shoulder = bird goes UP', GW / 2, GH / 2 + 18);
        ctx.fillStyle = '#94a3b8'; ctx.font = '11px sans-serif';
        ctx.fillText(`Starting in ${Math.max(0, Math.ceil((this.gracePeriod - this.frame) / 30))}s...`, GW / 2, GH / 2 + 42);
      }

      // Dead overlay
      if (this.dead) {
        ctx.fillStyle = 'rgba(0,0,0,0.65)'; ctx.fillRect(0, 0, GW, GH);
        ctx.fillStyle = '#fff'; ctx.font = 'bold 30px "Segoe UI",sans-serif'; ctx.textAlign = 'center';
        ctx.fillText('Game Over! 💥', GW / 2, GH / 2 - 50);
        ctx.fillStyle = '#fbbf24'; ctx.font = 'bold 18px sans-serif';
        ctx.fillText(`Score: ${this.score}   Best: ${this.best}`, GW / 2, GH / 2 - 12);
        ctx.fillStyle = '#94a3b8'; ctx.font = '14px sans-serif';
        ctx.fillText('Complete a Lateral Raise rep to restart!', GW / 2, GH / 2 + 30);
        ctx.fillStyle = '#22c55e'; ctx.font = 'bold 13px sans-serif';
        ctx.fillText('🙌 Raise arms → hold → lower → RESTART', GW / 2, GH / 2 + 58);
      }
    }

    _drawBird(ctx, bx, by) {
      ctx.save(); ctx.translate(bx, by);
      // Body
      const bg = ctx.createRadialGradient(-2, -3, 2, 0, 0, 15);
      bg.addColorStop(0, '#ffef80'); bg.addColorStop(1, '#f59e0b');
      ctx.fillStyle = bg; ctx.beginPath(); ctx.arc(0, 0, 15, 0, Math.PI * 2); ctx.fill();
      // Wing (flaps based on arm position)
      ctx.fillStyle = '#fbbf24';
      const wingY = 4 + Math.sin(this.frame * 0.25) * 5;
      ctx.beginPath(); ctx.ellipse(-3, wingY, 12, 6, -0.4, 0, Math.PI * 2); ctx.fill();
      // Eye
      ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(7, -5, 7, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#1e293b'; ctx.beginPath(); ctx.arc(9, -4, 4, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(10, -5, 1.5, 0, Math.PI * 2); ctx.fill();
      // Beak
      ctx.fillStyle = '#f97316';
      ctx.beginPath(); ctx.moveTo(14, 0); ctx.lineTo(22, -3); ctx.lineTo(22, 3); ctx.closePath(); ctx.fill();
      ctx.restore();
    }

    _drawPipe(ctx, x, y, w, h, isTop) {
      if (h <= 0) return;
      const g = ctx.createLinearGradient(x, 0, x + w, 0);
      g.addColorStop(0, '#2d6a00'); g.addColorStop(0.35, '#5cb800'); g.addColorStop(0.65, '#4aaa00'); g.addColorStop(1, '#2d6a00');
      ctx.fillStyle = g; ctx.fillRect(x, y, w, h);
      // Cap
      const capH = 24, ex = 8;
      ctx.fillStyle = '#5cb800';
      if (isTop) {
        ctx.fillRect(x - ex, y + h - capH, w + ex * 2, capH);
        ctx.fillStyle = '#7de000'; ctx.fillRect(x - ex, y + h - capH, w + ex * 2, 4);
      } else {
        ctx.fillRect(x - ex, y, w + ex * 2, capH);
        ctx.fillStyle = '#7de000'; ctx.fillRect(x - ex, y + capH - 4, w + ex * 2, 4);
      }
      // Shine
      ctx.fillStyle = 'rgba(255,255,255,0.15)'; ctx.fillRect(x + 4, y, 8, h);
    }

    reset() {
      this.pipes = []; this.score = 0; this.dead = false; this.frame = 0;
      this.birdY = GH * 0.6; this.targetY = GH * 0.6;
      this.pipeSpeed = 2.8; this.gapH = 160;
    }
  }

  // ── SQUAT JUMP GAME ────────────────────────────────────────
  // Character runs, user squats to jump over obstacles
  class SquatJumpGame {
    constructor() {
      this.charY = GH - 100;
      this.groundY = GH - 100;
      this.jumpVY = 0;
      this.isJumping = false;
      this.obstacles = [];
      this.score = 0;
      this.frame = 0;
      this.dead = false;
      this.spawnTimer = 0;
    }

    update(repEvent) {
      if (this.dead) return;
      this.frame++;

      // Rep = jump
      if (repEvent && !this.isJumping) {
        this.jumpVY = -14;
        this.isJumping = true;
      }

      // Physics
      this.charY += this.jumpVY;
      this.jumpVY += 0.7;
      if (this.charY >= this.groundY) { this.charY = this.groundY; this.jumpVY = 0; this.isJumping = false; }

      // Spawn obstacles
      this.spawnTimer++;
      const spawnInt = Math.max(70, 150 - this.score * 2);
      if (this.spawnTimer >= spawnInt) {
        const h = 30 + Math.random() * 40;
        this.obstacles.push({ x: GW, h, scored: false });
        this.spawnTimer = 0;
      }

      // Move obstacles
      const spd = 3 + this.score * 0.03;
      for (let i = this.obstacles.length - 1; i >= 0; i--) {
        this.obstacles[i].x -= spd;
        if (this.obstacles[i].x + 35 < 0) { this.obstacles.splice(i, 1); continue; }
        if (!this.obstacles[i].scored && this.obstacles[i].x + 35 < 90) {
          this.obstacles[i].scored = true; this.score++;
        }
        // Collision
        const o = this.obstacles[i];
        const oTop = GH - 55 - o.h;
        if (90 + 20 > o.x && 90 - 20 < o.x + 35 && this.charY + 20 > oTop) {
          this.dead = true;
        }
      }
    }

    draw(ctx, repEvent) {
      // Ground bg
      const sky = ctx.createLinearGradient(0, 0, 0, GH);
      sky.addColorStop(0, '#1a1a2e'); sky.addColorStop(1, '#16213e');
      ctx.fillStyle = sky; ctx.fillRect(0, 0, GW, GH);

      // Stars
      ctx.fillStyle = 'rgba(255,255,255,0.5)';
      for (let i = 0; i < 30; i++) {
        const sx = (i * 87 + this.frame * 0.3) % GW;
        const sy = (i * 53) % (GH - 100);
        ctx.fillRect(sx, sy, 2, 2);
      }

      // Ground
      ctx.fillStyle = '#1a4a1a'; ctx.fillRect(0, GH - 55, GW, 55);
      ctx.fillStyle = '#2a6a2a'; ctx.fillRect(0, GH - 55, GW, 8);

      // Obstacles (cactus-like)
      for (const o of this.obstacles) {
        const oTop = GH - 55 - o.h;
        ctx.fillStyle = '#e74c3c';
        ctx.fillRect(o.x, oTop, 35, o.h);
        ctx.fillStyle = '#c0392b';
        ctx.fillRect(o.x + 5, oTop - 15, 10, 15);
        ctx.fillRect(o.x + 20, oTop - 10, 10, 10);
      }

      // Character (stick figure runner)
      const cx = 90, cy = this.charY;
      ctx.strokeStyle = '#00ff88'; ctx.lineWidth = 3;
      // Body
      ctx.beginPath(); ctx.moveTo(cx, cy - 30); ctx.lineTo(cx, cy); ctx.stroke();
      // Head
      ctx.fillStyle = '#00ff88'; ctx.beginPath(); ctx.arc(cx, cy - 38, 10, 0, Math.PI * 2); ctx.fill();
      // Legs (animated)
      const legSwing = this.isJumping ? 0.4 : Math.sin(this.frame * 0.25) * 0.5;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.sin(legSwing) * 20, cy + 28);
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx - Math.sin(legSwing) * 20, cy + 28);
      ctx.stroke();
      // Arms
      ctx.beginPath();
      ctx.moveTo(cx, cy - 22);
      ctx.lineTo(cx + Math.cos(legSwing) * 20, cy - 10);
      ctx.moveTo(cx, cy - 22);
      ctx.lineTo(cx - Math.cos(legSwing) * 20, cy - 10);
      ctx.stroke();

      // HUD
      ctx.fillStyle = 'rgba(0,0,0,0.65)'; ctx.fillRect(0, 0, GW, 44);
      ctx.fillStyle = '#00ff88'; ctx.font = 'bold 18px monospace'; ctx.textAlign = 'left';
      ctx.fillText(`SCORE: ${this.score}`, 12, 28);
      ctx.fillStyle = '#fbbf24'; ctx.textAlign = 'right';
      ctx.fillText('SQUAT TO JUMP!', GW - 12, 28);

      if (this.dead) {
        ctx.fillStyle = 'rgba(0,0,0,0.65)'; ctx.fillRect(0, 0, GW, GH);
        ctx.fillStyle = '#fff'; ctx.font = 'bold 28px "Segoe UI",sans-serif'; ctx.textAlign = 'center';
        ctx.fillText('TRIPPED!', GW / 2, GH / 2 - 30);
        ctx.fillStyle = '#fbbf24'; ctx.font = '18px sans-serif';
        ctx.fillText(`Score: ${this.score}`, GW / 2, GH / 2 + 10);
        ctx.fillStyle = '#94a3b8'; ctx.font = '13px sans-serif';
        ctx.fillText('Do a squat to restart', GW / 2, GH / 2 + 45);
      }
    }

    reset() { this.obstacles = []; this.score = 0; this.dead = false; this.frame = 0; this.charY = GH - 100; this.jumpVY = 0; this.isJumping = false; }
  }

  // ── SPACE SHOOTER (Shoulder Press) ────────────────────────
  // Rep fires bullets upward; enemies spawn at top
  class SpaceShooterGame {
    constructor() {
      this.bullets = [];
      this.enemies = [];
      this.score = 0;
      this.frame = 0;
      this.dead = false;
      this.shipY = GH - 80;
      this.spawnTimer = 0;
      this.lives = 3;
    }

    update(armAngle, repEvent) {
      if (this.dead) return;
      this.frame++;

      if (repEvent) {
        this.bullets.push({ x: GW / 2, y: this.shipY - 20, speed: 8 });
        this.bullets.push({ x: GW / 2 - 20, y: this.shipY - 10, speed: 7 });
        this.bullets.push({ x: GW / 2 + 20, y: this.shipY - 10, speed: 7 });
      }

      // Move bullets
      for (let i = this.bullets.length - 1; i >= 0; i--) {
        this.bullets[i].y -= this.bullets[i].speed;
        if (this.bullets[i].y < 0) this.bullets.splice(i, 1);
      }

      // Spawn enemies
      this.spawnTimer++;
      if (this.spawnTimer >= Math.max(40, 90 - this.score * 2)) {
        this.enemies.push({ x: 30 + Math.random() * (GW - 60), y: -20, speed: 1.2 + this.score * 0.05, hp: 1 });
        this.spawnTimer = 0;
      }

      // Move enemies + check bullet hits + ship collision
      for (let i = this.enemies.length - 1; i >= 0; i--) {
        const e = this.enemies[i];
        e.y += e.speed;
        if (e.y > GH) { this.enemies.splice(i, 1); this.lives--; if (this.lives <= 0) this.dead = true; continue; }
        let hit = false;
        for (let j = this.bullets.length - 1; j >= 0; j--) {
          const b = this.bullets[j];
          if (Math.abs(b.x - e.x) < 22 && Math.abs(b.y - e.y) < 22) {
            this.bullets.splice(j, 1); hit = true; this.score++; break;
          }
        }
        if (hit) this.enemies.splice(i, 1);
      }
    }

    draw(ctx, armAngle) {
      // Space bg
      ctx.fillStyle = '#050510'; ctx.fillRect(0, 0, GW, GH);
      ctx.fillStyle = 'rgba(255,255,255,0.6)';
      for (let i = 0; i < 50; i++) {
        const sx = (i * 113 + this.frame * 0.2) % GW;
        const sy = (i * 67 + (i % 3) * this.frame * 0.15) % GH;
        ctx.fillRect(sx, sy, 1.5, 1.5);
      }

      // Bullets
      for (const b of this.bullets) {
        ctx.fillStyle = '#ffd700'; ctx.fillRect(b.x - 2, b.y - 8, 4, 16);
        ctx.fillStyle = '#fff'; ctx.fillRect(b.x - 1, b.y - 8, 2, 6);
      }

      // Enemies
      for (const e of this.enemies) {
        ctx.save(); ctx.translate(e.x, e.y);
        ctx.fillStyle = '#e74c3c';
        ctx.beginPath(); ctx.arc(0, 0, 16, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = '#c0392b'; ctx.beginPath(); ctx.arc(-8, -4, 5, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = '#ff9c9c'; ctx.beginPath(); ctx.arc(8, -4, 5, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      }

      // Ship
      const sx = GW / 2;
      ctx.save(); ctx.translate(sx, this.shipY);
      ctx.fillStyle = '#3b82f6';
      ctx.beginPath(); ctx.moveTo(0, -28); ctx.lineTo(-22, 20); ctx.lineTo(22, 20); ctx.closePath(); ctx.fill();
      ctx.fillStyle = '#60a5fa'; ctx.beginPath(); ctx.arc(0, -4, 8, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#ff6b35';
      for (let fx = -1; fx <= 1; fx += 2) {
        ctx.beginPath(); ctx.moveTo(fx * 8, 20); ctx.lineTo(fx * 14, 35 + Math.sin(this.frame * .3) * 5); ctx.lineTo(fx * 2, 22); ctx.closePath(); ctx.fill();
      }
      ctx.restore();

      // Lives
      for (let l = 0; l < this.lives; l++) {
        ctx.fillStyle = '#ef4444';
        ctx.beginPath(); ctx.arc(GW - 20 - l * 22, 30, 8, 0, Math.PI * 2); ctx.fill();
      }

      // HUD
      ctx.fillStyle = 'rgba(0,0,0,0.6)'; ctx.fillRect(0, 0, GW, 44);
      ctx.fillStyle = '#fbbf24'; ctx.font = 'bold 18px monospace'; ctx.textAlign = 'left';
      ctx.fillText(`SCORE: ${this.score}`, 12, 28);
      ctx.fillStyle = '#94a3b8'; ctx.textAlign = 'center';
      ctx.fillText('PRESS UP TO SHOOT!', GW / 2, 28);

      if (this.dead) {
        ctx.fillStyle = 'rgba(0,0,0,0.7)'; ctx.fillRect(0, 0, GW, GH);
        ctx.fillStyle = '#fff'; ctx.font = 'bold 28px "Segoe UI",sans-serif'; ctx.textAlign = 'center';
        ctx.fillText('GAME OVER!', GW / 2, GH / 2 - 30);
        ctx.fillStyle = '#fbbf24'; ctx.font = '18px sans-serif';
        ctx.fillText(`Score: ${this.score}`, GW / 2, GH / 2 + 10);
        ctx.fillStyle = '#94a3b8'; ctx.font = '13px sans-serif';
        ctx.fillText('Do a shoulder press to restart', GW / 2, GH / 2 + 45);
      }
    }

    reset() { this.bullets = []; this.enemies = []; this.score = 0; this.dead = false; this.frame = 0; this.lives = 3; }
  }

  // ── LIFT METER GAME (Deadlift / Pushup) ───────────────────
  // Each rep fills a power bar; filled bar smashes a barrier for points
  class LiftMeterGame {
    constructor() {
      this.power = 0;
      this.maxPower = 5;
      this.barriers = [];
      this.score = 0;
      this.frame = 0;
      this.particles = [];
      this.flashA = 0;
    }

    update(repEvent) {
      this.frame++;
      if (repEvent) {
        this.power++;
        if (this.power >= this.maxPower) {
          this.power = 0; this.score++;
          // Smash particles
          for (let i = 0; i < 20; i++) {
            const a = Math.random() * Math.PI * 2;
            const s = 3 + Math.random() * 5;
            this.particles.push({ x: GW / 2, y: GH / 2, vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: 1, col: '#ffd700' });
          }
          this.flashA = 1;
          // New barrier
          this.barriers.push({ x: GW / 2, hitsNeeded: this.score + 2, hitsLeft: this.score + 2 });
        }
        this.particles.push({ x: GW / 2 + 80, y: GH / 2, vx: -5, vy: -2, life: 1, col: '#00ff88' });
      }
      if (this.barriers.length === 0) {
        this.barriers.push({ x: GW / 2, hitsNeeded: 3, hitsLeft: 3 });
      }
      // Particles
      for (let i = this.particles.length - 1; i >= 0; i--) {
        const p = this.particles[i];
        p.x += p.vx; p.y += p.vy; p.vy += 0.25; p.life -= 0.035;
        if (p.life <= 0) this.particles.splice(i, 1);
      }
      if (this.flashA > 0) this.flashA -= 0.05;
    }

    draw(ctx, currentAngle) {
      // Gym background
      const bg = ctx.createLinearGradient(0, 0, 0, GH);
      bg.addColorStop(0, '#1a0a2e'); bg.addColorStop(1, '#0a0a1a');
      ctx.fillStyle = bg; ctx.fillRect(0, 0, GW, GH);

      // Floor
      ctx.fillStyle = '#1a1a2a'; ctx.fillRect(0, GH - 60, GW, 60);
      ctx.strokeStyle = '#2a2a3a'; ctx.lineWidth = 1;
      for (let fx = 0; fx < GW; fx += 40) { ctx.beginPath(); ctx.moveTo(fx, GH - 60); ctx.lineTo(fx, GH); ctx.stroke(); }

      // Draw weightlifter silhouette
      const phase = currentAngle < 90 ? 'up' : 'down';
      const lx = GW / 2, ly = phase === 'up' ? GH - 120 : GH - 100;
      ctx.strokeStyle = '#3b82f6'; ctx.lineWidth = 4;
      // Body
      ctx.beginPath(); ctx.moveTo(lx, ly - 40); ctx.lineTo(lx, ly); ctx.stroke();
      // Head
      ctx.fillStyle = '#3b82f6'; ctx.beginPath(); ctx.arc(lx, ly - 52, 12, 0, Math.PI * 2); ctx.fill();
      // Arms + barbell
      const armY = phase === 'up' ? ly - 55 : ly - 40;
      ctx.beginPath(); ctx.moveTo(lx - 30, armY + 10); ctx.lineTo(lx - 80, armY); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(lx + 30, armY + 10); ctx.lineTo(lx + 80, armY); ctx.stroke();
      // Barbell
      ctx.strokeStyle = '#94a3b8'; ctx.lineWidth = 6;
      ctx.beginPath(); ctx.moveTo(lx - 80, armY); ctx.lineTo(lx + 80, armY); ctx.stroke();
      ctx.fillStyle = '#475569';
      for (let wx of [lx - 82, lx - 72, lx + 72, lx + 82]) {
        ctx.beginPath(); ctx.arc(wx, armY, 8, 0, Math.PI * 2); ctx.fill();
      }
      // Legs
      ctx.strokeStyle = '#3b82f6'; ctx.lineWidth = 4;
      if (phase === 'up') {
        ctx.beginPath(); ctx.moveTo(lx, ly); ctx.lineTo(lx - 20, ly + 45); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(lx, ly); ctx.lineTo(lx + 20, ly + 45); ctx.stroke();
      } else {
        ctx.beginPath(); ctx.moveTo(lx, ly); ctx.lineTo(lx - 25, ly + 30); ctx.lineTo(lx - 20, ly + 55); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(lx, ly); ctx.lineTo(lx + 25, ly + 30); ctx.lineTo(lx + 20, ly + 55); ctx.stroke();
      }

      // Power meter
      const meterX = 40, meterY = 80, meterH = GH - 180;
      ctx.fillStyle = 'rgba(0,0,0,0.5)'; ctx.fillRect(meterX, meterY, 28, meterH);
      ctx.strokeStyle = '#475569'; ctx.lineWidth = 1; ctx.strokeRect(meterX, meterY, 28, meterH);
      const fillPct = this.power / this.maxPower;
      const fillH = meterH * fillPct;
      const mGrad = ctx.createLinearGradient(0, meterY + meterH, 0, meterY);
      mGrad.addColorStop(0, '#3b82f6'); mGrad.addColorStop(0.5, '#00ff88'); mGrad.addColorStop(1, '#ffd700');
      ctx.fillStyle = mGrad; ctx.fillRect(meterX, meterY + meterH - fillH, 28, fillH);
      ctx.fillStyle = '#fff'; ctx.font = 'bold 11px sans-serif'; ctx.textAlign = 'center';
      ctx.fillText('PWR', meterX + 14, meterY - 8);
      for (let seg = 0; seg < this.maxPower; seg++) {
        const lineY = meterY + meterH - (meterH / this.maxPower) * seg;
        ctx.strokeStyle = 'rgba(255,255,255,0.3)'; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(meterX, lineY); ctx.lineTo(meterX + 28, lineY); ctx.stroke();
      }

      // Barrier to break
      if (this.barriers.length > 0) {
        const bar = this.barriers[0];
        const barW = 60, barH = 180;
        const barX = GW - barW - 40, barY = GH / 2 - barH / 2;
        const hpPct = bar.hitsLeft / bar.hitsNeeded;
        ctx.fillStyle = `rgba(${Math.round(255 * hpPct)},${Math.round(100 * (1 - hpPct))},50,0.9)`;
        ctx.fillRect(barX, barY, barW, barH);
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.strokeRect(barX, barY, barW, barH);
        ctx.fillStyle = '#fff'; ctx.font = 'bold 12px sans-serif'; ctx.textAlign = 'center';
        ctx.fillText(`HP:${bar.hitsLeft}`, barX + barW / 2, barY - 8);
        // Crack lines
        for (let cr = 0; cr < (bar.hitsNeeded - bar.hitsLeft) * 3; cr++) {
          ctx.strokeStyle = 'rgba(0,0,0,0.5)'; ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(barX + 10 + cr * 12 % barW, barY + 10);
          ctx.lineTo(barX + 20 + cr * 12 % barW, barY + barH - 10);
          ctx.stroke();
        }
      }

      // Particles
      for (const p of this.particles) {
        ctx.globalAlpha = Math.max(0, p.life);
        ctx.fillStyle = p.col; ctx.beginPath(); ctx.arc(p.x, p.y, 5, 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = 1;

      // Flash
      if (this.flashA > 0) {
        ctx.fillStyle = 'rgba(255,220,0,' + this.flashA * 0.35 + ')'; ctx.fillRect(0, 0, GW, GH);
      }

      // HUD
      ctx.fillStyle = 'rgba(0,0,0,0.65)'; ctx.fillRect(0, 0, GW, 44);
      ctx.fillStyle = '#ffd700'; ctx.font = 'bold 18px monospace'; ctx.textAlign = 'left';
      ctx.fillText(`SCORE: ${this.score}`, 12, 28);
      ctx.fillStyle = '#00ff88'; ctx.textAlign = 'right';
      ctx.fillText(`${this.power}/${this.maxPower} REPS TO SMASH`, GW - 12, 28);
    }

    reset() { this.power = 0; this.barriers = []; this.score = 0; this.frame = 0; this.particles = []; }
  }

  // ══════════════════════════════════════════════════════════
  //  GAME FACTORY — pick game by exercise
  // ══════════════════════════════════════════════════════════
  function createGameForExercise(exercise) {
    const ex = (exercise || '').toLowerCase();
    if (ex.includes('lateral')) return { game: new FlappyGame(), type: 'flappy' };
    if (ex.includes('bicep') || ex.includes('curl')) return { game: new CatchGame(), type: 'catch' };
    if (ex.includes('squat') || ex.includes('lunge')) return { game: new SquatJumpGame(), type: 'squat' };
    if (ex.includes('shoulder') || ex.includes('press') || ex.includes('bench')) return { game: new SpaceShooterGame(), type: 'shooter' };
    if (ex.includes('deadlift') || ex.includes('pushup') || ex.includes('push')) return { game: new LiftMeterGame(), type: 'lift' };
    if (ex.includes('plank') || ex.includes('row') || ex.includes('pull')) return { game: new CatchGame(), type: 'catch' };
    return { game: new CatchGame(), type: 'catch' };
  }

  // ══════════════════════════════════════════════════════════
  //  GESTURE BUTTONS FOR WORKOUT CONTROLS
  //  (mirrors main.py hud_btns placed on the camera view)
  // ══════════════════════════════════════════════════════════
  class WorkoutGestureControls {
    constructor(canvasW, canvasH) {
      const bw = 120, bh = 40, x = canvasW - bw - 10;
      this.buttons = {
        stop: new GestureButton(x, 60, bw, bh, '⏹ STOP', '#7f1d1d', '#fca5a5'),
        reset: new GestureButton(x, 112, bw, bh, '🔄 RESET', '#1e3a5f', '#93c5fd'),
        switch: new GestureButton(x, 164, bw, bh, '🔀 SWITCH', '#3b1a6e', '#c4b5fd'),
      };
      this.canvasW = canvasW;
      this.canvasH = canvasH;
    }

    // fingertip: {x,y} normalised 0..1 (from MediaPipe Hands)
    update(fingertip) {
      const results = {};
      for (const [name, btn] of Object.entries(this.buttons)) {
        results[name] = btn.updateHover(fingertip, this.canvasW, this.canvasH);
      }
      return results;
    }

    draw(ctx) {
      for (const btn of Object.values(this.buttons)) btn.draw(ctx);
    }
  }

  // ══════════════════════════════════════════════════════════
  //  HAND GESTURE TRACKER
  //  Runs MediaPipe Hands on a separate video stream.
  //  Returns normalised {x, y} of index fingertip (or null).
  //  Mirrors main.py HandGestureTracker.get_fingertip()
  // ══════════════════════════════════════════════════════════
  class HandGestureTracker {
    constructor() {
      this.hands = null;
      this.camera = null;
      this.videoEl = null;
      this.fingertip = null;
      this.enabled = false;
      this.previewCtx = null;
      this._ready = false;
    }

    async init(previewCanvas) {
      // Hidden video element
      this.videoEl = document.createElement('video');
      this.videoEl.autoplay = true; this.videoEl.muted = true; this.videoEl.playsInline = true;
      this.videoEl.style.display = 'none';
      document.body.appendChild(this.videoEl);

      if (previewCanvas) this.previewCtx = previewCanvas.getContext('2d');

      // Load MediaPipe Hands
      const loadHands = () => new Promise((resolve, reject) => {
        if (window.Hands) { resolve(); return; }
        const s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js';
        s.onload = () => setTimeout(resolve, 600);
        s.onerror = reject;
        document.head.appendChild(s);
      });

      try {
        await loadHands();
        this.hands = new window.Hands({ locateFile: f => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${f}` });
        this.hands.setOptions({ maxNumHands: 1, modelComplexity: 0, minDetectionConfidence: 0.62, minTrackingConfidence: 0.58 });
        this.hands.onResults(r => this._onResults(r));
        this._ready = true;
      } catch (e) {
        console.warn('[GestureTracker] MediaPipe Hands load failed:', e);
      }
    }

    async start() {
      if (!this._ready || this.enabled) return;
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240, facingMode: 'user' }, audio: false });
        this.videoEl.srcObject = stream;
        await this.videoEl.play();
        this.enabled = true;

        if (window.Camera) {
          this.camera = new window.Camera(this.videoEl, {
            onFrame: async () => {
              if (this.enabled && this.hands && this.videoEl.readyState >= 2) {
                try { await this.hands.send({ image: this.videoEl }); } catch (e) { }
              }
            },
            width: 320, height: 240
          });
          this.camera.start();
        } else {
          const loop = async () => {
            if (!this.enabled) return;
            if (this.hands && this.videoEl.readyState >= 2) {
              try { await this.hands.send({ image: this.videoEl }); } catch (e) { }
            }
            requestAnimationFrame(loop);
          };
          loop();
        }
      } catch (e) { console.warn('[GestureTracker] Camera error:', e); }
    }

    stop() {
      this.enabled = false;
      if (this.camera) { try { this.camera.stop(); } catch (e) { } this.camera = null; }
      if (this.videoEl?.srcObject) { this.videoEl.srcObject.getTracks().forEach(t => t.stop()); this.videoEl.srcObject = null; }
      this.fingertip = null;
    }

    _onResults(results) {
      // Draw preview
      if (this.previewCtx && results.image) {
        const pc = this.previewCtx.canvas;
        this.previewCtx.clearRect(0, 0, pc.width, pc.height);
        this.previewCtx.drawImage(results.image, 0, 0, pc.width, pc.height);
        if (results.multiHandLandmarks && window.drawConnectors && window.HAND_CONNECTIONS) {
          for (const lm of results.multiHandLandmarks) {
            window.drawConnectors(this.previewCtx, lm, window.HAND_CONNECTIONS, { color: '#00ff88', lineWidth: 1.5 });
            window.drawLandmarks(this.previewCtx, lm, { color: '#3b82f6', lineWidth: 1, radius: 3 });
          }
        }
      }

      if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
        const lm = results.multiHandLandmarks[0];
        // main.py: only track when index finger is UP
        const indexUp = lm[8].y < lm[6].y;
        if (indexUp) {
          this.fingertip = { x: lm[8].x, y: lm[8].y };
        } else {
          this.fingertip = null;
        }

        // Draw fingertip on preview
        if (this.previewCtx && this.fingertip) {
          const pc = this.previewCtx.canvas;
          const fx = (1 - this.fingertip.x) * pc.width;
          const fy = this.fingertip.y * pc.height;
          this.previewCtx.beginPath(); this.previewCtx.arc(fx, fy, 8, 0, Math.PI * 2);
          this.previewCtx.strokeStyle = '#ffd700'; this.previewCtx.lineWidth = 2; this.previewCtx.stroke();
          this.previewCtx.beginPath(); this.previewCtx.arc(fx, fy, 3, 0, Math.PI * 2);
          this.previewCtx.fillStyle = '#ffd700'; this.previewCtx.fill();
        }
      } else {
        this.fingertip = null;
      }
    }

    getFingertip() { return this.fingertip; }
  }

  // ══════════════════════════════════════════════════════════
  //  POSE MIRROR
  //  Copies pose-video + pose-canvas into the game's right panel
  // ══════════════════════════════════════════════════════════
  class PoseMirror {
    constructor(hostEl) {
      this.host = hostEl;
      this.canvas = null;
      this.ctx = null;
      this.rafId = null;
      this.running = false;
    }

    start() {
      if (this.running) return;
      this.host.innerHTML = '';

      this.canvas = document.createElement('canvas');
      this.canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#000;';
      this.host.appendChild(this.canvas);
      this.ctx = this.canvas.getContext('2d');

      // LIVE badge
      const badge = document.createElement('div');
      badge.style.cssText = 'position:absolute;top:8px;left:8px;background:rgba(220,38,38,0.9);color:#fff;font-size:10px;font-weight:700;padding:3px 10px;border-radius:12px;pointer-events:none;font-family:"Segoe UI",sans-serif;';
      badge.textContent = '🔴 LIVE';
      this.host.appendChild(badge);

      this.running = true;
      this._frame();
    }

    _frame() {
      if (!this.running || !this.ctx) return;

      const host = this.host;
      const hw = host.clientWidth || 600, hh = host.clientHeight || 400;
      if (this.canvas.width !== hw) this.canvas.width = hw;
      if (this.canvas.height !== hh) this.canvas.height = hh;

      const vid = document.getElementById('pose-video');
      const src = document.getElementById('pose-canvas');

      if (vid && vid.readyState >= 2 && vid.videoWidth > 0) {
        this.ctx.drawImage(vid, 0, 0, hw, hh);
      } else {
        this.ctx.fillStyle = '#0f172a'; this.ctx.fillRect(0, 0, hw, hh);
        this.ctx.fillStyle = '#475569'; this.ctx.font = '14px "Segoe UI",sans-serif'; this.ctx.textAlign = 'center';
        this.ctx.fillText('📷 Start workout for live feed', hw / 2, hh / 2);
        this.ctx.textAlign = 'left';
      }
      if (src && src.width > 0) {
        this.ctx.drawImage(src, 0, 0, hw, hh);
      }

      this.rafId = requestAnimationFrame(() => this._frame());
    }

    // Draw gesture cursor overlay on pose mirror canvas
    drawGestureCursor(fingertip) {
      if (!this.ctx || !fingertip || !this.canvas) return;
      const fx = (1 - fingertip.x) * this.canvas.width;
      const fy = fingertip.y * this.canvas.height;
      this.ctx.save();
      this.ctx.beginPath(); this.ctx.arc(fx, fy, 22, 0, Math.PI * 2);
      this.ctx.strokeStyle = '#ffd700'; this.ctx.lineWidth = 2.5; this.ctx.stroke();
      this.ctx.beginPath(); this.ctx.arc(fx, fy, 5, 0, Math.PI * 2);
      this.ctx.fillStyle = '#ffd700'; this.ctx.fill();
      this.ctx.restore();
    }

    stop() {
      this.running = false;
      if (this.rafId) { cancelAnimationFrame(this.rafId); this.rafId = null; }
    }
  }

  // ══════════════════════════════════════════════════════════
  //  MAIN GAME CONTROLLER
  // ══════════════════════════════════════════════════════════
  let gameCanvas, gameCtx;
  let gestureControls = null;
  let gestureTracker = null;
  let poseMirror = null;
  let currentGameObj = null;
  let currentGameType = null;
  let animId = null;
  let gameRunning = false;
  let prevReps = 0;
  let prevAngle = 90;

  function getReps() { return typeof window._acpfRepCount === 'number' ? window._acpfRepCount : (typeof window.repCounter === 'number' ? window.repCounter : parseInt(document.getElementById('rep-count')?.textContent || '0')); }
  function getAngle() { return typeof window._acpfCurrentAngle === 'number' ? window._acpfCurrentAngle : (parseFloat(document.getElementById('angle-display')?.textContent) || 90); }
  function getLateralNorm() {
    // Direct from script.js: 0=arms down, 1=arms at shoulder height
    if (typeof window._lateralRaiseNorm === 'number') return window._lateralRaiseNorm;
    // Fallback: derive from raw angle (hip-shoulder-wrist, ~10°=down, ~90°=up)
    const angle = getAngle();
    return Math.min(1, Math.max(0, (angle - 10) / 80));
  }

  // ── Main loop ──────────────────────────────────────────────
  function mainLoop() {
    if (!gameRunning) return;

    const currentReps = getReps();
    const repEvent = currentReps > prevReps;
    const angle = getAngle();
    prevAngle = angle;

    // Get wrist positions from pose for CatchGame
    let wristPts = [];
    if (currentGameType === 'catch') {
      const vid = document.getElementById('pose-video');
      if (currentGameObj && vid && vid.videoWidth > 0) {
        // Best effort: use angle as proxy for wrist spread
        // The CatchGame will use pose landmarks if available
        if (typeof window._acpfWristL === 'object') wristPts.push(window._acpfWristL);
        if (typeof window._acpfWristR === 'object') wristPts.push(window._acpfWristR);
      }
    }

    // Update game
    if (currentGameObj) {
      switch (currentGameType) {
        case 'catch':
          if (wristPts.length > 0) currentGameObj.catcherPoints = wristPts;
          currentGameObj.update(repEvent);
          break;
        case 'flappy':
          // Pass raw angle - FlappyGame internally reads window._lateralRaiseNorm
          currentGameObj.update(angle, repEvent);
          break;
        case 'squat':
          if (repEvent && currentGameObj.dead) currentGameObj.reset();
          currentGameObj.update(repEvent);
          break;
        case 'shooter':
          if (repEvent && currentGameObj.dead) currentGameObj.reset();
          currentGameObj.update(angle, repEvent);
          break;
        case 'lift':
          currentGameObj.update(repEvent);
          break;
      }
    }

    prevReps = currentReps;

    // Draw game canvas
    if (gameCtx && currentGameObj) {
      gameCtx.clearRect(0, 0, GW, GH);
      switch (currentGameType) {
        case 'catch': currentGameObj.draw(gameCtx); break;
        case 'flappy': currentGameObj.draw(gameCtx, angle); break;
        case 'squat': currentGameObj.draw(gameCtx, repEvent); break;
        case 'shooter': currentGameObj.draw(gameCtx, angle); break;
        case 'lift': currentGameObj.draw(gameCtx, angle); break;
      }
    }

    // Gesture controls
    const ft = gestureTracker ? gestureTracker.getFingertip() : null;
    if (gestureControls && ft !== undefined) {
      const fired = gestureControls.update(ft);

      // Draw gesture buttons on game canvas (same as main.py hud_btns on cam side)
      if (gameCtx) gestureControls.draw(gameCtx);

      // Draw cursor on game canvas
      if (gameCtx && ft) {
        const fx = (1 - ft.x) * GW, fy = ft.y * GH;
        gameCtx.beginPath(); gameCtx.arc(fx, fy, 20, 0, Math.PI * 2);
        gameCtx.strokeStyle = '#ffd700'; gameCtx.lineWidth = 2; gameCtx.stroke();
        gameCtx.beginPath(); gameCtx.arc(fx, fy, 4, 0, Math.PI * 2);
        gameCtx.fillStyle = '#ffd700'; gameCtx.fill();
      }

      if (fired.stop) { if (typeof stopWorkout === 'function') stopWorkout(); toast('⏹ Stopped by gesture'); }
      if (fired.reset) { if (typeof resetCounter === 'function') resetCounter(); toast('🔄 Reset by gesture'); if (currentGameObj) currentGameObj.reset(); }
      if (fired.switch) { if (typeof switchWorkout === 'function') switchWorkout(); toast('🔀 Switched by gesture'); }
    }

    // Mirror pose into right panel
    if (poseMirror && ft) poseMirror.drawGestureCursor(ft);

    // Update stats
    updateStats();

    animId = requestAnimationFrame(mainLoop);
  }

  function updateStats() {
    const get = id => document.getElementById(id)?.textContent || '-';
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set('game-stage-mirror', get('stage-display'));
    const form = get('form-display');
    set('game-form-mirror', form.length > 20 ? form.slice(0, 20) + '…' : form);
    set('game-angle-mirror', get('angle-display'));
    set('game-rep-display', getReps());
    const exName = document.getElementById('current-workout-name');
    const gName = document.getElementById('game-exercise-name');
    if (exName && gName) gName.textContent = exName.textContent || 'Exercise';
    const scoreEl = document.getElementById('game-score-display');
    if (scoreEl && currentGameObj) scoreEl.textContent = currentGameObj.score || 0;
  }

  // ── Open ───────────────────────────────────────────────────
  async function openGame() {
    const cv = document.getElementById('camera-view');
    if (!cv || cv.style.display === 'none') { showMsg('⚠️ Start a workout first, then click 🎮 Game Mode!'); return; }

    const modal = document.getElementById('workout-game-modal');
    if (!modal) return;
    modal.style.display = 'flex';

    // Get canvas refs
    gameCanvas = document.getElementById('game-canvas');
    gameCtx = gameCanvas.getContext('2d');

    // Create exercise-specific game
    const exName = document.getElementById('current-workout-name')?.textContent || '';
    const { game, type } = createGameForExercise(exName);
    currentGameObj = game;
    currentGameType = type;

    // Gesture buttons on game canvas
    gestureControls = new WorkoutGestureControls(GW, GH);

    // Pose mirror
    const host = document.getElementById('game-pose-host');
    if (host) { poseMirror = new PoseMirror(host); poseMirror.start(); }

    // Gesture tracker
    const previewCanvas = document.getElementById('gesture-preview-canvas');
    if (!gestureTracker) {
      gestureTracker = new HandGestureTracker();
      await gestureTracker.init(previewCanvas);
    }
    await gestureTracker.start();

    // Reset state
    prevReps = getReps(); prevAngle = getAngle(); gameRunning = true;

    if (animId) cancelAnimationFrame(animId);
    mainLoop();

    // Update game title
    const titles = { catch: '🏋️ Catch the Dumbbells!', flappy: '🐦 Flap with Your Arms!', squat: '🏃 Squat to Jump!', shooter: '🚀 Press to Shoot!', lift: '💪 Lift to Smash!' };
    const gTitle = document.getElementById('game-title-label');
    if (gTitle) gTitle.textContent = titles[type] || '🎮 Workout Game';
  }

  function closeGame() {
    gameRunning = false;
    if (animId) { cancelAnimationFrame(animId); animId = null; }
    if (poseMirror) { poseMirror.stop(); poseMirror = null; }
    if (gestureTracker) { gestureTracker.stop(); }
    const modal = document.getElementById('workout-game-modal');
    if (modal) modal.style.display = 'none';
  }

  // ══════════════════════════════════════════════════════════
  //  BUILD MODAL UI
  // ══════════════════════════════════════════════════════════
  function buildUI() {
    const modal = document.createElement('div');
    modal.id = 'workout-game-modal';
    modal.style.cssText = 'display:none;position:fixed;inset:0;z-index:10001;background:rgba(0,0,0,0.93);align-items:center;justify-content:center;flex-direction:column;';

    modal.innerHTML = `
  <div style="display:flex;width:96vw;max-width:1300px;height:90vh;background:#0f172a;border-radius:18px;overflow:hidden;border:2px solid #1e293b;box-shadow:0 0 80px rgba(0,0,0,0.9);">

    <!-- LEFT: Game canvas panel -->
    <div style="width:${GW}px;flex-shrink:0;display:flex;flex-direction:column;background:#0c1526;border-right:2px solid #1e293b;">

      <!-- Game header -->
      <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:#070e1a;border-bottom:1px solid #1e293b;flex-shrink:0;">
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-size:20px;">🎮</span>
          <div>
            <div id="game-title-label" style="color:#f1f5f9;font-weight:800;font-size:14px;font-family:'Segoe UI',sans-serif;">Workout Game</div>
            <div style="color:#475569;font-size:10px;font-family:'Segoe UI',sans-serif;">Game reacts to your reps!</div>
          </div>
        </div>
        <div style="display:flex;gap:18px;">
          <div style="text-align:center;">
            <div style="color:#475569;font-size:9px;text-transform:uppercase;font-family:'Segoe UI',sans-serif;">SCORE</div>
            <div id="game-score-display" style="color:#fbbf24;font-weight:900;font-size:20px;font-family:monospace;">0</div>
          </div>
        </div>
      </div>

      <!-- Game canvas — FIXED pixel size -->
      <canvas id="game-canvas" width="${GW}" height="${GH}"
              style="display:block;width:${GW}px;height:${GH}px;flex-shrink:0;"></canvas>

      <!-- Gesture preview (bottom of game panel) -->
      <div style="flex:1;display:flex;flex-direction:column;background:#070e1a;border-top:1px solid #1e293b;padding:8px 10px;min-height:0;">
        <div style="color:#475569;font-size:9px;text-transform:uppercase;letter-spacing:.4px;margin-bottom:5px;font-family:'Segoe UI',sans-serif;">☝️ GESTURE CONTROL — index finger to click buttons</div>
        <canvas id="gesture-preview-canvas" width="200" height="100"
                style="display:block;width:100%;border-radius:6px;background:#000;border:1px solid #1e293b;"></canvas>
      </div>
    </div>

    <!-- RIGHT: Live pose detection -->
    <div style="flex:1;display:flex;flex-direction:column;background:#0f172a;min-width:0;overflow:hidden;">

      <!-- Header -->
      <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 16px;background:#070e1a;border-bottom:1px solid #1e293b;flex-shrink:0;">
        <div style="display:flex;align-items:center;gap:10px;">
          <span style="font-size:18px;">📷</span>
          <div>
            <div style="color:#f1f5f9;font-weight:700;font-size:15px;font-family:'Segoe UI',sans-serif;">Live Pose Detection</div>
            <div id="game-exercise-name" style="color:#475569;font-size:10px;font-family:'Segoe UI',sans-serif;">Exercise</div>
          </div>
        </div>
        <div style="display:flex;gap:8px;">
          <button id="game-pause-btn"
            style="background:#1e293b;border:1px solid #334155;color:#94a3b8;padding:7px 16px;border-radius:8px;cursor:pointer;font-size:12px;font-family:'Segoe UI',sans-serif;font-weight:600;">
            ⏸ Pause
          </button>
          <button id="game-exit-btn"
            style="background:#7f1d1d;border:1px solid #991b1b;color:#fca5a5;padding:7px 16px;border-radius:8px;cursor:pointer;font-size:12px;font-family:'Segoe UI',sans-serif;font-weight:700;">
            ✕ Exit
          </button>
        </div>
      </div>

      <!-- POSE MIRROR — fills available height -->
      <div id="game-pose-host" style="flex:1;position:relative;overflow:hidden;background:#000;min-height:0;"></div>

      <!-- Stats bar -->
      <div style="display:flex;background:#070e1a;border-top:1px solid #1e293b;flex-shrink:0;">
        <div style="flex:1;text-align:center;padding:10px 4px;border-right:1px solid #1e293b;">
          <div style="color:#475569;font-size:9px;text-transform:uppercase;margin-bottom:3px;font-family:'Segoe UI',sans-serif;">STAGE</div>
          <div id="game-stage-mirror" style="color:#f1f5f9;font-weight:700;font-size:13px;font-family:'Segoe UI',sans-serif;">-</div>
        </div>
        <div style="flex:2;text-align:center;padding:10px 4px;border-right:1px solid #1e293b;">
          <div style="color:#475569;font-size:9px;text-transform:uppercase;margin-bottom:3px;font-family:'Segoe UI',sans-serif;">FORM</div>
          <div id="game-form-mirror" style="color:#10b981;font-weight:700;font-size:12px;font-family:'Segoe UI',sans-serif;">Ready</div>
        </div>
        <div style="flex:1;text-align:center;padding:10px 4px;border-right:1px solid #1e293b;">
          <div style="color:#475569;font-size:9px;text-transform:uppercase;margin-bottom:3px;font-family:'Segoe UI',sans-serif;">ANGLE</div>
          <div id="game-angle-mirror" style="color:#3b82f6;font-weight:700;font-size:13px;font-family:'Segoe UI',sans-serif;">-</div>
        </div>
        <div style="flex:1;text-align:center;padding:10px 4px;">
          <div style="color:#475569;font-size:9px;text-transform:uppercase;margin-bottom:3px;font-family:'Segoe UI',sans-serif;">REPS</div>
          <div id="game-rep-display" style="color:#00ff88;font-weight:700;font-size:13px;font-family:'Segoe UI',sans-serif;">0</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Bottom tip -->
  <div style="margin-top:8px;color:#475569;font-size:11px;text-align:center;font-family:'Segoe UI',sans-serif;">
    🎮 Game reacts to your exercise reps &nbsp;|&nbsp; ☝️ Point index finger at buttons to gesture-click &nbsp;|&nbsp; Press <b style="color:#3b82f6">Space</b> to manually trigger
  </div>
  `;

    document.body.appendChild(modal);

    // Wire buttons
    document.getElementById('game-pause-btn').addEventListener('click', () => {
      gameRunning = !gameRunning;
      const btn = document.getElementById('game-pause-btn');
      btn.textContent = gameRunning ? '⏸ Pause' : '▶ Resume';
      btn.style.background = gameRunning ? '#1e293b' : '#14532d';
      if (gameRunning) { if (animId) cancelAnimationFrame(animId); mainLoop(); }
    });
    document.getElementById('game-exit-btn').addEventListener('click', closeGame);

    // Space bar = manual rep trigger
    document.addEventListener('keydown', e => {
      if (e.code === 'Space') {
        const m = document.getElementById('workout-game-modal');
        if (m && m.style.display !== 'none') {
          e.preventDefault();
          if (currentGameObj) {
            if (currentGameType === 'catch') { currentGameObj.spawn(); currentGameObj.spawn(); }
            if (currentGameType === 'flappy') { currentGameObj.dead ? currentGameObj.reset() : (() => { currentGameObj.birdY = Math.max(60, currentGameObj.birdY - 40); })(); }
            if (currentGameType === 'squat') currentGameObj.update(true);
            if (currentGameType === 'shooter') currentGameObj.update(90, true);
            if (currentGameType === 'lift') currentGameObj.update(true);
          }
        }
      }
    });
  }

  // ══════════════════════════════════════════════════════════
  //  INJECT BUTTONS INTO FITPULSE UI
  // ══════════════════════════════════════════════════════════
  function injectButtons() {
    // "Play with Game" in workout-config
    const waitConfig = n => {
      const bg = document.querySelector('.button-group');
      if (bg) {
        if (!document.getElementById('open-game-mode-btn')) {
          const btn = document.createElement('button');
          btn.id = 'open-game-mode-btn';
          btn.className = 'config-btn game-mode-btn';
          btn.innerHTML = '<span style="font-size:20px;">🎮</span> Play with Game';
          btn.onclick = () => {
            if (typeof startWorkout === 'function') {
              startWorkout().then(() => setTimeout(openGame, 600)).catch(() => setTimeout(openGame, 600));
            } else openGame();
          };
          bg.insertBefore(btn, bg.firstChild);
        }
      } else if (n < 40) setTimeout(() => waitConfig(n + 1), 300);
    };
    waitConfig(0);

    // "🎮 Game Mode" in trainer-controls
    const waitControls = n => {
      const tc = document.querySelector('.trainer-controls');
      if (tc) {
        if (!tc.querySelector('.game-btn')) {
          const btn = document.createElement('button');
          btn.className = 'control-btn game-btn';
          btn.innerHTML = '<span style="font-size:18px;">🎮</span> Game Mode';
          btn.onclick = openGame;
          tc.appendChild(btn);
        }
      } else if (n < 40) setTimeout(() => waitControls(n + 1), 300);
    };
    waitControls(0);
  }

  function showMsg(msg) {
    const t = document.createElement('div');
    t.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#1e293b;border:2px solid #f59e0b;color:#fbbf24;padding:16px 28px;border-radius:12px;font-size:15px;font-weight:700;z-index:20000;font-family:"Segoe UI",sans-serif;';
    t.textContent = msg; document.body.appendChild(t);
    setTimeout(() => t.remove(), 3500);
  }

  function toast(msg) {
    const old = document.getElementById('game-toast'); if (old) old.remove();
    const t = document.createElement('div');
    t.id = 'game-toast';
    t.style.cssText = 'position:fixed;top:70px;left:50%;transform:translateX(-50%);background:#0f172a;border:1.5px solid #00ff88;color:#00ff88;padding:9px 22px;border-radius:10px;font-size:13px;font-weight:600;z-index:99999;pointer-events:none;font-family:"Segoe UI",sans-serif;transition:opacity .3s;';
    t.textContent = msg; document.body.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; }, 2200);
    setTimeout(() => t.remove(), 2700);
  }

  // ══════════════════════════════════════════════════════════
  //  INIT
  // ══════════════════════════════════════════════════════════
  function init() {
    buildUI();
    injectButtons();
    console.log('[WorkoutGame] ✅ Ready — exercise-specific games with gesture controls');
  }

  window.workoutGame = {
    openGame, closeGame,
    pauseGame: () => {
      gameRunning = !gameRunning;
      const pb = document.getElementById('game-pause-btn');
      if (pb) { pb.textContent = gameRunning ? '⏸ Pause' : '▶ Resume'; pb.style.background = gameRunning ? '#1e293b' : '#14532d'; }
      if (gameRunning) { if (animId) cancelAnimationFrame(animId); mainLoop(); }
    }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

})();