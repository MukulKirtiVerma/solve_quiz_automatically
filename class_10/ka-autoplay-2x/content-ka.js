// Runs in the TOP frame on khanacademy.org pages.
// Responsibilities:
//  1. Click the video "Play" overlay so the embedded YouTube player loads.
//  2. Show a small floating on/off badge (also controllable from the toolbar popup).
//  3. When the youtube.com iframe (content-yt.js) reports the video ended,
//     click Khan Academy's own "Up next" button to advance through the sidebar list.

(() => {
  const DEFAULTS = { ka2x_enabled: true, ka2x_speed: 2 };
  let state = { enabled: DEFAULTS.ka2x_enabled, speed: DEFAULTS.ka2x_speed };
  let advanceTimer = null;

  function log(...args) {
    console.log('[KA AutoPlay]', ...args);
  }

  function loadState(cb) {
    chrome.storage.sync.get(DEFAULTS, (items) => {
      state.enabled = items.ka2x_enabled;
      state.speed = items.ka2x_speed;
      cb && cb();
    });
  }

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'sync') return;
    if (changes.ka2x_enabled) state.enabled = changes.ka2x_enabled.newValue;
    if (changes.ka2x_speed) state.speed = changes.ka2x_speed.newValue;
    updateBadge();
    applyToTopVideo();
  });

  // ---------------- Floating badge ----------------
  let badge;
  function ensureBadge() {
    if (badge && document.body && document.body.contains(badge)) return;
    if (!document.body) return;
    badge = document.createElement('div');
    badge.id = 'ka2x-badge';
    Object.assign(badge.style, {
      position: 'fixed',
      bottom: '16px',
      right: '16px',
      zIndex: 2147483647,
      background: '#1c1c1c',
      color: '#fff',
      padding: '8px 14px',
      borderRadius: '20px',
      fontFamily: '-apple-system, Arial, sans-serif',
      fontSize: '12px',
      boxShadow: '0 2px 10px rgba(0,0,0,.35)',
      cursor: 'pointer',
      userSelect: 'none',
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      lineHeight: '1',
    });
    badge.innerHTML =
      '<span id="ka2x-dot" style="width:8px;height:8px;border-radius:50%;background:#4ade80;display:inline-block;"></span>' +
      '<span id="ka2x-label">Auto 2x: ON</span>';
    badge.title = 'Click to toggle Khan Academy Auto-Play';
    badge.addEventListener('click', () => {
      state.enabled = !state.enabled;
      chrome.storage.sync.set({ ka2x_enabled: state.enabled });
      updateBadge();
    });
    document.body.appendChild(badge);
    updateBadge();
  }

  function updateBadge() {
    if (!badge) return;
    const dot = badge.querySelector('#ka2x-dot');
    const label = badge.querySelector('#ka2x-label');
    if (!dot || !label) return;
    dot.style.background = state.enabled ? '#4ade80' : '#9ca3af';
    label.textContent = `Auto ${state.speed}x: ${state.enabled ? 'ON' : 'OFF'}`;
  }

  // ---------------- Element finders ----------------
  function isVisible(el) {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const style = getComputedStyle(el);
    return style.visibility !== 'hidden' && style.display !== 'none';
  }

  // Finds the big circular "Play" overlay button shown before the video loads.
  // Deliberately avoids the "Watch on YouTube" link, which navigates off-site.
  function findPlayOverlayButton() {
    const nodes = document.querySelectorAll('button, [role="button"], div[tabindex]');
    for (const el of nodes) {
      if (el.closest('a[href*="youtube.com"]')) continue;
      const label = (
        el.getAttribute('aria-label') ||
        el.getAttribute('title') ||
        el.textContent ||
        ''
      ).trim().toLowerCase();
      if (
        label.length &&
        label.length < 40 &&
        /\bplay\b/.test(label) &&
        !label.includes('playlist') &&
        !label.includes('autoplay') &&
        isVisible(el)
      ) {
        return el;
      }
    }
    return null;
  }

  // Finds Khan Academy's "Up next: ..." button/link that advances to the next
  // item in the left-hand playlist.
  function findUpNextButton() {
    const nodes = document.querySelectorAll('button, a, [role="button"]');
    for (const el of nodes) {
      const text = (el.textContent || '').trim().toLowerCase();
      if (text.startsWith('up next') && isVisible(el)) return el;
    }
    return null;
  }

  // ---------------- Direct <video> control ----------------
  // Khan Academy doesn't always embed a YouTube iframe — some videos play
  // through a plain HTML5 <video> element sitting directly in this (top)
  // frame. Handle that case here; the youtube.com iframe case is handled by
  // content-yt.js instead.
  let topVideo = null;
  let topVideoEndedSent = false;

  function applyToTopVideo() {
    if (!topVideo || !state.enabled) return;
    if (topVideo.playbackRate !== state.speed) {
      try {
        topVideo.playbackRate = state.speed;
      } catch (e) {
        /* ignore */
      }
    }
    if (topVideo.paused) {
      topVideo.play().catch(() => {});
    }
  }

  function attachTopVideo(v) {
    if (topVideo === v) return;
    topVideo = v;
    topVideoEndedSent = false;
    log('Direct <video> element found in top frame, applying settings');
    applyToTopVideo();
    v.addEventListener('loadedmetadata', applyToTopVideo);
    v.addEventListener('playing', applyToTopVideo);
    v.addEventListener('ratechange', () => {
      if (state.enabled && v.playbackRate !== state.speed) applyToTopVideo();
    });
    v.addEventListener('ended', () => {
      if (topVideoEndedSent) return;
      topVideoEndedSent = true;
      log('Direct <video> element ended — advancing');
      clearTimeout(advanceTimer);
      advanceTimer = setTimeout(tryAdvance, 1200);
    });
  }

  function scanForTopVideo() {
    const v = document.querySelector('video');
    if (v) attachTopVideo(v);
  }

  // ---------------- Automation ----------------
  // Khan Academy actually inserts the YouTube iframe into the page up front
  // (behind the "Play video" overlay), so we can't use "does a youtube
  // iframe exist" to decide whether we've already clicked play. Instead we
  // track which button elements we've already clicked, in a WeakSet — a
  // fresh element appears for each new video, so this naturally resets as
  // you move through the playlist without needing a time-based debounce.
  const clickedButtons = new WeakSet();

  function tryAutoPlay() {
    if (!state.enabled) return;
    const btn = findPlayOverlayButton();
    if (btn && !clickedButtons.has(btn)) {
      log('Clicking play overlay', btn);
      clickedButtons.add(btn);
      btn.click();
    }
  }

  function tryAdvance() {
    if (!state.enabled) return;
    const btn = findUpNextButton();
    if (btn) {
      log('Video finished — advancing to next item in the list');
      btn.click();
    } else {
      log('No "Up next" button found (end of list, or an exercise is next).');
    }
  }

  // content-yt.js (running inside the YouTube iframe) posts this when the
  // video's `ended` event fires. postMessage works across origins, so no
  // background script / relay is needed.
  window.addEventListener('message', (event) => {
    const data = event.data;
    if (!data || data.source !== 'ka2x') return;
    if (data.type === 'ended') {
      clearTimeout(advanceTimer);
      advanceTimer = setTimeout(tryAdvance, 1200);
    }
  });

  // Khan Academy is a single-page app, so watch the DOM for the play button /
  // next lesson content appearing without a full page navigation.
  const observer = new MutationObserver(() => {
    ensureBadge();
    tryAutoPlay();
    scanForTopVideo();
  });

  function start() {
    observer.observe(document.documentElement, { childList: true, subtree: true });
    loadState(() => {
      ensureBadge();
      tryAutoPlay();
      scanForTopVideo();
    });
    // Safety-net poll in case a mutation is missed, and to keep re-asserting
    // the speed in case the player resets it.
    setInterval(() => {
      ensureBadge();
      tryAutoPlay();
      scanForTopVideo();
      applyToTopVideo();
    }, 2000);
  }

  log('content script loaded on', location.href);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
