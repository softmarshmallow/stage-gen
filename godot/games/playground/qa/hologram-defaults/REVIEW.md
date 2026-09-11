# P83 Hologram defaults — independent visual review

**PASS for the inspected native captures.** Reviewed by `transmission_story`,
who did not implement this shader revision. The treatment clearly reads as a
transmission on both Eira's blue portrait feed and Sera's standing sprite.
This is an independent visual verdict, not user quality approval.

The framed Eira default at strength 0.70 has distinct horizontal scanlines,
cool transmission color, and a brighter passing band. Her eyes, smile, hair,
and research clothing remain identifiable. At 1280 × 900 the effect is obvious
without requiring the viewer to compare an untreated image; the larger close
capture preserves her expression and confines all treatment to the feed.
The separate frame, laboratory, Korean text, and controls remain readable.

Sera at strength 0.90 is strongly separated from the two normal actors by the
cyan projection and scanline contrast. Her face and body silhouette remain
recognizable at both inspected resolutions. Comparing the later sample shows
a bright band at a different vertical position without a large image tear or
displaced facial features. No stray rectangular sprite background, spill onto
neighboring characters, or corruption of the dialogue controls is visible.

No blocking visual artifact or excessive random noise appears in these samples.
The stronger treatment deliberately suppresses much of the original warm skin
and eye color, especially on Sera. Fine face detail is less clear than in the
normal captures, but the eyes and mouth remain legible. These defaults suit an
explicit transmission showcase; they should not be described as preserving
the artwork's original colors unchanged.

## Inspected evidence

The shader digest matches the accompanying [pixel checks](pixel-checks.json):
`e8f5837c45720aeecce90c1b0e7d41372a39d2d6fde6835902709a3b02c2714a`.
Capture digests bind this review even if a later check regenerates the files.

| Capture | SHA-256 |
| --- | --- |
| [Eira default, 1280 × 900](eira-default-1280.png) | `99088ff61a2be9c1e30f81508b021e99cb7399dcd7d6f06af1c9d03aff28c1b2` |
| [Eira close, 2560 × 1800](eira-close-2560.png) | `f86858017e5ee2e62b55cbab139956c3e3cd0444b90ac3fa7dda727452ec611a` |
| [Sera Hologram, 1280 × 900](tactical-hologram_sera-1280.png) | `4621207523a2096644ced5c7b32336ecf2925328d91dd6d7d300b44a146208ce` |
| [Sera Hologram, 2560 × 1800](tactical-hologram_sera-2560.png) | `f6961a6c8637bf03b17dfa00dc7dceea74664e274505083d7e989e7e8a73144f` |
| [Eira normal comparison](eira-normal-1280.png) | `678a4d41922601a4672af405cfacaae5553d30d4705a299bfa2327398ed2cd44` |
| [Eira later sample](eira-later-1280.png) | `c168091a774d8befd97e16c76efe72c3856bd4d7eb4daac562efddb42349827e` |
| [Sera normal comparison](tactical-effect_normal-1280.png) | `d9a1b479abae14825c5539a4d9d1abf1145af5ab3b42f5d6c5088719109deb0e` |
| [Sera later sample](tactical-hologram_sera_later-1280.png) | `37d2ca04e857e334e472fefc391339762e1ccaf9080c7dd05dac8809a4260b74` |

The later samples establish visible variation between captured moments; still
images do not establish how comfortable continuous flicker feels in motion.
The focused native suite and pixel-locality checks were produced by the QA
agent and were not rerun by this reviewer. The earlier P82 composition review
remains historical evidence for its prior shader strength.
