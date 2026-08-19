# Dialogue-scene README showcase visual verification

Verdict: **pass**

- Artifact: `docs/media/dialogue-scene-showcase.webp`; SHA-256
  `234c68fbc458f9281e06e9e3004fb8f9ee6df3a9e93db2578f7e13a148634cbe`;
  82,910 bytes; 1200×833.
- Independent reviewer: a visual-verification subagent distinct from the
  browser-capture producer.
- Result: clean, faithful README rendering below the 250 KiB acceptance limit.
- Bound source verdict:
  `web/output/playwright/dialogue-scene-anime/visual-review.json`, SHA-256
  `94efbbfba6485fadd01cc212db21c5a106e6cc2f29ee375358d90b2b78546239`.
- The source verdict also passed the exact desktop and mobile captures from the
  same production build; those bulky local captures were retired after their
  content digests and compact verdict were retained.

This review attests only to the exact digest-matched WebP above. It does not
upgrade the planned provider-backed recipe or make an art-quality claim about
uncaptured framing-control values.
