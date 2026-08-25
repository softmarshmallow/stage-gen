# Canonical scrolling-preview request

The request selected by `library/games/main.toml` belongs to the canonical demo closure even
though it lives under `examples/`. Only the designated canonical-game curator may edit that
selected request. Concurrent experiments must copy the complete selector, request, and game
library closure under `spikes/game-forks/<owner>-<slug>/`; never point a fork back here by
symlink.

Any selected-request edit must update `main.toml`'s `request_sha256` in the same change. Do not
migrate old schemas or add compatibility aliases: update the fork to the exact current contract
before proposing it for promotion.
