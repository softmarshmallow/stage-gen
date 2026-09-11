# P85 Keeper intensity — independent visual review

**PASS for the final inspected captures.** The `transmission_story` reviewer
did not implement these VFX changes. This review compares the final images
with the earlier low-intensity compositions and the intermediate candidate;
it does not claim user quality approval or assign an objective intensity score.

The final scene has substantially stronger infernal atmosphere: a broad red
character aura, visible red mist, strongly bending hall columns, and warm
orange ember flecks. The elongated flecks read as airborne sparks rather than
the intermediate candidate's uniform red points. They reinforce the fiery
setting without obscuring the Keeper's face or Korean dialogue. Architecture
remains visible instead of collapsing into a uniformly black backdrop.

Reducing local refraction and held-dialogue barrier strength corrected the
intermediate candidate's distracting doubled eyelids, lips, and jaw. In the
final close-up at 1280 and 2560 widths, the eyes, evil smile, face shape, and
costume remain readable. The wider view retains slight refraction softness,
but no longer has the conspicuous double-face appearance. Stronger instability
is retained in the brief `the_room_refuses` burst; the character remains
recognizable and the environment carries most of the distortion.

The open hall reveal clearly establishes heat and drifting ember shapes before
the Keeper appears. In the inspected `only_a_second` return, the reading room
and four normal characters are warm and clear again. No red aura, embers, or
hall distortion remains, and the Sigh Puff is visible. Dialogue and top controls
remain readable in all inspected story compositions.

## Digest-bound final evidence

All seven capture digests below match [the final capture manifest](after/manifest.json).
That manifest also records source hashes, authored strengths, effect state,
and camera transforms. Its SHA-256 at review time is
`adbd9519b6dad8bd217e02dbc796be17f4f213553523ffd2bdf7b9324ee518d5`.

| Inspected capture | SHA-256 |
| --- | --- |
| [Keeper introduction, 1280 × 900](after/the_keeper-1280.png) | `f3348ac0ee566c507020ee9c80075db2b569dca980c28eeb996ac893ab17ab20` |
| [Keeper close-up, 1280 × 900](after/the_price_of_return-1280.png) | `277641f12954326487790c1eaeda85560fbe654cd75e0a80fa7d9dcb8109cab2` |
| [Resistance burst, 1280 × 900](after/the_room_refuses-1280.png) | `4c60af570a7f74b965724b186e932f1e364fa8a93c58ceac2217184317d22436` |
| [Open hall reveal, 1280 × 900](after/the_unlit_house-open-1280.png) | `8b4283031bdff7a567a46e780987ddcfd1557cf72863ef16a778d73853ac144c` |
| [Keeper introduction, 2560 × 1800](after/the_keeper-2560.png) | `1c3f0c1db19ebb2cf76ee88dcba89643d77cfa2271eab26730dbcad47a84591d` |
| [Keeper close-up, 2560 × 1800](after/the_price_of_return-2560.png) | `08d092d0de6d749d5a9813ddf0d28ed0322f628fe897690073b20e48da865e81` |
| [Clean return with Sigh Puff, 1280 × 900](after/only_a_second-1280.png) | `0170f42019bdc80e913cb7d8b60a1f652b3dd15617b5eaf1c25596e7e1b0b346` |

These are native still-image checks. They do not independently prove world
attachment over a moving camera, ember motion, shake comfort, transition timing,
or lifecycle behavior. Those remain the focused runtime checks' responsibility.
No runtime or artwork files were modified by this reviewer.
