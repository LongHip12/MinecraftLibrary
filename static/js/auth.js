function showSuccessOverlay(message, sub, redirectUrl) {
  const overlay = document.getElementById('success-overlay');
  if (!overlay) return;
  overlay.querySelector('.success-text').textContent = message;
  if (sub) overlay.querySelector('.success-sub').textContent = sub;
  overlay.classList.add('show');
  setTimeout(() => {
    window.location.href = redirectUrl;
  }, 2000);
}

function handleAuthSubmit(formId, endpoint, successMsg) {
  const form = document.getElementById(formId);
  if (!form) return;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = form.querySelector('.auth-submit-btn');
    const errEl = form.querySelector('.auth-error');
    const captchaToken = document.querySelector('[name="h-captcha-response"]')?.value || '';

    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> Processing...';

    const fd = new FormData(form);
    const nextUrl = new URLSearchParams(window.location.search).get('next') || '/';

    try {
      const resp = await fetch(endpoint + (window.location.search ? window.location.search : ''), {
        method: 'POST',
        body: fd
      });
      const data = await resp.json();
      if (data.success) {
        showSuccessOverlay(successMsg, 'Redirecting you shortly...', data.redirect || '/');
      } else {
        if (errEl) {
          errEl.textContent = data.error || 'An error occurred';
          errEl.style.display = 'flex';
        }
        btn.disabled = false;
        btn.innerHTML = endpoint.includes('login') ? 'Sign In' : 'Create Account';
        if (window.hcaptcha) window.hcaptcha.reset();
      }
    } catch (err) {
      if (errEl) {
        errEl.textContent = 'Network error. Please try again.';
        errEl.style.display = 'flex';
      }
      btn.disabled = false;
      btn.innerHTML = endpoint.includes('login') ? 'Sign In' : 'Create Account';
    }
  });
}
