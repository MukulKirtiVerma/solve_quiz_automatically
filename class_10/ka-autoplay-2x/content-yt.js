// Runs inside EVERY frame on youtube.com / youtube-nocookie.com — including
// the embedded player iframe that Khan Academy uses to show its videos.
// Because it shares the extension's origin (not the page's), it can reach
// into that iframe and control the real <video> element directly.

(() => {
  const DEFAULTS = { ka2x_enabled: true, ka2x_speed: 2 };
  let state = { enabled: DEFAULTS.ka2x_enabled, speed: DEFAULTS.ka2x_speed };
  let video = null;
  let endedSent = false;

  function log(...args) {
    console.log('[KA AutoPlay:player]', ...args);
  }

  chrome.storage.sync.get(DEFAULTS, (items) => {
    state.enabled = items.ka2x_enabled;
    state.speed = items.ka2x_speed;
    applyToVideo();
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'sync') return;
    if (changes.ka2x_enabled) state.enabled = changes.ka2x_enabled.newValue;
    if (changes.ka2x_speed) state.speed = changes.ka2x_speed.newValue;
    applyToVideo();
  });

  function applyToVideo() {
    if (!video || !state.enabled) return;
    if (video.playbackRate !== state.speed) {
      try {
        video.playbackRate = state.speed;
      } catch (e) {
        /* ignore */
      }
    }
    if (video.paused) {
      video.play().catch(() => {
        /* autoplay may be blocked until a user gesture happens elsewhere on the page */
      });
    }
  }

  function attach(v) {
    if (video === v) return;
    video = v;
    endedSent = false;
    log('Video element attached');
    applyToVideo();

    video.addEventListener('loadedmetadata', applyToVideo);
    video.addEventListener('playing', applyToVideo);
    video.addEventListener('ratechange', () => {
      if (state.enabled && video.playbackRate !== state.speed) applyToVideo();
    });
    video.addEventListener('ended', () => {
      if (endedSent) return;
      endedSent = true;
      log('Video ended — notifying parent page');
      window.parent.postMessage({ source: 'ka2x', type: 'ended' }, '*');
    });
  }

  function scan() {
    const v = document.querySelector('video');
    if (v) attach(v);
  }

  const observer = new MutationObserver(scan);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  scan();

  // Safety-net: some players briefly reset playbackRate on quality/state
  // changes, so keep re-asserting it.
  setInterval(() => {
    scan();
    applyToVideo();
  }, 2000);
})();
