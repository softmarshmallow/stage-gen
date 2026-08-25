# Illustration style taxonomy lab

> **Status: active research draft with one reviewed concept-to-asset chain.**
>
> Most inventory terms remain `untested`. One OpenRouter route requested as
> `openai/gpt-image-2` completed concept controls plus character, prop, and
> background extraction controls for `inked_atmospheric_2d_v1`; the result is
> cross-role recognition with reference-dominant continuity, not proof that
> every term in the bundle contributes. Four other profiles stopped after their
> exploratory concept screen. All media remains unapproved research evidence,
> and no generated image has been promoted or committed.
> This page is a research guide and evidence index, not a component, runtime
> schema, prompt template, provider promise, or publication approval.

## Purpose

This lab studies whether image models respond to illustration-style words in a
repeatable and useful way for 2D games. The target is controllable
micro-variance: terms such as `super-deformed`, `shonen manga`, `soft cel
shading`, or `screentone manga` should be more informative than a broad request
such as `Japanese style`.

Game use is wider than actor sprites. A useful style may need to carry across a
cutscene still, dialogue portrait, environment background, prop illustration,
card image, loading screen, UI icon, or effect sheet. Production role is kept
separate from visual style so a model cannot appear to understand a style merely
because it changed the crop or produced a familiar asset layout.

This document has four jobs:

1. inventory candidate words without claiming that they work;
2. derive neutral descriptors from commercially proven 2D-game anchors;
3. define a concept-to-focused-asset experiment plus atomic follow-up tests; and
4. become the single public guide to results that survive review and promotion.

The inventory is deliberately broad, but it is not a claim to enumerate every
illustration tradition or every community's preferred terminology. Terms should
be corrected as stronger sources or practitioners provide better language.

The global [game visual reference and vocabulary](../../game-visual-reference.md)
owns the game-first seed catalog and shared keyword-admission rules. This lab
consumes selected records, adds stronger research, and owns model-specific test
evidence; it does not duplicate or silently mutate the global reference list.

## Repository boundary and lifecycle

This directory is research under `docs/`. It does not extend
`src/stage_gen/components/`, define a recipe, or alter the implemented
[image style anchor](../../image-style-anchor.md). The current runtime anchor has
three coarse modes. This lab may provide evidence for a future vocabulary
revision, but no result changes runtime behavior automatically.

The proposed working lifecycle is:

```text
docs/research/illustration-style-taxonomy/README.md
    text taxonomy, protocol, reviewed findings, and evidence links

out/illustration-style-taxonomy/
    ignored raw candidates, temporary comparisons, and local work products

docs/media/illustration-style-taxonomy/
    only selected, independently reviewed, rights-cleared examples
```

Raw generations remain unreviewed. The current publication checker has no
provenance kind for a direct style-lab generation, so media promotion is blocked
until that kind and its lineage validator exist. Once supported, promotion to
`docs/media/` also requires exact artifact provenance, an independent semantic
verdict, an artifact-specific rights decision, an adjacent sidecar and notice,
and an entry in the generated-media inventory. Cleanup and promotion are
separate from generation.

## Core rule: labels are candidates; observable facets are controls

A label can mix several things:

- a medium or production process;
- a line, shading, palette, or surface treatment;
- a character-design grammar;
- a publishing demographic or market lineage;
- a story genre or affect;
- a production role or layout; and
- a cultural or historical tradition.

Those are not interchangeable. For example:

- `moe` is primarily an affective and cultural label, not a precise rendering
  method;
- `shonen`, `shojo`, `seinen`, and `josei` begin as publishing demographics,
  even though visual dialects can correlate with them;
- `webtoon` is primarily a digital comics format;
- `chibi` or `super-deformed` primarily controls proportion and simplification;
  and
- `cutscene still` is an asset role, not a style.

The lab preserves recognized labels because a model may know them, but any
accepted control must be restated as visible traits. A useful style direction is
therefore faceted rather than a bag of fashionable words:

```text
visual lineage
+ character-design grammar
+ line language
+ shading model
+ palette/value model
+ surface treatment
+ era or production technique, when relevant
+ independently selected asset treatment
```

Pose, camera, crop, subject, costume, setting, and asset role stay outside that
style expression. Experiments freeze them where possible.

## Taxonomy axes

| Axis | What it describes | Example values |
| --- | --- | --- |
| `visual_lineage` | A recognized illustration, comic, print, or painting dialect | `gekiga`, `ukiyo_e`, `ligne_claire` |
| `character_design_grammar` | Proportion, facial construction, and silhouette abstraction | `super_deformed`, `adult_anime_proportions`, `angular_silhouette` |
| `line_language` | Contour weight, continuity, and mark character | `fine_tapered_line`, `bold_contour`, `broken_contour` |
| `shading_model` | How value describes form | `one_band_cel`, `soft_cel`, `continuous_tonal` |
| `color_language` | Palette size, saturation, value key, and color relationships | `limited_palette`, `high_key_pastel`, `jewel_toned` |
| `surface_language` | Visible substrate, print, pigment, or digital texture | `paper_grain`, `analog_cel_texture`, `multi_pass_print_misregistration` |
| `era_technique` | A dated production process rather than decade costume | `hand_painted_cel`, `early_digital_anime` |
| `detail_density` | Frequency and distribution of meaningful detail | `sparse`, `focal`, `uniform`, `dense` |
| `depth_finish` | Pictorial depth and polish, not scene-camera projection | `flat_graphic`, `overlap_depth`, `atmospheric`, `volumetric` |
| `affect` | Intended visual-emotional tendency | `kawaii`, `severe`, `dreamy`, `grotesque_cute` |
| `production_role` | Where the image is used | `cutscene_still`, `environment_background`, `item_icon` |
| `content` | Who or what is depicted | courier, forest, tool, costume, fantasy |
| `composition` | Framing, layout, camera, and pose | full shot, close-up, lateral view, seated pose |

The first nine axes define a style record. `affect` may modify that record, but
an affect word alone does not prove control of rendering style.
`production_role`, `content`, and `composition` are experiment controls or
application context.

Canonical IDs use `lower_snake_case`. Exact prompt spellings and aliases are
also retained because `SD`, `super-deformed`, and `chibi` may not produce the
same model behavior.

## Candidate keyword inventory

All candidates below start with evidence status `untested`. Priority values mean:
`high`, `medium`, or `low` test value; `control` for an intentionally broad
baseline; `context` for a non-style term that should remain fixed; `reject` for
a term that is already unsuitable as a canonical style ID; and `restricted`
for a term that needs extra safety, cultural, or rights review. None of these
priority values claims model recognition.

Priority is also separate from eligibility. Each tested record receives one
hard `term_kind`:

- `style_candidate`: a visible medium, line, shading, color, surface, or
  character-grammar control that may enter atomic testing;
- `diagnostic_label`: an umbrella, demographic, market, affective, or cultural
  shorthand worth probing for model behavior but not canonicalizing without
  decomposition;
- `context_only`: a production role, genre, subject, layout, camera, or pose;
  and
- `reject`: unsafe, product-derived, incoherent, or irrelevant vocabulary.

Only `style_candidate` enters the atomic promotion path. A high-priority
`diagnostic_label` may reveal a useful or stereotyped model association, while a
high-priority `context_only` term may expose a confound; neither is thereby a
style control.

### Contemporary Japanese illustration and publishing labels

| Candidate keyword or alias | Primary class | Expected signal or reason to test | Priority |
| --- | --- | --- | --- |
| `anime`, `anime style`, `Japanese anime illustration` | umbrella label | Broad baseline; likely too underspecified for micro-control | control |
| `manga`, `manga style` | umbrella/format label | May change monochrome treatment or page grammar instead of rendering | control |
| `anime cel rendering`, `cel-shaded anime` | shading and production family | Flat fills, crisp contours, discrete shadow shapes | high |
| `hard cel shading` | shading model | Sharp one- or two-band shadow boundaries | high |
| `soft cel shading` | shading model | Cel structure with selectively softened transitions | high |
| `flat-color anime` | shading model | Minimal modeled form; must not merely look unfinished | high |
| `multi-band cel shading` | shading model | Several discrete tone regions without continuous gradients | high |
| `cel-painterly hybrid`, `painterly cel` | rendering compound | Cel structure plus selective modeled brush rendering | high |
| `painterly anime` | rendering compound | Anime design grammar with continuous painted form | high |
| `semi-realistic anime` | design/rendering compound | More grounded anatomy and planes; too broad unless decomposed | medium |
| `monochrome manga ink` | medium/line family | Black ink, value grouping, no page-layout requirement | high |
| `screentone manga` | surface/shading family | Mechanical tone textures with inked contours | high |
| `halftone manga` | surface/shading alias | Possible partial alias of `screentone manga` | medium |
| `shonen manga visual dialect`, `shounen manga` | publishing dialect | Test angularity, bold contour, graphic contrast, and motion-language leakage | high |
| `shojo manga visual dialect`, `shoujo manga` | publishing dialect | Test fine line, decorative abstraction, eye treatment, and soft/open value grouping | high |
| `seinen manga visual dialect` | publishing dialect | Diverse adult-male market shorthand; likely conditional | medium |
| `josei manga visual dialect` | publishing dialect | Diverse adult-women market shorthand; likely conditional | medium |
| `kodomomuke`, `kodomo manga` | publishing dialect | Simplification and bright readability; may leak child subject matter | medium |
| `gekiga` | comic movement/dialect | Grounded anatomy, dramatic black shapes, texture, cinematic severity | high |
| `moe`, `moe-kei` | affect/design shorthand | Test soft facial grammar and endearing affect; not a rendering method | high |
| `kawaii` | affect | Rounded, low-threat, compact, bright or pastel tendencies; very broad | medium |
| `yuru-kawa`, `yurukawa` | affect/line compound | Loose, relaxed, understated cute treatment | medium |
| `kimo-kawaii` | affect compound | Grotesque-cute; likely subject leakage | low |
| `yume-kawaii` | affect/aesthetic compound | Dreamy pastel cute; likely fashion and mood leakage | low |
| `yami-kawaii` | affect/aesthetic compound | Cute-dark shorthand; safety-sensitive motif leakage makes it non-priority | restricted |
| `bishoujo`, `bishōjo` | market/character archetype | Attractive feminine character category, not a rendering style; any diagnostic test requires a clearly adult fixed subject | context |
| `bishounen`, `bishōnen` | market/character archetype | Elegant or androgynous masculine character category, not a rendering style; any diagnostic test requires a clearly adult fixed subject | context |
| `chibi` | character-design grammar | Large head, compact body, simplified extremities and features | high |
| `super-deformed`, `super deformed` | character-design grammar | Extreme deliberate proportion deformation; more precise than `SD` | high |
| `SD` | ambiguous alias | Could mean super-deformed or a technical abbreviation; test as an exact alias | high |
| `mini-character`, `mini character`, `mini-chara` | design/production shorthand | Compact variant, possibly less extreme than chibi | high |
| `puchi-character`, `petit character` | design/production shorthand | Extra-small collectible or mascot variant; weakly standardized | low |
| `kawaii mascot` | affect/design/role compound | Iconic compact forms; mixes anatomy and asset purpose | high |
| `yuru mascot` | affect/design compound | Loose, friendly municipal-style mascot shorthand; likely subject-heavy | medium |
| `heta-uma` | drawing aesthetic | Deliberately awkward or naive but compelling; risk of merely low quality | high |
| `gag manga` | genre/dialect compound | Deformation and graphic reaction language; genre confound | low |
| `visual novel illustration` | production dialect | Polished character-focused game illustration; broad | high |
| `visual novel character sprite`, `tachie` | production role/dialect | Standing character treatment; layout is not style | context |
| `visual novel event CG`, `event CG` | production role/dialect | Narrative still role; polish and composition do not define a style | context |
| `light novel illustration` | publishing dialect | Character-led polished illustration with white-space or cover/interior conventions | high |
| `otome game illustration` | market/production dialect | Refined character presentation; may change subject and framing | high |
| `anime key visual` | production role/dialect | Ensemble or promotional finish; layout-heavy | medium |
| `anime film background` | production role/dialect | Environment role; test explicit paint, depth-plane, and surface facets instead | context |
| `mobile RPG character illustration` | market/production dialect | High-finish game character rendering; broad and trend-sensitive | high |
| `mobile game card illustration`, `gacha card art` | market/production dialect | Card role and monetization context; dense effects or framing would be role leakage | context |
| `JRPG character illustration` | market/genre umbrella | Broad negative control; should not become canonical alone | control |
| `mecha anime illustration` | subject/genre compound | Mechanical subject more than style | context |
| `magical-girl illustration` | subject/genre compound | Costume and genre more than rendering | context |
| `kemono illustration` | subject morphology | Animal-humanoid design, not rendering style | context |
| `retro anime` | era umbrella | Too broad; use only as a negative control | control |
| `1970s shojo manga` | era/publishing dialect | Era plus dialect may be more separable than decade alone | medium |
| `1980s hand-painted cel anime` | era/technique compound | Analog cel edges, flat paint, period color and line tendencies | high |
| `1990s hand-painted cel anime` | era/technique compound | Compare directly with 1980s and early digital | high |
| `early-2000s digital anime` | era/technique compound | Early digital color and compositing tendencies; avoid costume confound | high |
| `contemporary digital anime` | era/technique baseline | Current broad production baseline, not an endpoint | medium |
| `four-panel manga`, `4-koma`, `yonkoma` | layout format | Sequential layout, not illustration style | context |
| `doujinshi` | publishing mode | Self-publishing category, not style | reject |
| `sakuga` | animation craft | Motion/performance term, not a still-image style | reject |

`Moe` stays in the inventory because users and models may employ it as a visual
shorthand, but research describes it primarily as a response to fictional
characters rather than one fixed style. The experiment must therefore test the
bare word and a separately authored observable-trait expansion. A bare-word
success would establish model behavior, not settle the cultural definition.

### Japanese historical painting, print, and craft lineages

| Candidate keyword or alias | Primary class | Expected signal or caveat | Priority |
| --- | --- | --- | --- |
| `ukiyo-e` | print/genre lineage | Flat shape, carved contour, period print color; likely costume and subject leakage | high |
| `Japanese woodblock print` | medium/technique | Broader process description for comparison with `ukiyo-e` | high |
| `moku-hanga` | woodblock technique | Compare exact loanword with generic process wording | medium |
| `nishiki-e` | multicolor woodblock print lineage | Rich multicolor woodblock print treatment; may default to Edo subject matter | medium |
| `shin-hanga` | modern print movement | Polished collaborative-print finish, often atmospheric | high |
| `sosaku-hanga`, `sōsaku-hanga` | creative-print movement | Ideology of self-drawing, self-carving, and self-printing; rough finish is not guaranteed | medium |
| `Rinpa`, `Rimpa` | decorative painting lineage | Bold abbreviated natural motifs, pattern, rich pigment, metallic grounds | high |
| `yamato-e` | classical painting lineage | Stylized figures, bright pigment, cloud-divided space; subject leakage likely | medium |
| `Nihonga` | modern Japanese painting tradition | Mineral-pigment-like surface and traditional material cues; internally diverse | high |
| `yoga`, `yōga` | modern Western-style painting category in Japan | Historical contrast to `Nihonga`; internally diverse and not one renderer | medium |
| `sumi-e` | ink-painting shorthand | Monochrome brush economy and tonal wash | high |
| `suibokuga` | ink-wash painting | Close alias test against `sumi-e` | high |
| `nanga`, `bunjinga` | literati painting lineage | Calligraphic brush and learned landscape conventions | medium |
| `Maruyama-Shijo`, `Shijo school` | painting lineage | Naturalistic observation with decorative brush economy | medium |
| `Tosa-school painting` | courtly painting lineage | Fine line, bright opaque color, classical subjects | low |
| `Kano-school painting` | ink/decorative lineage | Strong brush, monochrome-to-gold decorative range; very broad | low |
| `kirie` | cut-paper technique | Crisp silhouette, negative space, layered paper edges | high |
| `tarashikomi` | wet-in-wet technique | Pooled pigment or ink blooming inside forms | medium |
| `mokkotsu` | outline-free method | Boneless color or ink forms without enclosing contour | medium |
| `gofun pigment` | material/surface cue | Opaque shell-white-like highlights and matte surface | low |
| `emaki`, `emakimono` | narrative handscroll format | Composition/format more than style | context |
| `kamishibai illustration` | paper-theater role | Bold readable narrative panels; role and era compound | medium |
| `ehon illustration` | picture-book form | Too broad without period, medium, or line qualifiers | control |
| `bijin-ga` | subject genre | Pictures of beauties, not a generic style | context |
| `kacho-ga`, `kachō-ga` | subject genre | Bird-and-flower subject, not generic style | context |
| `meisho-e` | subject genre | Famous-place imagery, not generic style | context |

### Korean illustration and painting labels

| Candidate keyword or alias | Primary class | Expected signal or caveat | Priority |
| --- | --- | --- | --- |
| `manhwa` | comics umbrella | Diagnostic baseline; not one style | control |
| `webtoon` | digital-comic format | Digital publication category; vertical scrolling and full color are common, not universal | control |
| `full-color vertical webtoon` | format/production compound | Tests common mobile-panel conventions; still not a rendering style | medium |
| `Korean webtoon rendering` | market shorthand | Test model stereotype, not cultural truth | high |
| `romance-fantasy webtoon` | genre/market compound | Polished figures, fashion, glow; strong costume/content confound | medium |
| `action webtoon` | genre/market compound | Contrast, modeled bodies, effects; strong action/layout confound | medium |
| `sunjeong manhwa` | publishing category | Romance/female-market lineage; likely content leakage | medium |
| `sonyeon manhwa` | publishing category | Youth/boys-market lineage; likely action leakage | medium |
| `minhwa` | broad folk-painting category | Internally diverse and historically constructed; test named subgenres and visible facets | high |
| `sumukhwa` | ink painting | Korean ink-painting shorthand; compare with generic ink wash | high |
| `chaekgeori` | books-and-things still-life genre | Broad books-and-objects imagery; subject-bound but useful for prop scenes | high |
| `chaekgado` | bookshelf/cabinet composition | Structured shelving or cabinet arrangement; a narrower composition than `chaekgeori` | medium |
| `munbangdo` | scholar-studio genre | Objects of learning; subject-bound | medium |
| `munjado` | character/rebus folk painting | Written characters and rebus relationships are essential; requires a dedicated text-compatible, culturally reviewed carrier | restricted |
| `dancheong` | architectural polychrome system | Material, symbolic, structural, and religious context; not a generic pattern modifier | restricted |
| `jinchae`, `jinchaehwa` | Korean heavy-color painting | Dense mineral-like color and layered opaque finish; terminology and lineage need practitioner review | medium |
| `jingyeong sansuhwa`, `true-view landscape` | landscape tradition | Subject-bound | low |
| `pungsokhwa` | genre painting | Everyday-life subject genre | low |
| `dansaekhwa`, `tansaekhwa` | modern art movement | Material monochrome abstraction; low priority for game assets | low |

`Webtoon` must not be promoted as a style merely because a model emits a
vertical comic. Full color and vertical scrolling are common production
conventions, not universal requirements; any claimed rendering dialect needs
separate visible evidence.

### Chinese illustration and painting labels

| Candidate keyword or alias | Primary class | Expected signal or caveat | Priority |
| --- | --- | --- | --- |
| `manhua` | comics umbrella | Diagnostic baseline; not one style | control |
| `donghua` | animation umbrella | Medium/industry label, not a still style | control |
| `guoman` | domestic-sector shorthand | Market label, not stable visual definition | control |
| `guofeng` | fluid contemporary discourse/marketing label | Heritage cues may appear through pattern, palette, costume, or setting rather than rendering | high |
| `gufeng` | fluid contemporary ancient-style label | Often more costume and setting than rendering; not a fixed tradition | high |
| `guochao` | fluid contemporary marketing/design label | Graphic, fashion, and branding associations; not a fixed historical tradition | medium |
| `gongbi` | meticulous brush method | Controlled fine line, layered color, exact detail | high |
| `xieyi` | expressive/freehand method | Economical, spontaneous brush gestures | high |
| `baimiao` | line method | Plain ink line without shading | high |
| `mogu` | outline-free method | Boneless color forms without ink contour | medium |
| `shuimo`, `Chinese ink wash` | ink-wash tradition | Tonal ink, brush economy, paper reserve | high |
| `qinglu shanshui`, `qinglü shanshui`, `blue-green landscape painting` | landscape/color lineage | Mineral blue-green color; subject-bound | medium |
| `gongbi zhongcai`, `meticulous heavy-color painting` | method/color compound | Fine controlled line with layered saturated color | medium |
| `jiehua`, `ruled-line painting` | architectural drawing method | Ruled-line precision for buildings; strongly subject-bound | medium |
| `shan shui` | landscape genre | Subject, not general style | context |
| `Chinese ink-wash animation` | animation lineage | Economical brush forms, tonal wash, reserved paper, and frame-to-frame transformation cues | medium |
| `Dunhuang mural-inspired` | historical corpus reference | Mineral color and mural surface; requires culturally careful review | medium |
| `Tang mural-inspired` | era/corpus shorthand | Broad and subject-prone | low |
| `Chinese paper-cut` | folk medium | Strong positive/negative silhouettes and limited flat color | high |
| `nianhua` | New Year print tradition | Folk-print surface and festive iconography; subject leakage likely | medium |
| `lianhuanhua` | sequential picture-book form | Format and historical production shorthand | low |
| `yuefenpai` | calendar-poster genre | Polished period commercial illustration; layout/subject bound | medium |
| `Q-version`, `Q-style` | chibi-like market shorthand | Compare with `chibi` and `super-deformed`; exact alias may be unstable | medium |
| `wuxia`, `xianxia`, `xuanhuan` | narrative genres | Setting, costume, and effects rather than style | context |

### Global comics, publishing, and commercial-illustration labels

These labels are worth knowing, but market and format labels remain conditional
until their visible effects are isolated.

- Comics lineages: `American comic book`, `superhero comic`, `Golden Age comic`,
  `Silver Age comic`, `pulp comic`, `newspaper comic strip`, `Sunday comic`,
  `underground comix`, `alternative comic`, `indie comic`, `graphic novel`,
  `noir graphic novel`, `woodcut novel`, `European comic`, `Franco-Belgian
  comic`, `bandes dessinees`, `ligne claire`, `Marcinelle school`, `Italian
  fumetti`, `British adventure comic`, `editorial cartoon`, `caricature`.
- Book and editorial roles: `children's picture-book illustration`, `nursery-book
  illustration`, `chapter-book illustration`, `middle-grade cover
  illustration`, `young-adult cover illustration`, `storybook illustration`,
  `fairy-tale illustration`, `folk-tale illustration`, `spot illustration`,
  `editorial illustration`, `fashion illustration`, `botanical illustration`,
  `scientific illustration`, `technical illustration`, `infographic
  illustration`, `travel-poster illustration`, `pulp-magazine cover`,
  `mid-century editorial illustration`.
- Game and entertainment roles: `concept art`, `character concept art`,
  `environment concept art`, `prop concept art`, `key art`, `splash art`,
  `cutscene illustration`, `loading-screen illustration`, `collectible-card
  illustration`, `quest illustration`, `chapter illustration`, `map
  illustration`, `matte-painted background`, `parallax background`, `UI
  illustration`, `game icon`, `effect illustration`.

### Medium and production-process keywords

These are often more controllable than cultural umbrellas:

- Drawing: `graphite pencil`, `colored pencil`, `charcoal`, `chalk`, `wax
  crayon`, `oil pastel`, `soft pastel`, `marker illustration`, `pen and ink`,
  `brush and ink`, `ink wash`, `scratchboard`.
- Paint: `transparent watercolor`, `opaque watercolor`, `gouache`, `tempera`,
  `acrylic painting`, `oil painting`, `fresco`, `airbrush`, `digital painting`,
  `digital airbrush`, `matte painting`.
- Print: `woodcut`, `linocut`, `engraving`, `etching`, `lithograph`,
  `screenprint`, `silkscreen`, `stencil duplicator print`, `stencil print`, `monotype`,
  `newsprint comic`, `two-color print`, `four-color process print`.
- Constructed media: `paper-cut illustration`, `layered paper cutout`,
  `collage`, `photomontage`, `silhouette cutout`, `shadow-puppet illustration`,
  `stained-glass illustration`, `mosaic illustration`, `tapestry-like
  illustration`, `embroidered illustration`, `felt-craft illustration`,
  `papercraft`, `clay-like illustration`.
- Digital/game media: `flat vector illustration`, `geometric vector
  illustration`, `pixel art`, `1-bit pixel art`, `indexed-palette pixel art`,
  `dithered pixel art`, `high-resolution pixel art`, `isometric pixel art`,
  `voxel art`, `low-poly render`, `toon-shaded 3D`, `2D-3D hybrid`,
  `pre-rendered sprite`, `paper-cut render`, `clay-like render`.

`Risograph` is a product-derived name. It may be retained in private search
notes as an alias for model-diagnostic research, but repository prompts and
canonical profiles use `stencil duplicator print`, `stencil print grain`, and
`multi-pass print misregistration` instead.

### Line and mark-making keywords

- Contour presence: `lineless`, `contourless`, `selective outlines`, `broken
  contour`, `enclosed contour`, `colored lineart`, `dark contour`.
- Line weight: `monoline`, `uniform thin line`, `fine tapered line`,
  `variable-width ink`, `bold contour`, `heavy black outline`, `hairline
  contour`.
- Line character: `clean line art`, `rough line art`, `sketchy line art`, `loose
  pencil`, `construction sketch`, `clean ink`, `brush ink`, `calligraphic line`,
  `dry-brush line`, `ink feathering`, `wobbly hand-drawn line`, `angular line`,
  `rounded line`.
- Tone marks: `hatching`, `crosshatching`, `stipple`, `scribble shading`,
  `screentone`, `halftone dots`, `pixel clusters`, `ordered dithering`, `error
  diffusion dithering`, `paint daubs`, `palette-knife marks`.

### Shading and rendering keywords

- Flat families: `unshaded flat color`, `flat fill`, `value-blocked`, `one-band
  cel shading`, `two-band cel shading`, `multi-band cel shading`, `hard cel
  shading`, `soft cel shading`.
- Continuous families: `gradient shading`, `soft airbrush shading`, `continuous
  tonal rendering`, `painterly modeled shading`, `semi-realistic modeling`,
  `luminous glazing`, `volumetric shading`.
- Mark-based families: `crosshatched shadows`, `stippled shadows`, `screentone
  shadows`, `ink-wash shadows`, `dry-brush shadows`.
- Lighting modifiers: `flat ambient light`, `soft diffuse light`, `directional
  key light`, `rim light`, `backlight`, `high-key lighting`, `low-key lighting`,
  `emissive glow`, `graphic cast shadows`, `no photographic depth of field`.

Lighting is a style facet only when it describes the image treatment. It does
not replace a scene-lighting or camera contract.

### Palette and value keywords

- Palette size: `one-bit monochrome`, `grayscale`, `duotone`, `tritone`,
  `four-color palette`, `eight-color palette`, `sixteen-color palette`,
  `limited palette`, `indexed palette`, `full-color`.
- Value: `high-key`, `low-key`, `high contrast`, `low contrast`, `compressed
  values`, `graphic black shapes`, `pale value range`.
- Saturation and family: `pastel`, `muted`, `desaturated`, `high saturation`,
  `candy-colored`, `jewel-toned`, `earth-toned`, `neon-accented`, `fluorescent`,
  `sepia`, `faded print palette`.
- Relationships: `monochromatic`, `analogous palette`, `complementary palette`,
  `split-complementary palette`, `triadic palette`, `warm-biased`,
  `cool-biased`, `warm-cool split`, `chromatic shadows`, `selective color`,
  `color-blocked`.

### Surface and texture keywords

- Substrate: `smooth digital surface`, `paper grain`, `hot-press paper`,
  `cold-press paper`, `rough watercolor paper`, `canvas tooth`, `newsprint`,
  `fibrous handmade paper`, `aged paper`.
- Pigment and paint: `watercolor bloom`, `watercolor backrun`, `pigment
  granulation`, `gouache dry brush`, `chalk dust`, `pastel grain`,
  `colored-pencil tooth`, `crayon wax`, `paint impasto`, `matte paint`, `glossy
  airbrush`.
- Print and capture: `woodgrain`, `uneven ink coverage`, `ink bleed`,
  `screenprint distress`, `stencil print grain`, `multi-pass print misregistration`, `halftone
  screen`, `screentone`, `analog cel texture`, `film grain`, `registration
  marks`.
- Digital finish: `clean raster`, `subtle digital grain`, `clustered noise`,
  `soft bloom`, `crisp edges`, `anti-aliased edges`, `pixel-sharp edges`.

### Character proportion, face, and shape-language keywords

These affect style strongly but apply primarily to characters. They should not
be used to judge environment-only transfer.

- Measured proportion: `2-head-tall`, `2.5-head-tall`, `3-head-tall`,
  `4-head-tall`, `5-head-tall`, `6-head-tall`, `7.5-head-tall`, `8-head-tall`,
  `big-head small-body`, `compact proportions`, `elongated proportions`,
  `heroic proportions`, `adult anime proportions`.
- Build and silhouette: `rounded silhouette`, `angular silhouette`, `geometric
  shape language`, `organic shape language`, `soft shape language`, `chunky`,
  `stocky`, `slender`, `lanky`, `long-legged`, `top-heavy`, `bottom-heavy`,
  `doll-like`, `mascot-like`, `silhouette-led design`.
- Facial grammar: `oversized irises`, `small irises`, `round eyes`,
  `almond-shaped eyes`, `narrow eyes`, `single eye highlight`, `dense eye
  highlights`, `heavy eyelash emphasis`, `minimal nose`, `simplified mouth`,
  `pointed chin`, `rounded jaw`, `flat facial planes`, `modeled facial planes`,
  `doll-like face`, `graphic face`.
- Simplification: `simplified hands and feet`, `anatomically articulated hands`,
  `stubby limbs`, `slender limbs`, `broad-shouldered silhouette`, `reduced facial
  detail`, `iconic expression shapes`.

### Detail, depth, and finish keywords

- Detail: `minimalist`, `sparse detail`, `focal detail`, `uniform detail`, `dense
  detail`, `maximalist`, `ornamental`, `decorative`, `intricate`, `filigree`,
  `low-frequency shapes`, `high-frequency detail`.
- Finish: `rough sketch`, `clean finish`, `polished illustration`, `graphic
  finish`, `painterly loose finish`, `flat finish`, `semi-flat finish`,
  `luminous finish`, `matte finish`, `glossy finish`, `crisp finish`, `grainy
  finish`.
- Pictorial depth: `no depth cues`, `overlap depth`, `value-separated depth`,
  `atmospheric depth`, `linear-perspective depth`, `flattened decorative space`,
  `volumetric depth`, `layered theatrical depth`.
- Optical treatment: `no blur`, `soft focus`, `dreamy bloom`, `vignette`,
  `chromatic fringe`, `depth-of-field effect`, `motion smear`. These must not be
  confused with runtime camera or animation behavior.

### Art-history and design-movement keywords

These can be productive for cutscenes, environments, cards, UI, or promotional
art. They remain historically broad and should be paired with visible traits
rather than treated as magic words.

- Decorative and graphic: `Art Nouveau`, `Jugendstil`, `Art Deco`, `Arts and
  Crafts`, `Bauhaus`, `Constructivist`, `De Stijl`, `Suprematist`, `Futurist`,
  `Op Art`, `Pop Art`, `Psychedelic poster`, `mid-century modern`, `brutalist
  graphic design`, `retro travel poster`.
- Painterly and expressive: `Impressionist`, `Post-Impressionist`,
  `Expressionist`, `German Expressionist woodcut`, `Symbolist`, `Romantic`,
  `Rococo`, `Baroque`, `Neoclassical`, `Pre-Raphaelite`, `naive art`, `folk
  modernist`.
- Narrative and manuscript: `medieval illuminated manuscript`, `Byzantine icon`,
  `Persian miniature`, `Mughal miniature`, `Indian miniature painting`,
  `Ethiopian manuscript illumination`, `folk woodcut`, `paper theater`,
  `shadow-puppet`, `storybook engraving`.
- Folk and regional traditions requiring careful cultural review: `Mithila
  painting`, `Madhubani painting`, `Warli painting`, `Pattachitra`, `Kalamkari`,
  `Korean minhwa`, `Mexican retablo`, `papel picado`, `Dong Ho woodblock print`,
  `Chinese paper-cut`, `Japanese kirie`.

Heritage terms may carry subject, religious, ceremonial, or geographic meaning
that cannot be reduced to surface decoration. They require stronger sourcing
and review before canonical use.

### Aesthetic and story bundles that must remain contextual

The following words can create visually obvious changes, but they mix genre,
setting, fashion, mood, palette, and props. They are useful content direction,
not clean style controls:

`whimsical fantasy`, `heroic fantasy`, `dark fantasy`, `cozy fantasy`, `gothic
fantasy`, `fairy-tale`, `storybook fantasy`, `science fantasy`, `steampunk`,
`dieselpunk`, `cyberpunk`, `solarpunk`, `biopunk`, `retrofuturism`, `Afrofuturism`,
`cottagecore`, `fairycore`, `dreamcore`, `weirdcore`, `vaporwave`, `synthwave`,
`Y2K`, `dark academia`, `pastel goth`, `gothic`, `cute`, `cool`, `cinematic`,
`beautiful`, `stylized`, `premium`, `high quality`.

The quality fillers at the end should not enter canonical style records.

### Production-role vocabulary kept outside style

The experiment must name a role explicitly without treating it as style:

- Character and dialogue: `standing character illustration`, `tachie`,
  `dialogue portrait`, `bust portrait`, `visual-novel character sprite`,
  `expression portrait`, `cut-in illustration`, `UI portrait`, `avatar icon`,
  `paper-doll layer`, `costume layer`.
- Narrative and promotional: `event illustration`, `event CG`, `story still`,
  `cutscene still`, `anime key visual`, `promotional key art`, `gacha splash
  illustration`, `collectible-card illustration`, `loading-screen
  illustration`, `light-novel cover illustration`, `light-novel interior
  illustration`, `chapter illustration`.
- World and objects: `background painting`, `environment illustration`,
  `visual-novel background`, `parallax background`, `prop illustration`, `item
  card`, `inventory icon`, `skill icon`, `quest illustration`, `map
  illustration`, `tileable texture`, `decorative UI frame`, `emblem`, `badge`,
  `sticker`.
- Production sheets: `character sheet`, `model sheet`, `expression sheet`,
  `effect sheet`, `asset sheet`, `pixel sprite`, `sprite sheet`, `storyboard
  frame`, `animatic frame`.

Ambiguous words must be expanded in records: `sprite` can mean a pixel asset or
a visual-novel standing character; `CG` can mean computer graphics generally or
a visual-novel event illustration; `key visual` and `key art` are roles; `SD`
has several technical meanings.

## Terms excluded from canonical style records

- Geography alone: `Japanese`, `Chinese`, `Korean`, `Asian`, `East Asian`.
- Generic medium alone: `2D`, `digital art`, `illustration`, `anime`, `manga`.
- Business or platform tier: `mobile game`, `AAA`, `indie`, `premium`.
- Story genre alone: `romance`, `action`, `horror`, `fantasy`, `science fiction`,
  `isekai`, `wuxia`, `xianxia`.
- Subject or archetype alone: `samurai`, `shrine maiden`, `magical girl`,
  `idol`, `mecha`, `yokai`, `kemono`, `kemonomimi`, `ikemen`.
- Composition or pose: `full body`, `close-up`, `three-quarter view`,
  `isometric`, `Dutch angle`, `attack pose`, `running`, `neutral pose`.
- Release or animation craft: `OVA`, `sakuga`.
- Quality filler: `masterpiece`, `best quality`, `official art`, `trending`.
- Any named living artist, studio, franchise, character, game, proprietary asset
  pack, or `in the style of ...` construction.

`Photorealistic`, `live-action`, `cinematic photography`, and `realistic 3D
render` are retained only as optional boundary controls. They are not part of
the initial 2D-game illustration queue.

## Primary proof target: concept-to-asset style retention

The primary study is not a gallery of isolated keyword outputs. It tests this
chain:

```text
commercially proven 2D game research anchor
    -> neutral, observable descriptor profile D
    -> original concept scene C
    -> focused character, prop, or background asset E
    -> blinded consistency and control verdict
```

The intended claim is deliberately narrow: under the recorded model and date,
an exact neutral descriptor profile controlled an original concept and helped
retain the same visual language in a focused derivative asset. Four links must
be evaluated separately:

- `D -> C`: the concept expresses the pre-registered descriptors;
- `C -> E`: the focused asset preserves the selected content identity;
- `D -> E`: the focused asset independently expresses the descriptors; and
- `C <-> E`: reviewers judge both artifacts compatible with one original game
  art bible.

A famous game can be a factual research anchor, but it is not an admissible
generation keyword in this repository. The game name stops at the research
table. It must not appear in a provider prompt, provider-bound filename,
provider metadata, style ID, or submitted reference image. Screenshots and
other proprietary game art are not submitted to the model. This follows the
repository's [OSS and IP policy](../../oss-ip.md) and means this lab does **not**
claim to test whether a model recognizes a named game directly. It tests the
more reusable and redistributable descriptor set derived from observation.

### Commercial research-anchor cohort

This cohort is a purposive style-coverage sample, not a universal sales ranking.
Unit sales, players, downloads, revenue, awards, and cultural prominence are
different evidence types and must never be combined into one leaderboard. A
game enters the primary cohort only when:

1. a developer, publisher, platform owner, audited filing, or strong secondary
   report supports its commercial or iconic significance;
2. 2D or 2D-dominant art materially defines its player-facing presentation;
3. its observable treatment adds a useful contrast to the cohort; and
4. at least two analysts independently code its style facets and reconcile
   disagreements.

Each anchor records:

```text
research_anchor_id
game_name
anchor_version_or_asset_family
evidence_type
evidence_value
evidence_as_of
evidence_source
2d_relevance
observed_asset_roles
line_facets
shading_facets
color_facets
surface_facets
character_grammar
analyst_1
analyst_2
agreement_notes
neutral_profile_id
```

The initial sourced cohort and its analyst-coded profiles appear below; the
experiment protocol follows them. Commercial evidence proves only that an
anchor is worth studying; the neutral facet descriptions are analyst
observations, not claims made by the cited sales source.

The following research pool is intentionally broader than the first generation
wave. Every candidate profile remains `untested`.

| ID | Evidence-only game anchor and commercial signal | Neutral visual-analysis hypothesis | Useful concept-to-asset transfer | Candidate profile ID |
| --- | --- | --- | --- | --- |
| `a01` | **Terraria** — [70 million copies as of May 2026](https://steamcommunity.com/games/105600/announcements/detail/662735945909403987), developer announcement | Modern detail-dense side-view pixel art; crisp clusters; selective contours; tile-aligned terrain; biome-specific saturated palettes; layered scenic depth | Scene to player, tool, tile, and parallax biome; preserve effective pixel size and material clusters | `modern_tile_sideview_pixel` |
| `a02` | **Stardew Valley** — [over 41 million copies as of December 2024](https://www.stardewvalley.net/press/), developer press page | Modern low-resolution oblique top-down tile art; compact sprites; warm seasonal palettes; restrained per-object shading; high material readability | Farm scene to world-scale resident sprite, hand tool, crop, and modular tiles; larger dialogue portraits are a separate later system | `warm_tile_pixel` |
| `a03` | **Castle Crashers** — [over 20 million copies by 2019](https://blog.thebehemoth.com/category/castle-crashers/page/23/), developer post | Heavy black contour; bright flat fills; sparse cel-like shadow; compact geometric characters; clean vector-like edges; layered flat scenery | Battle scene to character, weapon, effect, and castle plate; pin original/remastered versus later redesigns before testing | `flat_bold_cartoon` |
| `a04` | **Hollow Knight** — [about 15 million copies reported from a 2025 developer interview](https://www.nintendolife.com/news/2025/08/hollow-knight-has-now-sold-almost-15-million-copies), strong secondary source | Hand-drawn 2D; clean dark contours; pale focal silhouettes; restrained character color; dark layered environments; soft atmospheric depth | Exploration scene to an original, non-mask-like traveler, relic, foreground prop, and background plate; preserve value separation | `inked_atmospheric_fantasy` |
| `a05` | **Dead Cells** — [more than 11 million players](https://motiontwin.com/), current developer page; player count, not unit sales | High-resolution pixel-rendered 2D; decisive silhouettes; dense environment texture; saturated emissive accents; strong depth separation; substantially 3D-derived animation | Combat scene to player, weapon, effect sprite, and environment module; separate runtime particles and glow from sprite style | `luminous_pixel_rendered_action` |
| `a06` | **Cuphead** — [over 3 million copies in the developer's 2018 milestone](https://studiomdhr.com/cuphead-goes-triple-platinum/); its [press kit](https://studiomdhr.com/press-kits/) documents the production treatment | Rubber-hose character grammar; variable hand-inked contour; flat cel color; watercolor environment; analog capture texture | Scene to character, prop, effect, and watercolor background; role surfaces differ but must retain one analog art direction | `analog_cel_watercolor` |
| `a07` | **Balatro** — [over 5 million units as of January 2025](https://www.playstack.com/news/balatro-5-million-copies-sold/), publisher announcement | Low-resolution card/UI raster art; hard-edged symbols; dithered texture; saturated limited colors; scanline and chromatic-fringe post-processing | Card-table system to card vignette, token, pack, icon, and abstract field; specialist UI track, not the main scene benchmark | `low_resolution_card_ui` |
| `a08` | **Shovel Knight: Treasure Trove** — [over 2 million copies by 2018](https://old.yachtclubgames.com/2018/04/two-million-copies-of-shovel-knight-sold/), developer breakdown | 8-bit-inspired modern pixel art; small deliberate palette groups; crisp clusters; chunky silhouettes; discrete shading; modern animation and parallax | Side-view concept to an original non-horned player, non-shovel tool, enemy, and tile; strongest first grid-retention test | `eight_bit_inspired_modern_pixel` |
| `a09` | **Dungeon&Fighter** — [over 850 million registered users and US$22 billion lifetime gross revenue](https://www.nexon.co.jp/en/ir/our-business/); publisher also identifies the original as a 2D side-scroller | Hand-authored pixel figures; decisive silhouettes; strong value separation; dense equipment hierarchy; oversized effect accents | Encounter to player, enemy, item, effect, and higher-detail portrait; test controlled detail translation | `high_detail_action_pixel` |
| `a10` | **MapleStory** — [over 250 million registered users and US$5 billion lifetime gross revenue](https://www.nexon.co.jp/en/ir/our-business/), publisher profile | Head-heavy compact pixel figures; rounded silhouettes; bright flat color; minimal facial marks; highly readable small props | Town to NPC sprite, monster, prop, icon, and tile; test identity under aggressive simplification | `compact_bright_pixel` |
| `a11` | **Ace Attorney series** — [15 million series unit sales as of June 30, 2026](https://www.capcom.co.jp/ir/english/business/salesdata.html), publisher data | Clean controlled contours; restrained cel shading; caricatured adult facial planes; readable reaction silhouettes; orderly interior plates | Original event scene to speaking portrait, reaction frame, evidence prop, and background plate | `clean_cel_portrait` |
| `a12` | **Puzzle & Dragons** — [64 million Japanese downloads as of June 2026](https://www.gungho.co.jp/jp/news/ccjg5s00000000z0.html) and [16 million North American downloads as of December 2025](https://www.gungho.co.jp/jp/news/ccjg5s00000000vf-att/pr_20251210.pdf); regional counts are not summed | Fine contour; dense fantasy focal rendering; dominant attribute color; cel-painterly shading; layered effect shapes | Original unit scene to full illustration, portrait crop, small icon, and effect token; reduce particles before silhouette or face | `dense_fantasy_unit` |
| `a13` | **Monster Strike** — [over 65 million users worldwide as of December 2025](https://mixi.co.jp/en/news/2026/0416/52335/), publisher statement; user count, not sales | Compact caricature-to-anime proportions; bold colored contour; bright cel/gradient finish; action-forward silhouette; medallion-friendly focal design | Original unit scene to portrait medallion, compact token, skill icon, and effect; preserve proportion and dominant color | `bright_medallion_unit` |
| `a14` | **Octopath Traveler series** — [over 7 million shipments and downloads as of March 2026](https://www.square-enix.com/asia/newsportal/en/sg/octopathtraveler0/), publisher page | Low-resolution pixel figures in dimensional, material-rich environments; atmospheric focus; volumetric light; selective edge softness | Scene to pixel figure, prop, modular background element, and effect; translate rather than copy scene lighting into the sprite | `dimensional_pixel_translation` |
| `a15` | **Dave the Diver** — [over 5 million units](https://www.nexon.co.jp/en/ir/our-business/), publisher profile | Hybrid direction: expressive high-resolution pixel figures and foreground objects with smoother or 3D depth layers, underwater light, and particles | Base underwater scene to diver, tool, fish-like original creature, prop, and background; foreground and depth layers need role-scoped facets | `pixel_foreground_smooth_depth_hybrid` |

Two independent desk-research passes were reconciled into this pool. That is
enough to propose experiments, not to promote a profile. Before generation,
the record must still pin the exact game version and asset family, preserve the
two analyst notes, and resolve any remaining facet disagreement.

Two commercially important cases are held outside the first profile wave:

- **Fate/Grand Order** is a counterexample to the assumption that a successful
  game has one illustration style. Its [official character gallery](https://fate-go.us/servant/)
  credits many illustrators. A valid test would track one newly designed
  original character from full art to portrait, battle sprite, and icon; it
  must not invent a franchise-wide house renderer.
- **Persona 5 series** has [13 million blended units/downloads as of March
  2025](https://www.segasammy.co.jp/en/ir/individual/business/), but its
  combined palette, collage geometry, typography, and brush-edged silhouettes
  create a protected-similarity risk. It remains a graphic-system research
  anchor, not a generation profile, until a neutral decomposition clearly
  avoids trade dress.

The first proof wave is deliberately only five profiles whose same global
descriptor bundle can be applied fairly to a scene, character, prop, and
background. Role-system hybrids move to a later translation wave.

| Order | Profile ID | Exact frozen descriptor bundle for the exploratory run | Nearest contrast | Primary transfers | 2026-08-24 result |
| ---: | --- | --- | --- | --- | --- |
| 1 | `constrained_low_resolution_pixel_v1` | `low-resolution pixel art; limited sixteen-color palette; one-pixel dark contours; clustered two-step shading; no gradients or antialiasing` | `luminous_highres_pixel_v1` | character, prop, background tile | `exploratory`; stopped at production-pixel gate |
| 2 | `flat_bold_cartoon_v1` | `heavy dark contour; flat saturated colors; sparse one-band cel shading; compact geometric proportions; clean vector-like edges` | `clean_cel_portrait_v1` | character, prop, background plate | `exploratory`; stopped at concept content gate |
| 3 | `inked_atmospheric_2d_v1` | `smooth dark hand-drawn contour; pale focal values; restrained low-saturation palette; soft modeled shading; layered atmospheric depth` | `flat_bold_cartoon_v1` | character, relic prop, background plate | `chain_reviewed`; `recognized_cross_role`; `reference_dominant` |
| 4 | `luminous_highres_pixel_v1` | `high-resolution pixel-rendered 2D; decisive silhouette; dense clustered texture; saturated emissive accents; strong depth-value separation` | `constrained_low_resolution_pixel_v1` | character, prop, effect, background module | `exploratory`; stopped at production-pixel gate |
| 5 | `modern_dense_pixel_v1` | `modern detail-dense pixel art; crisp pixel clusters; selective outlines; saturated local palettes; compact banded shading` | `warm_tile_pixel_v1` | character, tool, tile, layered background | `exploratory`; stopped at production-pixel and content gates |

The first row answers the user's “8-bit pixel game” example without pretending
that `8-bit` alone is a precise technical specification. Its acceptance gate is
the explicit grid, palette, contour, cluster, gradient, and antialiasing bundle.
The game name is not part of the frozen descriptor string.

The later translation wave contains `compact_bright_pixel_v1`,
`clean_cel_portrait_v1`, `dense_fantasy_unit_v1`, and
`dimensional_pixel_translation_v1`. Those systems intentionally change detail,
surface, framing, or depth treatment between roles. They use a stable global
profile plus pre-registered role facets rather than pretending that identical
surface treatment across all assets is the desired result. Balatro remains in
a separate `card_ui` track.

### From anchor observations to a neutral profile

Each profile contains at most one term from each orthogonal axis: line,
shading, color/value, surface/medium, and character grammar when applicable.
Composition, camera, genre, costume, setting, ethnicity, and asset role stay in
the content brief. The profile is rejected or rewritten if it:

- names or implies a game, franchise, character, artist, or studio;
- depends on protected iconography or trade dress;
- merely restates a production role such as `card art` or `cutscene`;
- bundles contradictory or unreviewable adjectives; or
- cannot be translated into three to five visible acceptance traits.

The exact spelling and term order are frozen for a run. A successful multi-term
profile proves control by that bundle. It does not establish that every word in
the bundle contributes; leave-one-term-out and atomic tests are required for
that stronger claim.

## End-to-end experiment

### Model scope

Model awareness is scoped to the exact provider, reported model ID, endpoint,
parameters, and test date. It is not permanent and cannot be projected onto
future model revisions. The first OpenRouter series requested
`openai/gpt-image-2`, but its buffered responses did not report a model ID. The
evidence therefore separates the requested model, authenticated endpoint ID,
and response-reported model. If the response identity cannot be established,
the run cannot be promoted as model-specific evidence.

### Original concept carrier

The same original semantic fixture is used across profiles. It contains a
character, a distinctive prop, and a reusable environment without using mood,
pose, or camera as the style signal:

```text
Create an original 2D game scene in even diffuse daylight. Show one clearly
adult field cartographer beside a small freestanding weather station. The
cartographer wears a teal coat and tan satchel. A round brass compass with one
triangular blue enamel mark rests on a plain worktable. Behind them are a low
stone shelter, three rounded hills, and a single narrow tree. Keep every named
element visible and spatially separate. Do not include words, letters, numbers,
logos, signatures, watermarks, borders, existing characters, or recognizable
franchise elements.

Style profile, preserve exactly: [EXACT NEUTRAL DESCRIPTOR PROFILE].
```

The brief controls nuisance variables but does not make pose accuracy the
research question. A profile may require another fixture only when its declared
scope excludes a scene carrier; that exception is pre-registered and cannot be
used to rescue a failed result.

Pixel runs also pre-register a nominal authoring grid and integer display scale.
The first run uses a `320 x 180` concept grid, a `48 x 64` character grid, a
`32 x 32` prop grid, and nearest-neighbor display scaling. These are technical
controls outside the style keyword block. If the provider cannot honor them,
the output can still be reviewed as `pixel_look_only` but cannot pass the
production-pixel gate.

### Wave-batched execution

A wave is the scheduling unit; each profile remains its own evidence and gate
unit. Before generation, freeze a wave manifest containing every admitted
profile, its exact descriptor bundle, expected visible traits, nearest contrast,
known confounds, applicable roles, prompt digests, required arms and sample
counts, and provider/model/settings. Run equivalent arms across the wave in a
balanced round-robin or randomized order. Do not reuse an artifact or control
arm across profile records.

OpenRouter's asynchronous Batch API is not used because it does not support
image-output jobs. Distinct prompts use independent synchronous image requests
with bounded client-side concurrency. The model's `n` parameter is only a
same-prompt variation count; it does not replace distinct arm records. The
image-generation component remains the sole retry owner for each request.

Review and advancement remain profile-local. Each profile receives its own
controls and independent review. Only a profile that passes Phase A, binds the
selected concept's SHA-256, and satisfies its pre-registered content, safety,
style, and technical gates may enter Phase B. A failed profile stops before
extraction without blocking unrelated profiles; a shared provider, model, or
settings change invalidates or splits the wave. Close the wave only after every
profile records an `advance`, `stop`, or `invalidated` decision. Batching changes
scheduling only, never controls, sample counts, blinding, evidence thresholds,
the extraction gate, or promotion requirements.

### Phase A: concept control

Before generation, register the profile, three to five expected visible traits,
one nearest contrast profile, likely confounds, and applicable asset roles.
Generate balanced arms:

| Arm | Prompt difference | What it measures |
| --- | --- | --- |
| `C0` | No style block | Stochastic and content baseline |
| `CT` | Exact target profile | Target concept control |
| `CN` | Exact nearest-neighbor profile | Specificity rather than generic styling |
| `CP` | Unrelated neutral profile, optional | Generic response to receiving any style block |

One output per arm is a stop/go screen only. Confirmation requires four fresh
outputs per required arm. A target profile is `concept_distinct` only when at
least three of four target outputs show its signatures, blinded target
assignment is at least 75%, target-versus-neighbor forced choice is at least
70%, and content, pose, costume, or layout leakage does not explain the result.

Select the source concept using a content-only rule: the first `CT` output that
passes named-element, text, safety, and technical checks. Do not select the
prettiest or most stylistically exaggerated result. Record its SHA-256 digest;
every derivative record binds to that exact concept.

If `CT` fails concept review, stop that profile. Extraction cannot repair a
concept miss and does not count as another provider retry.

### Phase B: concept-derived focused assets

The applicable targets are:

- **Character:** the same adult cartographer with the teal coat and tan satchel,
  complete readable silhouette, no added accessories, no text.
- **Prop:** the same round brass compass and triangular blue enamel mark,
  isolated and unobscured, no text or frame.
- **Background:** the same stone shelter, three hills, and narrow tree, with the
  character, worktable, and compass removed.

Not every style or game use requires an actor. An anchor may pre-register only
prop and background extraction, but every claimed cross-role profile must test
at least two applicable roles.

For each role, generate these arms while holding content facts, role,
dimensions, provider/model, and settings constant:

| Arm | Concept reference | Style block | What it measures |
| --- | --- | --- | --- |
| `RK` | Exact selected concept | Exact same profile | Intended reference-plus-keyword chain |
| `R0` | Exact selected concept | None | Continuity supplied by reference alone |
| `0K` | None | Exact same profile | Keyword portability without visual reference |
| `RN` | Exact selected concept | Nearest contrast profile | Whether descriptors can steer against the reference |

The `0K` arm receives the same textual identity facts, not an image. The `RN`
arm changes only the style block. One fresh output per arm is exploratory;
promotion evidence requires at least three per arm and three independent
reviewers. A later leave-one-term-out study is run only for profiles that
survive the main chain.

### Phase C: blinded review

Two panels answer different questions:

1. **Concept classification.** Reviewers see randomized `C0`, `CT`, and `CN`
   artifacts without prompts, arm labels, or game anchors. They assign target,
   neighbor, or neutral and explain the visible evidence.
2. **Style consistency.** Reviewers see the selected concept and coded focused
   assets without prompts, keywords, or arm labels. They score the facets below
   and answer: “Which asset looks most likely to belong to the same original
   game art bible as the concept?”

Each dimension is scored `0`, `1`, or `2`:

| Dimension | `0` | `1` | `2` |
| --- | --- | --- | --- |
| Line-language continuity | Incompatible | Mixed | Clearly shared |
| Shading continuity | Incompatible | Mixed | Clearly shared |
| Palette/value continuity | Incompatible | Mixed | Clearly shared |
| Surface/medium continuity | Incompatible | Mixed | Clearly shared |
| Detail-density continuity | Incompatible | Mixed | Clearly shared |
| Character grammar, if applicable | Incompatible | Partial | Clearly shared |
| Content identity | Wrong subject | Approximate | Defining details preserved |
| Role usability | Unusable | Conditional | Readable for declared role |
| Protected-similarity cleanliness | Recognizable leakage | Questionable | Original and clean |

Scores do not replace a short visible-trait explanation. Preserve randomized
mappings and individual reviews, not only consensus.

### How to interpret the control arms

- `RK > R0`, `RK > 0K`, and `RK > RN`: reference and descriptors cooperate.
- `RK ~= R0`, while `RN` differs: reference is sufficient; descriptors add
  little continuity but can steer.
- `RK ~= R0 ~= RN`: reference dominates; descriptor contribution is unproven.
- `RK ~= 0K`, with identity loss in `0K`: descriptors are portable and the
  reference mainly preserves identity.
- `0K` preserves style but not identity: expected keyword-only behavior.
- `RN` equals or beats `RK`: control inversion; same-profile consistency is not
  demonstrated.
- one role fails while the others pass: role-scoped drift, not global control.

### Style-specific technical gates

Visual similarity and production validity are separate. Relevant additional
gates include:

- **Pixel profiles:** deliberate stable pixel grid, consistent effective pixel
  size between concept and extraction, coherent clusters, palette discipline,
  controlled dithering, and no accidental interpolation or antialiasing. A
  high-resolution image that merely resembles pixels is labeled
  `pixel_look_only`, not a production-valid sprite.
- **Flat or cel profiles:** discrete intended value bands, stable contour
  behavior, no unexplained gradients, and silhouette readability at target
  size.
- **Ink or print profiles:** stable mark vocabulary and surface treatment
  without false text, signatures, or random hatch noise.
- **Painterly profiles:** shared edge hierarchy, brush scale, value grouping,
  and focal-detail density rather than superficial texture alone.

Technical failure does not erase a valid style-recognition observation, but it
blocks a production-control verdict.

### Evidence and verdict vocabulary

| Field | Value | Meaning |
| --- | --- | --- |
| `evidence_status` | `untested` | Text inventory only; no model evidence |
| `evidence_status` | `exploratory` | Stop/go artifacts exist; no repeatability claim |
| `evidence_status` | `chain_reviewed` | Concept, extraction controls, and blind reviews are complete |
| `evidence_status` | `superseded` | Later model/version evidence replaces the recommendation |
| `recognition_verdict` | `not_observed` | No repeatable target signal |
| `recognition_verdict` | `weak_or_unstable` | Some target signal, but inconsistent |
| `recognition_verdict` | `concept_distinct` | Profile controls the concept, transfer not yet proven |
| `recognition_verdict` | `recognized_scoped` | Control survives only declared roles or contexts |
| `recognition_verdict` | `recognized_cross_role` | Control survives at least two applicable roles |
| `recognition_verdict` | `alias_collision` | Exact term is not separable from an alias or neighbor |
| `control_verdict` | `combined_control` | `RK` demonstrates useful reference-plus-descriptor control |
| `control_verdict` | `reference_dominant` | Reference explains continuity; keyword contribution is unproven |
| `control_verdict` | `descriptor_dominant` | Descriptor is portable; reference mainly supplies identity |
| `control_verdict` | `conditional` | Useful only with an observable-trait expansion or narrow scope |
| `control_verdict` | `entangled` | Content, demographic, era, layout, pose, or role explains the change |
| `control_verdict` | `diagnostic_only` | Stable model association is stereotyped or culturally unsound |
| `control_verdict` | `rejected` | Unusable, unsafe, rights-sensitive, or irrelevant |

Common failure codes are:

```text
anchor_evidence_missing
anchor_version_not_pinned
anchor_not_2d_relevant
ip_prompt_leak
taxonomy_axis_leak
keyword_not_observed
keyword_unstable
keyword_alias_collision
keyword_confounded
keyword_scope_limited
stereotyped_association
concept_content_failure
concept_style_failure
concept_selection_bias
reference_ignored
reference_dominant
keyword_ignored
control_inversion
character_style_drift
prop_style_drift
background_style_drift
identity_drift
role_layout_failure
pixel_look_only
reviewer_disagreement
insufficient_samples
model_identity_unavailable
model_drift
protected_similarity
rights_or_provenance_blocked
```

### Secondary atomic-keyword queue

The full inventory is a backlog, not authorization for bulk generation.
Profile-level tests answer the user's end-to-end question first. Atomic probes
then determine which words provide micro-variance and which merely ride along
inside a successful bundle.

Wave 1 is limited to these contrast clusters; every row is `untested`:

| Cluster | Atomic or established exact terms | Scope |
| --- | --- | --- |
| Raster construction | `pixel art`, `limited palette`, `dithering` | Surface, color, mark construction |
| Line | `bold contour`, `clean line art`, `lineless` | Contour behavior |
| Shading | `hard cel shading`, `soft cel shading`, `painterly shading` | Value construction |
| Character grammar | `chibi`, `super-deformed`, `moe` | Proportion versus affect; `moe` is diagnostic |

`SD` is tested later as an exact ambiguous alias. Synthetic compounds such as
`2.5-head-tall chibi` are property expansions, not atomic-awareness tests.
Production roles such as `gacha card art`, `visual novel event CG`, or `anime
film background` never enter the atomic queue.

Run admitted atomic contrast clusters under the same wave rules. Freeze every
term and property expansion before the wave starts; do not add a term after
seeing another profile's output. A weak bare term may receive one separately
registered property-expansion record. A successful expansion proves descriptor
control, not awareness of the bare term.

### Evidence record

Every tested chain eventually records:

```text
research_anchor_id
anchor_version_or_asset_family
neutral_profile_id
exact_descriptor_profile
declared_scope
hypothesized_visible_traits
known_confounds
nearest_contrast_profile_id
concept_prompt_sha256
extraction_prompt_sha256s
source_concept_sha256
provider
reported_model
endpoint
parameters
seed_status
tested_at
arm_generation_ids
arm_artifact_sha256s
blind_mapping_sha256
independent_reviewers
individual_review_scores
observed_visible_traits
evidence_status
recognition_verdict
control_verdict
failure_codes
rights_status
review_notes
promoted_media_paths
```

The exact original prompt may appear in this document. Provider responses,
temporary paths, credentials, signed URLs, and private references must not be
copied here. If the provider exposes no seed, record
`seed_status: unavailable`; never invent one.

### Exploratory run 001: built-in constrained-pixel smoke

This was one `CT` stop/go artifact, not a confirmation run, blinded comparison,
or promotion candidate. The temporary application path is intentionally omitted;
the artifact digest is its stable identifier. Two independent reviewers agreed
on the content and style verdicts.

Exact prompt:

```text
Use case: stylized-concept
Asset type: exploratory 2D game concept scene for a style-control study; the scene itself must be final pixel artwork, not a painted concept sheet.
Primary request: Create one original game scene in even diffuse daylight. Show one clearly adult field cartographer beside a small freestanding weather station. The cartographer wears a teal coat and tan satchel. A round brass compass with one triangular blue enamel mark rests on a plain worktable. Behind them are a low stone shelter, three rounded hills, and one single narrow tree. Keep every named element visible, spatially separate, and easy to identify.
Style/medium, preserve exactly: low-resolution pixel art; limited sixteen-color total palette; one-pixel dark contours; clustered two-step shading; no gradients or antialiasing.
Composition/framing: landscape 16:9 wide scene; one character only; readable full silhouette; no close crop.
Lighting/mood: neutral even diffuse daylight; lighting must not introduce smooth gradients.
Technical pixel contract: visually author the scene on a nominal 320 x 180 pixel grid and show it only with integer nearest-neighbor enlargement; stable square pixel cells; coherent hand-placed pixel clusters; no interpolation, smoothing, subpixel strokes, blur, glow, film grain, or soft transparency.
Constraints: original and brand-neutral content only; no words, letters, numbers, UI, captions, logos, signatures, watermarks, borders, existing characters, or recognizable franchise elements.
Avoid: painterly concept art, vector-smooth edges, 3D rendering, fake high-resolution mosaic texture, mixed pixel sizes, excessive dithering.
```

```text
run_id: exploratory_run_001
research_anchor_id: not_bound_for_smoke
anchor_version_or_asset_family: not_applicable
neutral_profile_id: constrained_low_resolution_pixel_v1
exact_descriptor_profile: low-resolution pixel art; limited sixteen-color palette; one-pixel dark contours; clustered two-step shading; no gradients or antialiasing
declared_scope: original concept scene; planned character, prop, and background extraction
hypothesized_visible_traits:
  - no more than sixteen total colors
  - one-pixel dark contours
  - clustered two-step shading
  - no gradients or antialiasing
  - 320 x 180 authoring grid with integer nearest-neighbor display scaling
nearest_contrast_profile_id: luminous_highres_pixel_v1
concept_prompt_sha256: 75a25ce16a24618cc6b25684498c23ee8356730003b4750c397373ec258d37ee
extraction_prompt_sha256s: []
source_concept_sha256: none
provider: Codex built-in image generation tool
reported_model: unavailable
endpoint: not_exposed
parameters: not_exposed
seed_status: unavailable
tested_at: 2026-08-24
arm_generation_ids:
  CT: unavailable
arm_artifact_sha256s:
  CT: cebc10c989cae04018891242a569607455858f2b74c8a3b7fd1d745d34fe7fef
artifact_format: PNG, 8-bit RGB
artifact_bytes: 1396757
artifact_dimensions: 1672 x 941
artifact_unique_rgb_colors: 158074
blind_mapping_sha256: not_applicable
independent_reviewers: 2
individual_review_scores: not_scored; two narrative stop/go reviews
observed_visible_traits:
  - requested character, coat, satchel, compass, weather station, shelter, three hills, narrow tree, and no-text condition were present
  - cartographer role was only weakly distinguished from a generic field researcher or meteorologist
  - the output used smooth gradients, antialiased edges, multi-step tonal ramps, and inconsistent pixel-block sizes
  - contours varied in thickness
  - dimensions were not an integer nearest-neighbor multiple of 320 x 180
evidence_status: exploratory
recognition_verdict: not_observed
control_verdict: rejected
failure_codes:
  - concept_style_failure
  - pixel_look_only
  - insufficient_samples
  - model_identity_unavailable
content_verdict: pass_with_minor_ambiguity
style_verdict: fail
extraction_gate: no_go
rights_status: unapproved
review_notes: Composition may remain an unpromoted planning reference, but the artifact must not become a style source. Extraction would propagate the excessive palette, gradients, antialiasing, inconsistent grid, and variable contours.
promoted_media_paths: []
```

The exact provider-submitted prompt is preserved, but the provider/model,
endpoint, parameters, seed, and stable generation ID were not exposed. This run
cannot support a model-specific or promotion claim.

### Reviewed run 002: OpenRouter concept-to-asset control chain

This run exercised all generation and review phases with original,
brand-neutral content.
It is a profile-control study, not yet an admitted game-anchor record: candidate
research anchor `a04` motivated the profile, but the exact release, platform,
and asset family were not pinned before generation. That lineage omission
cannot be repaired retroactively and blocks promotion of the keyword as
game-derived vocabulary. The visual evidence below remains useful for the
narrower provider-route question.

The request used OpenRouter's documented
[image-generation endpoint](https://openrouter.ai/docs/guides/overview/multimodal/image-generation).
Authenticated endpoint inspection immediately before the run returned the exact
endpoint ID `openai/gpt-image-2`, consistent with OpenRouter's
[model page](https://openrouter.ai/openai/gpt-image-2). The buffered generation
responses did not independently echo a model ID, so the evidence records the
requested model and authenticated endpoint separately from
`response_reported_model: unavailable`. The documented
[Batch API](https://openrouter.ai/docs/batch-quickstart) targets chat-completion
jobs; distinct image prompts therefore ran as bounded independent synchronous
requests rather than as one asynchronous provider batch.

```text
run_id: reviewed_run_002
tested_at: 2026-08-24
research_anchor_id: none_admitted; candidate lineage a04
anchor_version_or_asset_family: not_pinned_before_run
neutral_profile_id: inked_atmospheric_2d_v1
exact_descriptor_profile: smooth dark hand-drawn contour; pale focal values; restrained low-saturation palette; soft modeled shading; layered atmospheric depth
nearest_contrast_profile_id: flat_bold_cartoon_v1
provider: openrouter
endpoint: https://openrouter.ai/api/v1/images
requested_model: openai/gpt-image-2
authenticated_endpoint_id: openai/gpt-image-2
response_reported_model: unavailable
parameters: n=1; quality=high; background=opaque; moderation=low; aspect_ratio=role_specific
seed_status: unavailable
execution: independent synchronous calls; max_concurrency=3; component owns up to six attempts
rights_status: unapproved
promoted_media_paths: []
```

#### Batch and validation ledger

Every successful response passed strict base64 decoding, PNG-signature checking,
non-empty media validation, caller validation, and an artifact-digest check.
The three retries below were transport/provider attempts owned by the component,
not semantic regenerations or nested runner retries.

| Wave | Purpose | Successful calls | Provider attempts | Cost (USD) | Result |
| --- | --- | ---: | ---: | ---: | --- |
| `001` | Five-profile exploratory concepts; `C0`, `CT`, `CN` | 15 | 15 | 1.960895 | One profile advanced |
| `002` | Four fresh confirmations for each inked-atmospheric concept arm | 12 | 12 | 1.567080 | `concept_distinct` |
| `003` | One exploratory extraction for four arms and three roles | 12 | 12 | 2.250637 | Character stayed exploratory; prop and background advanced |
| `004` | Prop and background replications two and three | 16 | 19 | 2.865316 | Cross-role chain reviewed |
| **Total** |  | **55** | **58** | **8.643928** | No media promoted |

The frozen local evidence manifests and blind mappings are identified by digest.
They remain ignored raw research material and are not publication-ready
provenance sidecars.

| Wave | Preregistration SHA-256 | Execution SHA-256 | Blind-mapping SHA-256 |
| --- | --- | --- | --- |
| `001` | `9418b03bbf92d80c628caa2c8910f7ab4f799d352e8e09f72206f2732b13aba8` | `656c2a49d76819760be6fc0d2c82e276dcf8a671f839bf460a8bb35c11923cd3` | `20eefacd1057e948cb3b9f628c1399e703a584f4378059784072a0cbcc5f38b7` |
| `002` | `f4938148b99dabd1d91773927eceba46de376c9d14b0108343eb7edcf72f977c` | `425391c2a0e161463dd31d1b3fc722e908b9285550d450f23291bde9ee7de945` | `356cee7ed5ee4f26da9d562639e170681a85ccf6adb6da988f91c23746f9804f` |
| `003` | `81c8a903c29c64cf7df5e3fc5a7db014f298ca089acf478a0c9d4c74e97ac491` | `5f0f8537f87317667a4711919e2f7b19b53379750d53ff8e4b62c231d52ea8c1` | `97027d6115fa453baaca2cc6a198b361c11c9fc34d3bf07da4ac6ec7b5ed31dc` |
| `004` | `759a133d9e4df7c81a29df4832306e57a5a61f641f80b2ca92cc3ac98d881a3b` | `9c8d5af681403af30fea9d2fa4b1a9b46e6a4b2f7506b444b6a2e5760585d6f3` | `11f39e7952f9687ca57f50218b21409bca049413ffa44c3f8f56e7c31521a09a` |

#### Phase A result

In the first screen, each of three independent reviewers correctly recovered
the target, nearest-contrast, and neutral arms on all five randomized
three-image sheets. That proves visible separation in this sample, not
production suitability or repeatability.

| Profile | Observed target signal | Gate and decision |
| --- | --- | --- |
| `constrained_low_resolution_pixel_v1` | Coarse pixel-like treatment was recognizable | More than 100,000 RGB colors, no stable logical grid, gradients, and antialiasing: `pixel_look_only`; stop |
| `flat_bold_cartoon_v1` | Heavy contour, flat saturated fills, and compact geometry were clear | A strict content review found the required blue compass mark missing; stop |
| `inked_atmospheric_2d_v1` | Smooth ink-like contour, pale focal values, restrained color, soft modeling, and atmospheric depth were clear | Content and safety passed; advance |
| `luminous_highres_pixel_v1` | Dense pixel-like surface and decisive silhouettes were recognizable | Pixel construction was technically invalid and the emissive signal was weak; stop |
| `modern_dense_pixel_v1` | Dense pixel-like clusters and saturated local color were recognizable | No stable pixel grid, plus one strict review found only two clearly dominant hills; stop |

The confirmation wave then generated four fresh `C0`, `CT`, and `CN` outputs.
Each of the three blinded reviewers classified all 12 correctly. All four `CT`
outputs showed the five registered target traits and passed the content and
safety screen. The first qualifying `CT` by generation order, not aesthetic
preference, became the source concept:

```text
concept_prompt_sha256: 21fb32867b91e4aa1192aed2289873cc6f43f9c8792337a3a69012ca3888039e
source_concept_sha256: 495dc7abaa7066fded2bbcd6df218fe2fd53a584c8dc6d3ed0b6b6650276447d
phase_a_recognition_verdict: concept_distinct
```

#### Phase B result

All reviewers saw the selected source concept and randomized focused assets,
without prompts, keywords, or arm labels. The character screen remained
exploratory at one sample per arm. Two reviewers ranked `RK` above `R0`; one
ranked `R0` above `RK`; all placed those reference-bearing target treatments
above `RN` and `0K`. This is an initial reference-dominance signal, not a
confirmed character claim.

Prop and background each reached three samples per arm and three independent
reviews:

| Role | Unblinded result | Content result | Control interpretation |
| --- | --- | --- | --- |
| Prop | `RK` labels `A/E/I` and `R0` labels `D/H/K` formed one effectively tied source-like band. `RN` labels `B/G/J` were visibly heavier, flatter, and brighter. | All `RK` and `R0` outputs retained the simple blue-mark identity. Every `0K` output introduced a large compass rose; one `RN` output did too. | Repeatable continuity, but `RK ~= R0`; reference-dominant. Mismatched descriptors still steer. |
| Background | All six `RK` and `R0` outputs formed one source-like band; reviewers' finer visual clusters crossed arm boundaries. `RN` was consistently brighter, crisper, and more saturated, although the reference moderated the flat-bold request. | `RK`, `R0`, and `RN` retained the landmarks. `0K` retained the semantic element set but materially changed the shelter, hill, scale, or location identity. | Repeatable continuity, but `RK ~= R0`; very strong reference-dominance signal. |

The keyword-only `0K` arms carried a broadly compatible inked/atmospheric
treatment into both confirmed roles, but lost defining identity. The mismatched
`RN` arms shifted both roles toward the flat-bold contrast even while using the
same reference. Together with Phase A, that is enough for bundle-level
`recognized_cross_role`; it does not establish awareness of each atomic word.
The intended combined-control claim fails because adding the same descriptors
to the reference did not measurably outperform reference-only extraction.

```text
evidence_status: chain_reviewed
recognition_verdict: recognized_cross_role
control_verdict: reference_dominant
confirmed_roles: prop, background
exploratory_roles: character
failure_codes:
  - anchor_version_not_pinned
  - reference_dominant
  - identity_drift
promotion_blockers:
  - response_model_identity_unavailable
  - rights_or_provenance_blocked
review_summary: The route recognizes and can steer the exact descriptor bundle, and the concept can yield visually consistent focused assets. In this chain, the reference—not repetition of the same keyword bundle—explains the continuity.
```

Extraction prompt digests are stable across replications. `RK` and `0K` share
prompt text and differ only by whether the exact concept reference is attached.

| Role | `RK` and `0K` prompt SHA-256 | `R0` prompt SHA-256 | `RN` prompt SHA-256 |
| --- | --- | --- | --- |
| Character | `7e79e27168e6322c7e58139b2efc61e0670a61ad672e16421bece8b6095427a2` | `26a74d54d9e0cae32a12457e127cc898de8873b5985b618ed4d5ca0f02cd4a6a` | `1ffc8b7f38330e3768cc62df5a20fa18ad12896db1e911d7030821705479e931` |
| Prop | `3ccd2abecbcaec2b6cda551fd78fba4a7a67694340684c3f9251e4de33852a50` | `b55a6a319bfab68813f0d5abd0240c716d6e643cf800edaf4d8c53efb814cf4b` | `88ff1cd9680de390031b71b1a483589cce9dfb77365cb3cd5c06ec06c1347c01` |
| Background | `6869bd44c47d01fc123d62005353b8b0343540af61426373af0cbdc7d7a2c424` | `bbe59490f147f81f4c6dd1be22d063dd8d37c05147c5075c5626f8506dcb723b` | `214c1caac7a2ebec1b59815079addf6919fbebdf44c4e2037da07b05a653f83e` |

<details>
<summary>Artifact SHA-256 registry for reviewed run 002</summary>

`wave-001` exploratory concept screen:

```text
constrained_low_resolution_pixel_v1 C0 956645aa55eb429b46a2920fc5370334b430c6752bc338000af626ad14b96aa3
constrained_low_resolution_pixel_v1 CT c4bdedc7697cb3860b68537af33827ef70d298600d31d69da11451a2d77df189
constrained_low_resolution_pixel_v1 CN 940a3274a8a8ef26be97f1825f3d99b2f0ae9da325b4843621d578f846542892
flat_bold_cartoon_v1 C0 ca03e4aecf8551b7fa0653ed5a4dd0dec0e21946e8ce95c9f85fe673cc344eb3
flat_bold_cartoon_v1 CT f11904631e338e7f4caa388db3d4eb03e1130f322bddc49319d172d3a986237d
flat_bold_cartoon_v1 CN 763885af2301837ebe502633d432893d41ff9235d12735a99a2b8c3e54360cd6
inked_atmospheric_2d_v1 C0 179c1aa15bf178e551609a44edb99c85f541a215e673ac6b6b4352ae5e4f1783
inked_atmospheric_2d_v1 CT e06264953fceb7cc6c84e26a1733d2e0c75fdc50e61ce9f7a62e0ba37c3f02d3
inked_atmospheric_2d_v1 CN 584b12cdd65dc854b84f55aea6aa1b0a3a6816dc46bba997aaaf505b66af078c
luminous_highres_pixel_v1 C0 6508289b2be57895a55d301a38d7b65b9eab7fc53a3875818964e478cecbfb2d
luminous_highres_pixel_v1 CT 342615d3de5b3bf0da8560d5e169fc72b550d192327866025937c408552c73a0
luminous_highres_pixel_v1 CN f4e265a68fe54e5bc662623299edfcbe297bad52dd0648737e49b22eada39d96
modern_dense_pixel_v1 C0 1fa06e1b70eedaef5c6daf77a650510aef5ba8d20882a40a0ff7cfd6b7b98e9b
modern_dense_pixel_v1 CT 3b97d50093fa027fe25cb5de3c3f639763f754fad3b452f7f02b7e074222395b
modern_dense_pixel_v1 CN 997a5c4287047a441c53a81a00155b95e3955bc4abe7a73f5aa0ca16a5f17b31
```

`wave-002` inked-atmospheric concept confirmation:

```text
C0 r01 2c4f61af6d326542c9ba08fabb8111eb857c45c90cdcaa9ce9a1c938d8aa9d03
C0 r02 b18595a2fa0e28edfc781e884ca2de5a28507e92a2124e988999a866546c3318
C0 r03 31e9a65511d9a3f3339b167c613bd278f6ca0cc66b33babf292e45c596de39f7
C0 r04 567969a3d1c78d25a0f9fdfa85ca05d781d015dd83e172078a24a00ae31d6f28
CT r01 495dc7abaa7066fded2bbcd6df218fe2fd53a584c8dc6d3ed0b6b6650276447d
CT r02 33e1ddeb28a4e3b8301a4df6a4e97d75bfdff867a157e94bc6d28293d09433db
CT r03 b156297ca264ecdcc5c5f720d189f7b6536ba40ff35fdcc08a989aa1f92a11de
CT r04 d843612f2e81ed60f8865abfc383f3c8fabb06c7d5245a888149cf0ff45a62f6
CN r01 5cd103a661310d7fea6f0e2e7e5e407c790a50f588b09e1f3dd580e5955914af
CN r02 f21e543ab6817fd970643d559d79b2b5bcccbd949ff71fba487880ef1f152228
CN r03 5948674b308f957bacfb74f70c71ef098c2b805091b965913bacd12178ebcc77
CN r04 651cf255bff093bca81010027ccd9ad1f78800711a3fe7c3ffc1d1389d26777d
```

`wave-003` character exploration:

```text
RK r01 5810e2ca6aaeabdd99703f007bea131129fba755fdfc7f7c728c3934a78319dc
R0 r01 26a586bf854bb2327ca67caa4f13683988d6e4f2c2c5a801c0e2b43249e7a83e
0K r01 dc5e341990c4975be22518ff3553d2e4f801e2e7d77a8a70825c822c8f4f563f
RN r01 331f96423f2e7c2ef246501c4931bf334353b43c2bb42e0d1731d11e7ccd1993
```

`wave-003` plus `wave-004` prop confirmation:

```text
RK r01 e9c0fd9d48f02628e5822851ca4003801f792a8e2cd9fbf255fab20f8082c01f
RK r02 c4d5c7e95f9c41f627337ea74b1cff45155412c1fcee97a1da7a11c3fe6727f8
RK r03 78b2bb6f49a67e677331245b59071006860d398dd9ac0bbf3904292ce620185c
R0 r01 641421b6738cc6e323617906c7546b24bbaa8285fc257f19cbd850b3fdb976f2
R0 r02 547bca6aef557b6bb93df67cffd86af57fbeced9b3cbc3946382a4f90909b73b
R0 r03 44b572fb750f50e6de9b1136d4903b410f12e08973f4fc913a6ec0999a971edb
0K r01 1751ee52b18739c83b34add7ed76c74e9bf09a557f34178a7c3e02cd1a3ed16b
0K r02 69407d184ca1484a542a9c3267dc87f13b69b2023165065444dac793b7d550f4
0K r03 ac3f1e904f3be72a0d9bda6ae1b988485016b7757bbd9258780545f9287b048a
RN r01 903bbe24aadc07dba8880bcc8e62ebde02d05d1f45541148ff3e34e09eb8f70e
RN r02 3642fe0ad589a8be1dca4657b24df80fa9a7635ff92dfdc8f2a4c0daa7aa4bd2
RN r03 f8bdc28907fe56c3354f075781c0898b0da0e6cc03e296ba400048287bbc03e6
```

`wave-003` plus `wave-004` background confirmation:

```text
RK r01 202bc0ee17ebd4946ca023269a99ad9002a1764ea6fab9ebba70568185040449
RK r02 4ae750ad2df2e9911ddd40a5413171e395b7388b2c4fe7235c35006a1f057a5d
RK r03 c26a293ad950f59f4c658d81b911995f073f26b4597dc5ae01095ac670f00e58
R0 r01 0def4ed0fd459eec191375db5fddf11c5e5bce2b43bfdfe396586808f2efbccc
R0 r02 770942286eb2ae9937c644d6e3e57546c4b4cff3bdf5c62e2c621507c5f1658f
R0 r03 6d5ed59ac1d1d11f7becead23ba3de158cbfc2b040659527eb465e74e417dbb6
0K r01 aa54d9a697348fa2be4d3f12fd3d86c75c88bd186034c67497317ff8528e4ac5
0K r02 e98bd1043ac23a67bc6c53fdb47d9db2f96001f45e1663677d7800e1acc1fa10
0K r03 1509898fdf92f81db82031eb0d8760bda3e52bde1069e822393fbd7dce31a650
RN r01 eb8d07950f31bdab1ec2d9fd35c3dc4c7a96713953a10e689e4dfc28a5be6e6e
RN r02 0b1f2687ee3e634a0d5606cc188b8c389289f30f7e950278c94176b963784cdf
RN r03 b7684baa0eb61f785818c964f22de25a476035a6fc1261c620ef799ba2a43bf6
```

</details>

## Promotion checklist

Before a result appears as a reviewed showcase:

- [ ] Raw candidates were cleaned so only the selected evidence remains.
- [ ] The exact provider/model/date and non-secret parameters are recorded.
- [ ] The exact original prompt and its digest are recorded.
- [ ] Artifact bytes and SHA-256 digests are stable.
- [ ] An independent reviewer evaluated the exact artifact against the
      pre-registered traits and nearest contrasts.
- [ ] The result is labeled accurately: one sample is never called repeatable.
- [ ] No artist, studio, franchise, product, character, signature, logo, or
      recognizable protected expression leaked into the output.
- [ ] Inputs and references, if any, have an explicit rights basis.
- [ ] The artifact-specific redistribution decision and notice are complete.
- [ ] The sidecar, review report, and generated-media inventory agree.
- [ ] Documentation and repository media gates pass.

## Research notes and sources

- The [Kyoto International Manga Museum's Manga Wall](https://kyotomm.jp/en/manga-wall/)
  organizes shonen, shojo, and seinen as readership/publishing groupings. That
  supports treating them as dialect candidates rather than fixed renderers.
- Scholarship on the [formation of shojo manga](https://academic.oup.com/hawaii-scholarship-online/book/17611/chapter-abstract/175248026)
  and the [origin of a distinctive shojo manga style](https://academic.oup.com/minnesota-scholarship-online/book/21222/chapter-abstract/180875093)
  shows that publishing history and visual conventions interact; neither can be
  reduced to a timeless single look.
- Animation scholarship warns that
  [anime is not homogeneous](https://journal.animationstudies.org/article/id/39/)
  and discusses chibi-like distortion, enlarged eyes, and simplified features as
  variable visual devices.
- A computer-graphics study defines
  [super-deformed or SD characters](https://cir.nii.ac.jp/crid/1360302870460667392)
  through exaggerated proportions such as oversized heads and short limbs. This
  makes `super-deformed` a stronger measurable candidate than geography alone.
- Research on [moe and fantasy](https://mail.japanesestudies.org.uk/articles/2009/Galbraith.html)
  describes `moe` as a response to fantasy characters rather than one specific
  style. The label remains testable as model vocabulary, but it must be
  decomposed before canonical use.
- A [Korean Culture and Information Service overview](https://www.korean-culture.org/eng/webzine/202404/sub01.html)
  describes webtoons around online serialization and the development of
  vertical scrolling, supporting the decision to keep format separate from
  rendering style.
- The Metropolitan Museum of Art distinguishes
  [ukiyo-e](https://www.metmuseum.org/ja/essays/art-of-the-pleasure-quarters-and-the-ukiyo-e-style),
  [yamato-e](https://www.metmuseum.org/fr/essays/yamato-e-painting), and the
  [Rinpa aesthetic](https://www.metmuseum.org/ja/perspectives/japan-rinpa-school-screens)
  as historically situated lineages with different media, motifs, and formal
  conventions.
- The Met's guide to
  [Chinese painting](https://www.metmuseum.org/zh/essays/chinese-painting) and
  [baimiao line drawing](https://www.metmuseum.org/exhibitions/listings/2008/anatomy-of-a-masterpiece/photo-gallery)
  supports separating brush line, ink wash, shading, and subject tradition.
- MoMA's descriptions of
  [screenprint](https://www.moma.org/collection/terms/screenprint)
  and [lithography](https://www.moma.org/collection/terms/lithography) illustrate
  why process terms should predict observable surface traits rather than serve
  as vague aesthetic labels.

## Decision log

- The canonical home is a research directory, not a component or packaged
  skill.
- The first phase established the text taxonomy before any model evidence; only
  explicitly recorded profiles leave `untested`.
- The public artifact is one guide document. Machine-readable registries may be
  added only if the reviewed evidence becomes too large for this page.
- Broad regional words are negative controls, not accepted style names.
- `moe` remains a candidate but is not defined as a single visual style.
- `SD` is tested as an exact alias, while `super_deformed` is the preferred
  canonical ID.
- Production roles include actors, cutscenes, environments, props, cards, UI,
  and effects and remain separate from style.
- Photorealism is not prioritized for the first 2D-game study.
- The first OpenRouter route visibly separated all five exploratory descriptor
  profiles, but style recognition and production-valid asset construction are
  different gates; all three pixel profiles stopped before extraction.
- `inked_atmospheric_2d_v1` is recognized across prop and background roles, but
  `RK ~= R0`; the concept reference explains continuity better than repetition
  of the same descriptor bundle.
- The global game catalog is the upstream source for future keyword admission.
  Run 002 predates its pinned asset-family gate and therefore remains profile
  evidence rather than an admitted game-derived keyword record.
- No generated image is promoted or committed without independent review and
  the repository's media-rights gates.
