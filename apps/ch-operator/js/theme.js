// Light/dark theme toggle. Persisted in localStorage; falls back to the
// OS preference (see the prefers-color-scheme block in css/tokens.css) the
// first time the app runs.

const THEME_STORAGE_KEY = "gldOperatorWeb.theme";

function systemPrefersDark() {
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const button = document.getElementById("themeToggleBtn");
  if (button) button.textContent = theme === "dark" ? "Light Mode" : "Dark Mode";
}

export function initTheme() {
  const saved = localStorage.getItem(THEME_STORAGE_KEY);
  const theme = saved || (systemPrefersDark() ? "dark" : "light");
  applyTheme(theme);
}

export function toggleTheme() {
  const current = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
  const next = current === "dark" ? "light" : "dark";
  localStorage.setItem(THEME_STORAGE_KEY, next);
  applyTheme(next);
}
