const typewriterStrings = [
  'Free & Secured - Lonely Hub',
  'Trusted By Thousands Daily',
  '100% Free Mod',
  '100% No Malware,Virus',
];

let twIndex = 0;
let twChar = 0;
let twDeleting = false;
let twEl = null;

function typewriterTick() {
  if (!twEl) return;
  const str = typewriterStrings[twIndex];
  if (!twDeleting) {
    twEl.textContent = str.slice(0, ++twChar);
    if (twChar === str.length) {
      twDeleting = true;
      setTimeout(typewriterTick, 2000);
      return;
    }
    setTimeout(typewriterTick, 48);
  } else {
    twEl.textContent = str.slice(0, --twChar);
    if (twChar === 0) {
      twDeleting = false;
      twIndex = (twIndex + 1) % typewriterStrings.length;
      setTimeout(typewriterTick, 350);
      return;
    }
    setTimeout(typewriterTick, 22);
  }
}

function initTilt() {
  const cards = document.querySelectorAll('.tilt-card');
  const MAX_TILT = 14;
  const MAX_SHINE = 0.18;

  cards.forEach(card => {
    let raf = null;
    let currentX = 0;
    let currentY = 0;
    let targetX = 0;
    let targetY = 0;
    let isHovered = false;

    function lerp(a, b, t) { return a + (b - a) * t; }

    function animate() {
      currentX = lerp(currentX, targetX, 0.12);
      currentY = lerp(currentY, targetY, 0.12);

      const dx = Math.abs(currentX - targetX);
      const dy = Math.abs(currentY - targetY);

      card.style.transform =
        `perspective(900px) rotateX(${currentX}deg) rotateY(${currentY}deg) scale3d(1.02,1.02,1.02)`;

      if (dx > 0.01 || dy > 0.01) {
        raf = requestAnimationFrame(animate);
      } else {
        raf = null;
      }
    }

    card.addEventListener('mousemove', e => {
      const rect = card.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const px = (e.clientX - cx) / (rect.width / 2);
      const py = (e.clientY - cy) / (rect.height / 2);

      targetY = px * MAX_TILT;
      targetX = -py * MAX_TILT;

      const shine = card.querySelector('.feature-card-glow');
      if (shine) {
        const sx = ((e.clientX - rect.left) / rect.width) * 100;
        const sy = ((e.clientY - rect.top) / rect.height) * 100;
        shine.style.background =
          `radial-gradient(circle at ${sx}% ${sy}%, rgba(250,80,80,0.22) 0%, transparent 65%)`;
      }

      if (!raf) raf = requestAnimationFrame(animate);
    });

    card.addEventListener('mouseenter', () => {
      isHovered = true;
    });

    card.addEventListener('mouseleave', () => {
      isHovered = false;
      targetX = 0;
      targetY = 0;
      if (!raf) raf = requestAnimationFrame(animate);

      setTimeout(() => {
        if (!isHovered) {
          card.style.transform = 'perspective(900px) rotateX(0deg) rotateY(0deg) scale3d(1,1,1)';
          currentX = 0;
          currentY = 0;
          if (raf) { cancelAnimationFrame(raf); raf = null; }
        }
      }, 400);
    });
  });
}

function initScrollReveal() {
  const cards = document.querySelectorAll('.feature-card');
  if (!('IntersectionObserver' in window)) {
    cards.forEach(c => c.classList.add('visible'));
    return;
  }
  cards.forEach((card, i) => {
    card.style.opacity = '0';
    card.style.transform = 'translateY(32px)';
    card.style.transition = `opacity 0.55s ease ${i * 0.08}s, transform 0.55s ease ${i * 0.08}s`;
  });
  const obs = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        entry.target.style.transform = 'translateY(0)';
        obs.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });
  cards.forEach(card => obs.observe(card));
}

document.addEventListener('DOMContentLoaded', () => {
  twEl = document.getElementById('typewriter-text');
  if (twEl) setTimeout(typewriterTick, 600);

  initTilt();
  initScrollReveal();
});
