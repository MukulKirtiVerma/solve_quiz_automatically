const DEFAULTS = { ka2x_enabled: true, ka2x_speed: 2 };

chrome.storage.sync.get(DEFAULTS, (items) => {
  document.getElementById('enabled').checked = items.ka2x_enabled;
  document.getElementById('speed').value = String(items.ka2x_speed);
});

document.getElementById('enabled').addEventListener('change', (e) => {
  chrome.storage.sync.set({ ka2x_enabled: e.target.checked });
});

document.getElementById('speed').addEventListener('change', (e) => {
  chrome.storage.sync.set({ ka2x_speed: parseFloat(e.target.value) });
});
