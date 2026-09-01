/* ==========================================================================
   AuraMed — "AI Brain" hero animation
   A canvas neural network shaped like a brain: neurons inside two hemispheres
   plus a brain stem, synapses between nearby neurons, and action potentials
   travelling the synapses. Pure canvas 2D — no libraries, no build step.

   Public API:  AuraMedBrain.mount(canvas)  →  { setActivity, setStatus, stop }
   ========================================================================== */
(function () {
  'use strict';

  const PALETTE = {
    neuron: [45, 212, 191],     // teal
    hot: [139, 92, 246],        // violet (firing)
    synapse: [125, 211, 252],   // light blue
  };

  /* ---- brain silhouette: two hemispheres + brain stem (normalized units) ---- */
  const LOBES = [
    { cx: -0.27, cy: -0.06, rx: 0.37, ry: 0.44 },
    { cx: 0.27, cy: -0.06, rx: 0.37, ry: 0.44 },
    { cx: 0.0, cy: 0.44, rx: 0.13, ry: 0.20 },
  ];

  function insideBrain(x, y) {
    for (const l of LOBES) {
      const dx = (x - l.cx) / l.rx;
      const dy = (y - l.cy) / l.ry;
      if (dx * dx + dy * dy <= 1) return true;
    }
    return false;
  }

  function rng(seed) {
    // deterministic PRNG so the brain looks the same on every load
    let s = seed >>> 0;
    return function () {
      s = (s * 1664525 + 1013904223) >>> 0;
      return s / 4294967296;
    };
  }

  function buildNetwork(count, rand) {
    const neurons = [];
    let guard = 0;
    while (neurons.length < count && guard < count * 200) {
      guard++;
      const x = (rand() * 2 - 1) * 0.78;
      const y = (rand() * 2 - 1) * 0.78;
      if (!insideBrain(x, y)) continue;
      // keep a little breathing room between neurons
      if (neurons.some(n => Math.hypot(n.x - x, n.y - y) < 0.11)) continue;
      neurons.push({
        x, y,
        r: 1.4 + rand() * 2.1,
        phase: rand() * Math.PI * 2,
        speed: 0.5 + rand() * 0.9,
        energy: 0,
        links: [],
      });
    }

    // connect close neighbours (cap the degree so it stays legible)
    const maxDist = 0.24;
    for (let i = 0; i < neurons.length; i++) {
      for (let j = i + 1; j < neurons.length; j++) {
        const d = Math.hypot(neurons[i].x - neurons[j].x, neurons[i].y - neurons[j].y);
        if (d > maxDist) continue;
        if (neurons[i].links.length >= 4 || neurons[j].links.length >= 4) continue;
        neurons[i].links.push(j);
        neurons[j].links.push(i);
      }
    }
    return neurons;
  }

  function mount(canvas) {
    if (!canvas || !canvas.getContext) return { setActivity() {}, setStatus() {}, stop() {} };
    const ctx = canvas.getContext('2d');
    const rand = rng(20260901);
    const neurons = buildNetwork(88, rand);

    const reduceMotion = window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let width = 0, height = 0, dpr = 1;
    let running = true;
    let activity = 0.55;        // 0..1 — raised while the UI awaits an API call
    let raf = 0;
    let started = performance.now();

    const pulses = [];

    function resize() {
      const rect = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = Math.max(1, rect.width);
      height = Math.max(1, rect.height);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function spawnPulse() {
      if (!neurons.length) return;
      const from = Math.floor(rand() * neurons.length);
      const node = neurons[from];
      if (!node.links.length) return;
      const to = node.links[Math.floor(rand() * node.links.length)];
      pulses.push({ from, to, t: 0, speed: 0.010 + rand() * 0.016 + activity * 0.012 });
      node.energy = Math.min(1, node.energy + 0.5);
    }

    function step(now) {
      const t = (now - started) / 1000;

      // firing rate follows the UI's activity level
      const spawnTarget = 1 + activity * 4;
      if (rand() < 0.10 * spawnTarget) spawnPulse();

      for (let i = pulses.length - 1; i >= 0; i--) {
        const p = pulses[i];
        p.t += p.speed;
        if (p.t >= 1) {
          neurons[p.to].energy = Math.min(1, neurons[p.to].energy + 0.75);
          // chain reaction — keeps the network alive
          const next = neurons[p.to].links;
          if (next.length && rand() < 0.55) {
            pulses.push({ from: p.to, to: next[Math.floor(rand() * next.length)], t: 0, speed: p.speed });
          }
          pulses.splice(i, 1);
        }
      }
      if (pulses.length > 90) pulses.splice(0, pulses.length - 90);

      for (const n of neurons) {
        n.energy *= 0.955;   // decay
        if (n.energy < 0.001) n.energy = 0;
      }
      return t;
    }

    function draw(t) {
      ctx.clearRect(0, 0, width, height);
      const cx = width / 2;
      const cy = height / 2;
      const scale = Math.min(width, height) * 0.62;

      // gentle "breathing" wobble so it reads as alive, not as a diagram
      const breathe = 1 + Math.sin(t * 0.7) * 0.018;
      const tilt = Math.sin(t * 0.35) * 0.05;

      const px = (n) => cx + (n.x * Math.cos(tilt) - n.y * Math.sin(tilt)) * scale * breathe;
      const py = (n) => cy + (n.x * Math.sin(tilt) + n.y * Math.cos(tilt)) * scale * breathe;

      // soft halo behind the brain
      const halo = ctx.createRadialGradient(cx, cy, scale * 0.1, cx, cy, scale * 1.05);
      halo.addColorStop(0, 'rgba(45,212,191,0.20)');
      halo.addColorStop(0.55, 'rgba(34,211,238,0.08)');
      halo.addColorStop(1, 'rgba(5,9,18,0)');
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(cx, cy, scale * 1.05, 0, Math.PI * 2);
      ctx.fill();

      // synapses
      ctx.lineWidth = 1;
      for (let i = 0; i < neurons.length; i++) {
        const a = neurons[i];
        const ax = px(a), ay = py(a);
        for (const j of a.links) {
          if (j < i) continue;
          const b = neurons[j];
          const glow = Math.max(a.energy, b.energy);
          const base = 0.10 + 0.06 * Math.sin(t * 1.4 + a.phase);
          const alpha = Math.min(0.62, base + glow * 0.5);
          const c = glow > 0.25 ? PALETTE.hot : PALETTE.synapse;
          ctx.strokeStyle = `rgba(${c[0]},${c[1]},${c[2]},${alpha.toFixed(3)})`;
          ctx.beginPath();
          ctx.moveTo(ax, ay);
          ctx.lineTo(px(b), py(b));
          ctx.stroke();
        }
      }

      // travelling action potentials
      for (const p of pulses) {
        const a = neurons[p.from], b = neurons[p.to];
        const ax = px(a), ay = py(a), bx = px(b), by = py(b);
        const x = ax + (bx - ax) * p.t;
        const y = ay + (by - ay) * p.t;
        const g = ctx.createRadialGradient(x, y, 0, x, y, 7);
        g.addColorStop(0, 'rgba(255,255,255,0.95)');
        g.addColorStop(0.4, 'rgba(45,212,191,0.75)');
        g.addColorStop(1, 'rgba(45,212,191,0)');
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(x, y, 7, 0, Math.PI * 2);
        ctx.fill();
      }

      // neurons
      for (const n of neurons) {
        const x = px(n), y = py(n);
        const idle = 0.35 + 0.28 * Math.sin(t * n.speed + n.phase);
        const e = Math.max(idle, n.energy);
        const radius = n.r * (1 + n.energy * 1.35);
        const c = n.energy > 0.3 ? PALETTE.hot : PALETTE.neuron;

        const g = ctx.createRadialGradient(x, y, 0, x, y, radius * 4.2);
        g.addColorStop(0, `rgba(${c[0]},${c[1]},${c[2]},${(0.55 * e + 0.16).toFixed(3)})`);
        g.addColorStop(1, `rgba(${c[0]},${c[1]},${c[2]},0)`);
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(x, y, radius * 4.2, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = `rgba(255,255,255,${(0.35 + 0.5 * e).toFixed(3)})`;
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    function frame(now) {
      const t = step(now);
      draw(t);
      if (running) raf = requestAnimationFrame(frame);
    }

    resize();
    if (typeof ResizeObserver !== 'undefined') {
      new ResizeObserver(resize).observe(canvas);
    } else {
      window.addEventListener('resize', resize);
    }

    if (reduceMotion) {
      // one calm static frame
      for (const n of neurons) n.energy = 0.35;
      draw(0.6);
    } else {
      raf = requestAnimationFrame(frame);
    }

    return {
      /** 0..1 — how busy the AI looks (the UI raises it during API calls). */
      setActivity(value) { activity = Math.max(0, Math.min(1, Number(value) || 0)); },
      /** Trigger a visible burst of firing. */
      pulse(count) {
        const n = Math.max(1, count || 6);
        for (let i = 0; i < n; i++) spawnPulse();
      },
      setStatus() {},
      stop() { running = false; cancelAnimationFrame(raf); },
    };
  }

  window.AuraMedBrain = { mount: mount };
})();
