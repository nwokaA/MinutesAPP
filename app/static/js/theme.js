(function () {
  const STORAGE_KEY = 'minutesapp-theme';

  function getPreferredTheme() {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
  }

  applyTheme(getPreferredTheme());

  window.MinutesTheme = {
    get: getPreferredTheme,
    set(theme) {
      localStorage.setItem(STORAGE_KEY, theme);
      applyTheme(theme);
    },
    toggle() {
      const next = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
      this.set(next);
    },
  };

  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('theme-toggle');
    if (btn) {
      btn.addEventListener('click', () => window.MinutesTheme.toggle());
    }
  });
})();
