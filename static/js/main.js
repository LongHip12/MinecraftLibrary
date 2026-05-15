function showToast(message, type = 'success') {
  let container = document.querySelector('.toast');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast';
    document.body.appendChild(container);
  }
  const item = document.createElement('div');
  item.className = `toast-item toast-${type}`;

  const icons = {
    success: `<div class="toast-icon toast-icon-success"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg></div>`,
    error: `<div class="toast-icon toast-icon-error"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></div>`,
    info: `<div class="toast-icon toast-icon-info"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg></div>`,
    warning: `<div class="toast-icon toast-icon-warning"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg></div>`
  };

  const icon = icons[type] || icons.success;

  const closeBtn = document.createElement('button');
  closeBtn.className = 'toast-close';
  closeBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;

  item.innerHTML = icon + `<span class="toast-message">${message}</span>`;
  item.appendChild(closeBtn);

  const progress = document.createElement('div');
  progress.className = 'toast-progress';
  item.appendChild(progress);

  container.appendChild(item);

  const duration = 3800;
  const start = performance.now();
  let animFrame;

  function updateProgress(now) {
    const elapsed = now - start;
    const pct = Math.min(100, (elapsed / duration) * 100);
    progress.style.width = (100 - pct) + '%';
    if (pct < 100) {
      animFrame = requestAnimationFrame(updateProgress);
    }
  }
  animFrame = requestAnimationFrame(updateProgress);

  function dismiss() {
    cancelAnimationFrame(animFrame);
    item.classList.add('toast-out');
    setTimeout(() => item.remove(), 320);
  }

  closeBtn.addEventListener('click', dismiss);

  setTimeout(dismiss, duration);
}

function initDropdowns() {
  document.querySelectorAll('.dropdown-custom').forEach(dd => {
    const trigger = dd.querySelector('.dropdown-trigger');
    const menu = dd.querySelector('.dropdown-menu');
    if (!trigger || !menu) return;
    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = menu.classList.contains('open');
      document.querySelectorAll('.dropdown-menu.open').forEach(m => {
        m.classList.remove('open');
        m.previousElementSibling?.classList.remove('open');
      });
      if (!isOpen) {
        menu.classList.add('open');
        trigger.classList.add('open');
      }
    });
    menu.querySelectorAll('.dropdown-item').forEach(item => {
      item.addEventListener('click', () => {
        const value = item.dataset.value;
        const label = item.textContent.trim();
        trigger.querySelector('.dropdown-label').textContent = label;
        menu.querySelectorAll('.dropdown-item').forEach(i => i.classList.remove('selected'));
        item.classList.add('selected');
        menu.classList.remove('open');
        trigger.classList.remove('open');
        trigger.dataset.value = value;
        trigger.dispatchEvent(new CustomEvent('change', { detail: { value } }));
      });
    });
  });
  document.addEventListener('click', () => {
    document.querySelectorAll('.dropdown-menu.open').forEach(m => {
      m.classList.remove('open');
      m.previousElementSibling?.classList.remove('open');
    });
  });
}

function initThreeDotMenus() {
  document.querySelectorAll('.three-dot-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const menu = btn.nextElementSibling;
      if (!menu) return;
      const isOpen = menu.classList.contains('open');
      document.querySelectorAll('.user-actions-menu.open').forEach(m => m.classList.remove('open'));
      if (!isOpen) menu.classList.add('open');
    });
  });
  document.addEventListener('click', () => {
    document.querySelectorAll('.user-actions-menu.open').forEach(m => m.classList.remove('open'));
  });
}

function initNavHighlight() {
  const path = window.location.pathname;
  document.querySelectorAll('.nav-link').forEach(link => {
    if (link.getAttribute('href') === path) {
      link.classList.add('active');
    }
  });
}

function animateNumbers() {
  document.querySelectorAll('[data-count]').forEach(el => {
    const target = parseInt(el.dataset.count);
    if (isNaN(target)) return;
    const duration = 1500;
    const start = performance.now();
    const update = (now) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = Math.round(eased * target).toLocaleString();
      if (progress < 1) requestAnimationFrame(update);
    };
    requestAnimationFrame(update);
  });
}

function initIntersectionAnimations() {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        if (entry.target.hasAttribute('data-count')) {
          const target = parseInt(entry.target.dataset.count);
          if (!isNaN(target)) {
            const duration = 1500;
            const start = performance.now();
            const update = (now) => {
              const elapsed = now - start;
              const progress = Math.min(elapsed / duration, 1);
              const eased = 1 - Math.pow(1 - progress, 3);
              entry.target.textContent = Math.round(eased * target).toLocaleString();
              if (progress < 1) requestAnimationFrame(update);
            };
            requestAnimationFrame(update);
          }
        }
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.2 });
  document.querySelectorAll('[data-count]').forEach(el => observer.observe(el));
}

document.addEventListener('DOMContentLoaded', () => {
  initDropdowns();
  initThreeDotMenus();
  initNavHighlight();
  initIntersectionAnimations();
});
