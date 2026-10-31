(function () {
  // ----- On/Off switches (kisi effect ko band karna ho to false likho) -----
  const ENABLE_NETWORK = true;
  const ENABLE_COUNT_UP = true;
  const ENABLE_TYPEWRITER = true;

  const win = window.parent;
  const doc = win.document;

  if (win.__fxCleanup) {
    try { win.__fxCleanup(); } catch (e) {}
  }
  const cleanups = [];

  // ===== Effect 1: Data network background =====
  if (ENABLE_NETWORK) {
    const canvas = doc.createElement('canvas');
    canvas.id = 'fx-network';
    canvas.style.cssText =
      'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:1;opacity:0.55;';
    doc.body.appendChild(canvas);
    const ctx = canvas.getContext('2d');
    let W = 0, H = 0, nodes = [], raf = 0;
    const mouse = { x: -9999, y: -9999 };

    const resize = () => {
      const dpr = win.devicePixelRatio || 1;
      W = win.innerWidth;
      H = win.innerHeight;
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.min(70, Math.floor((W * H) / 22000));
      nodes = Array.from({ length: count }, () => ({
        x: Math.random() * W,
        y: Math.random() * H,
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.35,
        red: Math.random() < 0.12,
      }));
    };

    const draw = () => {
      ctx.clearRect(0, 0, W, H);
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        a.x += a.vx;
        a.y += a.vy;
        if (a.x < 0 || a.x > W) a.vx *= -1;
        if (a.y < 0 || a.y > H) a.vy *= -1;

        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d < 130) {
            ctx.strokeStyle = 'rgba(25,198,255,' + 0.18 * (1 - d / 130) + ')';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }

        const dm = Math.hypot(a.x - mouse.x, a.y - mouse.y);
        if (dm < 160) {
          ctx.strokeStyle = 'rgba(255,107,134,' + 0.35 * (1 - dm / 160) + ')';
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(mouse.x, mouse.y);
          ctx.stroke();
        }

        ctx.fillStyle = a.red ? 'rgba(255,59,92,0.9)' : 'rgba(25,198,255,0.85)';
        ctx.beginPath();
        ctx.arc(a.x, a.y, a.red ? 2.2 : 1.7, 0, Math.PI * 2);
        ctx.fill();
      }
      raf = win.requestAnimationFrame(draw);
    };

    const onMove = (e) => {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    };

    win.addEventListener('resize', resize);
    win.addEventListener('mousemove', onMove);
    resize();
    draw();

    cleanups.push(() => {
      win.cancelAnimationFrame(raf);
      win.removeEventListener('resize', resize);
      win.removeEventListener('mousemove', onMove);
      canvas.remove();
    });
  }

  // ===== Effect 2: KPI count-up =====
  if (ENABLE_COUNT_UP) {
    const firstTextNode = (el) => {
      const walker = doc.createTreeWalker(el, 4); // 4 = sirf text nodes
      let n;
      while ((n = walker.nextNode())) {
        if (/\d/.test(n.nodeValue)) return n;
      }
      return null;
    };

    const countUp = (el) => {
      const tn = firstTextNode(el);
      if (!tn) return;
      const raw = tn.nodeValue.trim();
      if (el.dataset.fxDone === raw || el.dataset.fxRun) return;
      const target = parseFloat(raw.replace(/,/g, ''));
      if (isNaN(target)) return;
      el.dataset.fxRun = '1';
      const start = win.performance.now();
      const duration = 1200;
      const step = (t) => {
        const p = Math.min(1, (t - start) / duration);
        const eased = 1 - Math.pow(1 - p, 3);
        tn.nodeValue = Math.round(target * eased).toLocaleString('en-US');
        if (p < 1) {
          win.requestAnimationFrame(step);
        } else {
          tn.nodeValue = raw;
          el.dataset.fxDone = raw;
          delete el.dataset.fxRun;
        }
      };
      win.requestAnimationFrame(step);
    };

    const scan = () => {
      doc.querySelectorAll('[data-testid="stMetricValue"]').forEach(countUp);
    };
    const observer = new win.MutationObserver(scan);
    observer.observe(doc.body, { childList: true, subtree: true });
    scan();
    cleanups.push(() => observer.disconnect());
  }

  // ===== Effect 3: Typewriter in hero =====
  if (ENABLE_TYPEWRITER) {
    const phrases = [
      'What is the total revenue?',
      'Which product sells the most?',
      'Show profit by country',
      'Sab se zyada sales kis city se hui?',
      'Explain this file',
    ];
    let pi = 0, ci = 0, deleting = false, timer = 0;

    const type = () => {
      const el = doc.querySelector('.fx-typing');
      let delay = deleting ? 28 : 55;
      if (el) {
        const full = phrases[pi];
        ci += deleting ? -1 : 1;
        el.textContent = full.slice(0, ci);
        if (!deleting && ci === full.length) {
          deleting = true;
          delay = 1400;
        } else if (deleting && ci === 0) {
          deleting = false;
          pi = (pi + 1) % phrases.length;
        }
      }
      timer = win.setTimeout(type, delay);
    };
    type();
    cleanups.push(() => win.clearTimeout(timer));
  }

  win.__fxCleanup = () => {
    cleanups.forEach((fn) => {
      try { fn(); } catch (e) {}
    });
  };
})();