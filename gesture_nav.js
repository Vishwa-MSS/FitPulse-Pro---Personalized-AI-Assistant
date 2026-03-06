/**
 * gesture_nav.js — FitPulse Gesture Control  v5
 * ================================================
 * GESTURE SCHEME (fixed):
 *   ☝️  Index finger UP only   → move cursor (no click)
 *   ✌️  Index + Middle UP      → INSTANT CLICK (pinch gesture = select)
 *
 * BUTTON COVERAGE: covers ALL buttons in FitPulse UI:
 *   - Home screen exercise cards
 *   - Workout config / start / stop buttons
 *   - In-workout controls (stop, reset, switch, +5/-5 reps)
 *   - Modal close buttons
 *
 * HOVER CLICK (fallback): hover index finger for 0.7s → fires
 *
 * USAGE:
 *   1. Click "🤚 Gesture" button (top-right during workout)
 *   2. Raise ☝️ index finger to move cursor
 *   3. Raise ✌️ index+middle to click what cursor is pointing at
 */

(function () {
  'use strict';

  // ══════════════════════════════════════════════════════════
  //  CONFIG
  // ══════════════════════════════════════════════════════════
  const HOVER_FRAMES = 21;    // frames to hold for hover-click (~0.7s at 30fps)
  const PINCH_COOLDOWN = 22;    // frames between pinch clicks (prevents double-fire)
  const CAM_W = 240, CAM_H = 180;

  // ══════════════════════════════════════════════════════════
  //  STATE
  // ══════════════════════════════════════════════════════════
  let enabled = false;
  let mpHands = null;
  let mpCamera = null;
  let vidEl = null;
  let previewCtx = null;
  let panelEl = null;
  let overlayCanvas = null;
  let overlayCtx = null;
  let rafId = null;

  // Fingertip in normalised coords [0..1]
  let fingertipNorm = null;   // index tip (cursor position)
  let isPinching = false;  // two fingers up = click intent
  let pinchCooldown = 0;      // prevents rapid repeated clicks
  let lastClickPt = null;   // for visual feedback

  // Per-button hover state
  let buttonHoverMap = new Map();  // elementId or selector → hover frames

  // ══════════════════════════════════════════════════════════
  //  HAND RESULT PROCESSING
  //  Index-only UP → cursor
  //  Index+Middle UP → pinch-click
  // ══════════════════════════════════════════════════════════
  function onResults(results) {
    // Draw preview
    if (previewCtx) {
      const pc = previewCtx.canvas;
      previewCtx.clearRect(0, 0, pc.width, pc.height);
      if (results.image) previewCtx.drawImage(results.image, 0, 0, pc.width, pc.height);
      if (results.multiHandLandmarks && window.drawConnectors && window.HAND_CONNECTIONS) {
        for (const lm of results.multiHandLandmarks) {
          window.drawConnectors(previewCtx, lm, window.HAND_CONNECTIONS, { color: '#00ff88', lineWidth: 1.5 });
          window.drawLandmarks(previewCtx, lm, { color: '#3b82f6', lineWidth: 1, radius: 3 });
        }
      }
    }

    if (!results.multiHandLandmarks || results.multiHandLandmarks.length === 0) {
      fingertipNorm = null; isPinching = false; return;
    }

    const lm = results.multiHandLandmarks[0];

    // Detect which fingers are UP
    // Finger up: tip Y < pip Y (y increases downward in normalised coords)
    const indexUp = lm[8].y < lm[6].y;   // index tip above index PIP
    const middleUp = lm[12].y < lm[10].y;  // middle tip above middle PIP
    const ringDown = lm[16].y > lm[14].y;  // ring is down
    const pinkyDown = lm[20].y > lm[18].y;  // pinky is down

    if (indexUp) {
      // Cursor position = index fingertip (mirrored)
      fingertipNorm = { x: 1 - lm[8].x, y: lm[8].y };

      // Pinch gesture = index + middle up, ring + pinky down
      isPinching = middleUp && ringDown && pinkyDown;
    } else {
      fingertipNorm = null;
      isPinching = false;
    }

    // Draw on preview
    if (previewCtx && fingertipNorm) {
      const pc = previewCtx.canvas;
      const fx = fingertipNorm.x * pc.width;
      const fy = fingertipNorm.y * pc.height;
      const col = isPinching ? '#ff4444' : '#ffd700';
      previewCtx.beginPath(); previewCtx.arc(fx, fy, 10, 0, Math.PI * 2);
      previewCtx.strokeStyle = col; previewCtx.lineWidth = 2.5; previewCtx.stroke();
      previewCtx.beginPath(); previewCtx.arc(fx, fy, 3, 0, Math.PI * 2);
      previewCtx.fillStyle = col; previewCtx.fill();
      if (isPinching) {
        previewCtx.strokeStyle = '#ff444488'; previewCtx.lineWidth = 8;
        previewCtx.beginPath(); previewCtx.arc(fx, fy, 18, 0, Math.PI * 2); previewCtx.stroke();
      }
    }
  }

  // ══════════════════════════════════════════════════════════
  //  GET ALL CLICKABLE ELEMENTS VISIBLE ON SCREEN
  //  Scans the live DOM for anything clickable (buttons, cards, etc.)
  // ══════════════════════════════════════════════════════════
  function getClickableElements() {
    const selectors = [
      'button',
      '[role="button"]',
      '.exercise-card',
      '.exercise-option',
      '.config-btn',
      '.control-btn',
      '.workout-card',
      '.rep-btn',
      '.trainer-control-btn',
      'a.btn',
      '[data-gesture-click]',
      '.modal-close',
      '.close-btn',
    ];
    const els = [];
    for (const sel of selectors) {
      document.querySelectorAll(sel).forEach(el => {
        if (el.offsetParent !== null && !el.disabled) {  // visible + enabled
          const rect = el.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) els.push(el);
        }
      });
    }
    // Deduplicate
    return [...new Set(els)];
  }

  // ══════════════════════════════════════════════════════════
  //  HIT TEST — is fingertip over an element?
  // ══════════════════════════════════════════════════════════
  function elementAtFingertip(fingertipScreen) {
    if (!fingertipScreen) return null;
    const { x, y } = fingertipScreen;
    const els = getClickableElements();
    for (const el of els) {
      const r = el.getBoundingClientRect();
      if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) {
        return el;
      }
    }
    return null;
  }

  // ══════════════════════════════════════════════════════════
  //  RENDER LOOP — draws overlay + processes clicks
  // ══════════════════════════════════════════════════════════
  function renderLoop() {
    if (!enabled || !overlayCtx) { rafId = null; return; }

    // Sync overlay to full viewport
    const vw = window.innerWidth, vh = window.innerHeight;
    if (overlayCanvas.width !== vw || overlayCanvas.height !== vh) {
      overlayCanvas.width = vw; overlayCanvas.height = vh;
    }
    overlayCtx.clearRect(0, 0, vw, vh);

    if (pinchCooldown > 0) pinchCooldown--;

    // Convert normalised fingertip → screen pixels
    let ftScreen = null;
    if (fingertipNorm) {
      ftScreen = {
        x: fingertipNorm.x * vw,
        y: fingertipNorm.y * vh,
      };
    }

    // Find element under cursor
    const hoveredEl = elementAtFingertip(ftScreen);

    // ── PINCH CLICK (two fingers = instant click) ──────────
    if (isPinching && ftScreen && pinchCooldown === 0) {
      pinchCooldown = PINCH_COOLDOWN;
      lastClickPt = { ...ftScreen };
      if (hoveredEl) {
        fireClick(hoveredEl);
      } else {
        // Click the DOM element at that screen point
        const el = document.elementFromPoint(ftScreen.x, ftScreen.y);
        if (el && el !== overlayCanvas) fireClick(el);
      }
    }

    // ── HOVER CLICK (index only, hold still for HOVER_FRAMES) ─
    if (ftScreen && hoveredEl && !isPinching) {
      const key = getElKey(hoveredEl);
      const frames = (buttonHoverMap.get(key) || 0) + 1;
      buttonHoverMap.set(key, frames);

      if (frames >= HOVER_FRAMES) {
        buttonHoverMap.set(key, 0);
        pinchCooldown = PINCH_COOLDOWN;
        lastClickPt = { ...ftScreen };
        fireClick(hoveredEl);
      }

      // Draw hover arc on the hovered button
      const r = hoveredEl.getBoundingClientRect();
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      const rad = Math.min(r.width, r.height) / 2 - 4;
      const frac = frames / HOVER_FRAMES;
      overlayCtx.save();
      overlayCtx.strokeStyle = '#00ffc8'; overlayCtx.lineWidth = 3;
      overlayCtx.beginPath();
      overlayCtx.arc(cx, cy, Math.max(rad, 12), -Math.PI / 2, -Math.PI / 2 + frac * Math.PI * 2);
      overlayCtx.stroke();
      // Highlight border
      overlayCtx.strokeStyle = `rgba(0,255,200,${0.2 + 0.5 * frac})`;
      overlayCtx.lineWidth = 2;
      overlayCtx.strokeRect(r.left - 2, r.top - 2, r.width + 4, r.height + 4);
      overlayCtx.restore();
    } else {
      // Decay hover frames for elements no longer hovered
      if (hoveredEl) {
        const key = getElKey(hoveredEl);
        buttonHoverMap.set(key, 0);
      }
    }

    // Clear hover state for non-hovered elements
    if (!hoveredEl) {
      buttonHoverMap.clear();
    }

    // ── DRAW CURSOR ────────────────────────────────────────
    if (ftScreen) {
      const col = isPinching ? '#ff4444' : '#ffd700';
      const r = isPinching ? 22 : 18;

      overlayCtx.save();

      // Outer ring
      overlayCtx.beginPath(); overlayCtx.arc(ftScreen.x, ftScreen.y, r, 0, Math.PI * 2);
      overlayCtx.strokeStyle = col + 'cc'; overlayCtx.lineWidth = isPinching ? 3.5 : 2.5;
      overlayCtx.stroke();

      // Inner dot
      overlayCtx.beginPath(); overlayCtx.arc(ftScreen.x, ftScreen.y, isPinching ? 7 : 5, 0, Math.PI * 2);
      overlayCtx.fillStyle = col; overlayCtx.fill();

      // Crosshair lines
      overlayCtx.strokeStyle = col + '88'; overlayCtx.lineWidth = 1.5;
      overlayCtx.beginPath();
      overlayCtx.moveTo(ftScreen.x - r - 8, ftScreen.y);
      overlayCtx.lineTo(ftScreen.x + r + 8, ftScreen.y);
      overlayCtx.moveTo(ftScreen.x, ftScreen.y - r - 8);
      overlayCtx.lineTo(ftScreen.x, ftScreen.y + r + 8);
      overlayCtx.stroke();

      // Pinch label
      if (isPinching) {
        overlayCtx.fillStyle = '#ff4444';
        overlayCtx.font = 'bold 13px "Segoe UI",sans-serif';
        overlayCtx.textAlign = 'center';
        overlayCtx.fillText('CLICK ✌️', ftScreen.x, ftScreen.y - r - 10);
      } else if (hoveredEl) {
        overlayCtx.fillStyle = '#ffd700';
        overlayCtx.font = 'bold 12px "Segoe UI",sans-serif';
        overlayCtx.textAlign = 'center';
        const label = hoveredEl.textContent?.trim()?.slice(0, 20) || 'button';
        overlayCtx.fillText(`✌️ to click: ${label}`, ftScreen.x, ftScreen.y - r - 10);
      }

      overlayCtx.restore();
    }

    // ── CLICK RIPPLE ───────────────────────────────────────
    if (lastClickPt) {
      // Handled by CSS animation injected at click time
      lastClickPt = null;
    }

    // Update HUD label
    updateHUDLabel(hoveredEl, isPinching);

    rafId = requestAnimationFrame(renderLoop);
  }

  function getElKey(el) {
    return el.id || el.className + el.textContent?.slice(0, 20);
  }

  // ══════════════════════════════════════════════════════════
  //  FIRE CLICK — synthesise a real click event on element
  // ══════════════════════════════════════════════════════════
  function fireClick(el) {
    if (!el) return;
    // Visual ripple
    showRipple(el);
    toast(`✌️ Clicked: ${el.textContent?.trim()?.slice(0, 25) || 'button'}`);

    // Dispatch real click
    try {
      el.click();
    } catch (e) { }

    // Also dispatch pointer + mouse events for frameworks that listen to those
    ['pointerdown', 'pointerup', 'mousedown', 'mouseup', 'click'].forEach(evName => {
      try {
        const ev = new MouseEvent(evName, { bubbles: true, cancelable: true, view: window });
        el.dispatchEvent(ev);
      } catch (e) { }
    });
  }

  // ══════════════════════════════════════════════════════════
  //  HUD LABEL UPDATE
  // ══════════════════════════════════════════════════════════
  function updateHUDLabel(hoveredEl, pinching) {
    const labelEl = document.getElementById('gest-hover-label');
    if (!labelEl) return;
    if (!fingertipNorm) {
      labelEl.textContent = '☝️ Raise index finger to point';
      labelEl.style.color = '#475569'; return;
    }
    if (pinching) {
      labelEl.textContent = '✌️ CLICKING!';
      labelEl.style.color = '#ff4444'; return;
    }
    if (hoveredEl) {
      const name = hoveredEl.textContent?.trim()?.slice(0, 30) || 'button';
      labelEl.textContent = `Hovering: ${name} — raise ✌️ to click`;
      labelEl.style.color = '#ffd700'; return;
    }
    labelEl.textContent = 'Point at any button, then ✌️ to click';
    labelEl.style.color = '#94a3b8';
  }

  // ══════════════════════════════════════════════════════════
  //  BUILD UI
  // ══════════════════════════════════════════════════════════
  function buildUI() {
    const style = document.createElement('style');
    style.textContent = `
    @keyframes gestRipple { from{transform:scale(1);opacity:0.8} to{transform:scale(3);opacity:0} }
    @keyframes gestSlide  { from{opacity:0;transform:translateY(-8px)} to{opacity:1;transform:translateY(0)} }
    #gesture-hud { animation: gestSlide .25s ease-out; }
    .gest-ripple { animation: gestRipple .5s ease-out forwards; pointer-events:none; }
  `;
    document.head.appendChild(style);

    // HUD panel
    panelEl = document.createElement('div');
    panelEl.id = 'gesture-hud';
    panelEl.style.cssText = `
    position:fixed;top:80px;left:12px;z-index:99990;
    display:none;flex-direction:column;
    width:${CAM_W}px;background:#0f172a;
    border:2px solid #1e293b;border-radius:14px;overflow:hidden;
    box-shadow:0 8px 32px rgba(0,0,0,0.7);font-family:'Segoe UI',sans-serif;
  `;
    panelEl.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;padding:7px 10px;background:#070e1a;border-bottom:1px solid #1e293b;">
      <div style="display:flex;align-items:center;gap:7px;">
        <div id="gest-dot" style="width:9px;height:9px;border-radius:50%;background:#ef4444;transition:background .3s;"></div>
        <span style="color:#94a3b8;font-size:11px;font-weight:700;letter-spacing:.4px;">GESTURE CONTROL</span>
      </div>
      <button id="gest-close" style="background:none;border:none;color:#64748b;cursor:pointer;font-size:14px;padding:0 4px;line-height:1;">✕</button>
    </div>
    <canvas id="gesture-preview" width="${CAM_W}" height="${CAM_H}" style="display:block;width:100%;background:#000;"></canvas>
    <div style="padding:8px 10px;background:#0c1526;border-top:1px solid #1e293b;">
      <div style="color:#475569;font-size:9px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px;">STATUS</div>
      <div id="gest-hover-label" style="color:#475569;font-size:11px;font-weight:600;line-height:1.4;">☝️ Raise index finger to point</div>
    </div>
    <div style="padding:8px 10px 10px;background:#070e1a;border-top:1px solid #1e293b;">
      <div style="color:#475569;font-size:9px;text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px;">HOW TO USE</div>
      <div style="color:#64748b;font-size:11px;line-height:1.9;">
        ☝️ <b style="color:#94a3b8">Index finger</b> = move cursor<br>
        ✌️ <b style="color:#ffd700">Index + Middle</b> = click instantly<br>
        <span style="color:#475569">Or hover index for 0.7s → click</span>
      </div>
    </div>
  `;
    document.body.appendChild(panelEl);
    document.getElementById('gest-close')?.addEventListener('click', () => { if (enabled) toggle(); });

    // Hidden video for hand tracking
    vidEl = document.createElement('video');
    vidEl.autoplay = true; vidEl.muted = true; vidEl.playsInline = true; vidEl.style.display = 'none';
    document.body.appendChild(vidEl);

    previewCtx = document.getElementById('gesture-preview')?.getContext('2d');

    // Full-viewport overlay canvas (above everything)
    overlayCanvas = document.createElement('canvas');
    overlayCanvas.id = 'gesture-overlay-canvas';
    overlayCanvas.style.cssText = `
    position:fixed;inset:0;width:100vw;height:100vh;
    pointer-events:none;z-index:99989;
  `;
    overlayCanvas.width = window.innerWidth;
    overlayCanvas.height = window.innerHeight;
    overlayCtx = overlayCanvas.getContext('2d');
    document.body.appendChild(overlayCanvas);

    // Toggle button (shows after page loads)
    const toggleBtn = document.createElement('button');
    toggleBtn.id = 'gesture-toggle-btn';
    toggleBtn.innerHTML = '🤚 Gesture';
    toggleBtn.style.cssText = `
    position:fixed;top:14px;right:12px;z-index:99991;
    background:#0f172a;border:2px solid #334155;color:#64748b;
    padding:7px 14px;border-radius:10px;cursor:pointer;
    font-size:12px;font-weight:700;font-family:'Segoe UI',sans-serif;
    transition:all .2s;
  `;
    toggleBtn.addEventListener('click', toggle);
    document.body.appendChild(toggleBtn);
  }

  // ══════════════════════════════════════════════════════════
  //  TOGGLE
  // ══════════════════════════════════════════════════════════
  function toggle() {
    enabled = !enabled;
    const tb = document.getElementById('gesture-toggle-btn');
    const dot = document.getElementById('gest-dot');

    if (enabled) {
      panelEl.style.display = 'flex';
      if (tb) { tb.style.borderColor = '#00ff88'; tb.style.color = '#00ff88'; tb.innerHTML = '🤚 ON'; }
      if (dot) dot.style.background = '#00ff88';
      startCamera();
      if (rafId) cancelAnimationFrame(rafId);
      renderLoop();
      toast('🤚 Gesture ON\n☝️ Point  |  ✌️ Click');
    } else {
      panelEl.style.display = 'none';
      if (tb) { tb.style.borderColor = '#334155'; tb.style.color = '#64748b'; tb.innerHTML = '🤚 Gesture'; }
      if (dot) dot.style.background = '#ef4444';
      stopCamera();
      if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
      if (overlayCtx) overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
      toast('Gesture Control OFF');
    }
  }

  // ══════════════════════════════════════════════════════════
  //  CAMERA
  // ══════════════════════════════════════════════════════════
  function startCamera() {
    const doInit = () => {
      if (!window.Hands) {
        const s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js';
        s.onload = () => setTimeout(doInit, 700);
        s.onerror = () => toast('⚠️ Could not load gesture model');
        document.head.appendChild(s);
        return;
      }
      if (!mpHands) {
        mpHands = new window.Hands({ locateFile: f => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${f}` });
        mpHands.setOptions({ maxNumHands: 1, modelComplexity: 0, minDetectionConfidence: 0.60, minTrackingConfidence: 0.55 });
        mpHands.onResults(onResults);
      }
      navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240, facingMode: 'user' }, audio: false })
        .then(stream => {
          vidEl.srcObject = stream;
          vidEl.play().catch(() => { });
          if (window.Camera) {
            if (mpCamera) { try { mpCamera.stop(); } catch (e) { } }
            mpCamera = new window.Camera(vidEl, {
              onFrame: async () => {
                if (enabled && mpHands && vidEl.readyState >= 2) {
                  try { await mpHands.send({ image: vidEl }); } catch (e) { }
                }
              },
              width: 320, height: 240
            });
            mpCamera.start();
          } else {
            const loop = async () => {
              if (!enabled) return;
              if (mpHands && vidEl.readyState >= 2) { try { await mpHands.send({ image: vidEl }); } catch (e) { } }
              requestAnimationFrame(loop);
            };
            loop();
          }
        })
        .catch(() => {
          toast('⚠️ Camera denied — gesture unavailable');
          enabled = false;
          panelEl.style.display = 'none';
          const tb = document.getElementById('gesture-toggle-btn');
          if (tb) { tb.style.borderColor = '#334155'; tb.style.color = '#64748b'; tb.innerHTML = '🤚 Gesture'; }
        });
    };
    doInit();
  }

  function stopCamera() {
    if (mpCamera) { try { mpCamera.stop(); } catch (e) { } mpCamera = null; }
    if (vidEl?.srcObject) { vidEl.srcObject.getTracks().forEach(t => t.stop()); vidEl.srcObject = null; }
    fingertipNorm = null; isPinching = false;
  }

  // ══════════════════════════════════════════════════════════
  //  FEEDBACK
  // ══════════════════════════════════════════════════════════
  function toast(msg) {
    const old = document.getElementById('gest-toast'); if (old) old.remove();
    const t = document.createElement('div'); t.id = 'gest-toast';
    t.style.cssText = 'position:fixed;top:68px;left:50%;transform:translateX(-50%);background:#0f172a;border:1.5px solid #00ff88;color:#00ff88;padding:9px 22px;border-radius:10px;font-size:13px;font-weight:600;z-index:99999;pointer-events:none;white-space:pre-line;text-align:center;font-family:"Segoe UI",sans-serif;transition:opacity .3s;box-shadow:0 4px 20px rgba(0,255,136,0.25);';
    t.textContent = msg; document.body.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; }, 2000);
    setTimeout(() => t.remove(), 2500);
  }

  function showRipple(el) {
    if (!el) return;
    const r = el.getBoundingClientRect();
    const div = document.createElement('div');
    div.className = 'gest-ripple';
    div.style.cssText = `position:fixed;left:${r.left + r.width / 2 - 20}px;top:${r.top + r.height / 2 - 20}px;width:40px;height:40px;border-radius:50%;border:3px solid #00ffc8;z-index:99998;`;
    document.body.appendChild(div);
    setTimeout(() => div.remove(), 600);
  }

  // ══════════════════════════════════════════════════════════
  //  INIT
  // ══════════════════════════════════════════════════════════
  function init() {
    buildUI();
    console.log('[GestureNav v5] ✅ Ready — ☝️ point | ✌️ instant click');
  }

  window.gestureNav = { toggle, isEnabled: () => enabled };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

})();