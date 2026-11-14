# Khan Academy Auto-Play 2x

A small unpacked Chrome extension that watches Khan Academy lessons for you:
it clicks each video's play button, sets your chosen playback speed (2x by
default), and — when a video finishes — clicks Khan Academy's own "Up next"
button to move to the next item in the left-hand lesson list. The result is
hands-free, seamless playback through an entire course/lesson.

## How it works

- `content-ka.js` runs on khanacademy.org pages. It clicks the video's play
  overlay, shows a small on/off badge in the bottom-right corner of the page,
  and clicks "Up next" once a video ends.
- `content-yt.js` runs inside the embedded YouTube player (Khan Academy videos
  play through a YouTube iframe). It sets the real `<video>` element's
  `playbackRate`, keeps it enforced if the player resets it, and reports back
  to the page when the video ends.
- `popup.html` / `popup.js` is the toolbar popup — a simple on/off switch and
  a speed dropdown (1x–3x). Settings are stored with `chrome.storage.sync`,
  so both scripts (and the floating badge) stay in sync instantly.

No background service worker is needed: the two content scripts talk to each
other with `window.postMessage`, which works fine across the iframe boundary.

## Install (load unpacked)

1. Unzip this folder somewhere permanent (don't delete it afterwards — Chrome
   loads the extension directly from these files).
2. Open `chrome://extensions` in Chrome.
3. Turn on **Developer mode** (top-right toggle).
4. Click **Load unpacked** and select the `ka-autoplay-2x` folder.
5. Open any Khan Academy video lesson. You'll see a small "Auto 2x: ON" badge
   in the bottom-right corner — click it (or use the toolbar popup) to toggle
   it off, or to change the speed.

## Notes / limitations

- Chrome's autoplay policy generally requires a user gesture before audio can
  play. Since you have to open the first video's play button yourself (or the
  extension clicks it for you after you've interacted with the page once),
  subsequent videos in the same tab keep that permission and autoplay fine.
- If Khan Academy's page markup changes, the button-finding logic (in
  `findPlayOverlayButton` / `findUpNextButton` inside `content-ka.js`) may
  need small selector tweaks — it currently matches by visible text/aria-label
  ("Play…", "Up next…") rather than brittle CSS classes, so it should keep
  working through most redesigns, but there's no guarantee.
- When the next item in the list is an exercise/quiz rather than a video, the
  extension simply stops (there's no video to auto-play) — it won't attempt
  the exercise for you.
- This is a local, unpacked extension — it isn't published to the Chrome Web
  Store, so it only runs on your machine after the manual "Load unpacked"
  step above.
