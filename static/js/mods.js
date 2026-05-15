document.addEventListener('DOMContentLoaded', () => {
  const searchInput = document.getElementById('search-input');
  const versionInput = document.getElementById('version-filter-input');

  function doSearch() {
    const params = new URLSearchParams(window.location.search);
    const val = searchInput?.value.trim() || '';
    if (val) params.set('search', val); else params.delete('search');
    params.set('page', '1');
    window.location.href = '?' + params.toString();
  }

  searchInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') doSearch();
  });

  document.querySelector('.search-btn')?.addEventListener('click', doSearch);

  versionInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const params = new URLSearchParams(window.location.search);
      const v = versionInput.value.trim();
      if (v) params.set('version', v); else params.delete('version');
      params.set('page', '1');
      window.location.href = '?' + params.toString();
    }
  });

  document.querySelectorAll('.dropdown-trigger').forEach(trigger => {
    trigger.addEventListener('change', (e) => {
      const params = new URLSearchParams(window.location.search);
      const parent = trigger.closest('.dropdown-custom');
      const type = parent?.dataset.type;
      if (type === 'filter') params.set('filter', e.detail.value);
      if (type === 'loader') {
        if (e.detail.value) params.set('loader', e.detail.value);
        else params.delete('loader');
      }
      params.set('page', '1');
      window.location.href = '?' + params.toString();
    });
  });
});
