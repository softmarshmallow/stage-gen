# Game visual reference and vocabulary

> **Status: global seed catalog and taxonomy input.**
>
> This document is shared visual-language infrastructure for any 2D-game asset,
> scene, cutscene, UI, or research workflow. It is not dedicated to one recipe,
> component, provider, or current experiment. Game names are research anchors,
> never approved prompt tokens or invitations to imitate protected expression.

## Purpose

This catalog makes visual vocabulary traceable. A game record supplies a
concrete, inspectable application context; a neutral decomposition turns that
reference into observable line, color, shading, surface, proportion, depth, and
production traits. Model-awareness experiments can then test those traits
without sending a game, franchise, character, artist, or studio name to an
image provider.

The default sequence is:

```text
game reference
-> pinned version, platform, and asset family
-> sourced visual observations
-> brand-neutral facets
-> candidate keyword or descriptor
-> model-specific test evidence
-> accepted, scoped, revised, or rejected vocabulary
```

Camera and framing are indexed here because they help find comparable games,
but they are not rendering style. Likewise, genre, setting, subject matter, UI
layout, and production role remain separate from style facets.

The proposed [game view and style taxonomy](spec/game/view-and-style-taxonomy.md)
owns canonical technical definitions for projection, camera pose, gameplay
space, asset view, framing, and typed visual-style facets. This reference
catalog inventories evidence and routes ambiguous aliases toward those axes; it
does not redefine that specification or change implemented runtime vocabulary.

## Governance

The registry has three deliberately separate layers:

| Layer | Contains | May reach prompts? |
| --- | --- | --- |
| Research anchors | Game names, releases, asset families, links, and observed shorthand | Never |
| Semantic registry | Neutral atomic IDs, definitions, visible traits, aliases, and evidence status | Only when separately approved for prompting |
| Operational vocabulary | Versioned runtime clauses, resources, and schemas | Only through a separate implementation change |

### Reference states

| State | Meaning |
| --- | --- |
| `seed` | A useful discovery row exists, but its year, version, framing, or visual label has not been source-checked for taxonomy use. |
| `researched` | The exact game version, platform, asset family, and factual sources are pinned. |
| `decomposed` | At least two reviewers agree on visible neutral facets and known confounds. |
| `tested` | A provider/model/date-specific controlled experiment exists. |
| `retired` | The record is duplicated, misleading, superseded, or unsuitable. |

All 76 supplied rows below begin as `seed`. Their Wikipedia links are useful
discovery links, not sufficient evidence for a `researched` or `decomposed`
claim. Commercial success, visual style, platform differences, ports, remasters,
and asset-family differences require appropriate sources before promotion.

### Keyword admission

Every compound game-art profile should point to at least one `decomposed` game
record before it becomes active vocabulary. Prefer two independent game anchors
when a label claims a family rather than one title. The registry must preserve:

- the exact submitted or observed alias;
- a canonical `lower_snake_case` candidate ID;
- visible facets rather than mood or geography alone;
- the basis record IDs and pinned asset families;
- aliases and likely collisions;
- camera, content, genre, era, and role confounds;
- test status and exact model scope; and
- the reason for acceptance, restriction, or rejection.

Track semantic correctness, prompt suitability, model recognition, and runtime
support independently:

```text
semantic_status: proposed | reviewed | deprecated
prompt_status: forbidden | candidate | approved
model_status: untested | exploratory | confirmed | superseded
implementation_status: none | runtime_vN
```

Every game anchor has `prompt_status: forbidden`. Every seed-derived term below
starts `semantic_status: proposed`, `prompt_status: candidate`,
`model_status: untested`, and `implementation_status: none`.

The global vocabulary is intentionally broader than games. An art-historical
lineage or technical primitive may enter as a candidate before a matching game
anchor only when it has an authoritative external source and
`basis_type: external_lineage` or `basis_type: technical_primitive`. It cannot
claim game applicability until a game record is linked. Broad regional words,
commercial platform names, decade labels, and genre words do not become
canonical styles merely because they appear in a seed label.

### Prompt boundary

Provider prompts use the neutral observable descriptor, never the game title or
a source label containing a franchise, platform trademark, character, artist,
or studio. For example, `8-bit NES Pixel Art` is preserved as a research alias;
a later prompt-safe record must state the actual palette, logical resolution,
cluster, contour, and shading constraints. `Gothic`, `military`, `fantasy`,
`industrial`, `sci-fi`, and `JRPG` are content or genre qualifiers until
separately decomposed.

## Required record shape

A promoted game reference records these fields:

```text
reference_id
game_title
release_or_version
platform_or_rendering_target
asset_family
release_year
camera_and_framing
source_style_aliases
neutral_line_facets
neutral_shading_facets
neutral_color_facets
neutral_surface_facets
neutral_character_grammar
neutral_depth_facets
content_genre_and_role_confounds
source_urls
source_quality
analyst_reviews
reference_state
derived_keyword_ids
```

One game may need several records. A world sprite, dialogue portrait, cutscene
still, card illustration, and UI icon can follow different role systems even
inside the same release.

## Framing-alias routing

These are research routing rules, not persisted canonical profiles. Resolve them
against the technical taxonomy before experiment or implementation use.

| Seed alias family | Tentative axis routing | Required resolution |
| --- | --- | --- |
| Side View | `camera_pose_family: lateral` | Projection, gameplay space, camera behavior, and shot extent remain unknown |
| Fixed Side View | `lateral` plus `camera_behavior: fixed` | Do not infer orthographic projection |
| Fixed Side / Orthographic | `lateral`, `fixed`, and `projection_model: orthographic` | Verify the exact game asset and runtime rather than trusting the seed phrase |
| Side View / Belt-scroller | `lateral` plus `gameplay_space: depth_belt` | Belt depth is gameplay space, not style |
| Top-Down | unresolved overhead pose | Inspect whether it is `overhead_nadir`, `high_elevation_oblique`, or another pose |
| Three-quarter or oblique top-down | `elevated_oblique` candidate | Projection remains unresolved; bare `three-quarter` is insufficient |
| Isometric variants | `axonometric_unverified` | Measure projected axes before choosing isometric, dimetric, or trimetric |
| Side or top-down cutaway | pose remains separate from cutaway composition | Cutaway is layout treatment, not projection or style |
| Fixed First-person / Desk View | `frontal_stage` plus `fixed` and desk-foreground composition | Projection and shot extent remain scene-specific |
| Fixed / Card-battle View | `screen_space`, `frontal_stage`, `fixed`, and card layout | Card battle is a presentation role |
| Fixed / Tabletop UI | `screen_space`, `fixed`, and tabletop layout | Do not infer overhead geometry from `tabletop` |
| Top-Down plus Fixed Battle View | split into distinct scene and battle records | A multi-mode game cannot use one slash-delimited canonical frame |

## Seed-derived atomic vocabulary

Compound seed labels should decompose into reusable atoms before prompting.
These are neutral candidates, not complete styles or runtime identifiers.

| Candidate ID | Facet | Observable descriptor candidate | Example seed anchors |
| --- | --- | --- | --- |
| `pixel_raster` | medium | Deliberate square-pixel raster construction with stable effective pixel size and coherent clusters | All pixel-labeled rows |
| `pre_rendered_3d_raster` | production process | Volumetric modeled forms with baked lighting rendered into 2D raster assets | Donkey Kong Country; Diablo; StarCraft; Factorio |
| `hand_drawn_raster` | medium and mark | Irregular drawn contours with raster-painted fills | Rayman; Binding of Isaac: Rebirth; Pizza Tower; Nine Sols |
| `cel_illustration_2d` | medium and shading | Flat color fields with discrete hard-edged shadow bands | Plants vs. Zombies; Mark of the Ninja; Cuphead |
| `painterly_digital` | medium and shading | Continuous tonal brush modeling with a digital-painted edge hierarchy | Braid; Ori; Slay the Spire |
| `watercolor_ink` | medium and surface | Transparent watercolor-like washes accented or bounded by ink lines | GRIS |
| `inked_cutout` | medium and construction | Irregular ink contours, flat cut-paper-like pieces, and layered overlap | Don't Starve |
| `monochrome_silhouette` | palette and shape | Near-monochrome value design carried primarily by readable silhouettes | LIMBO |
| `coarse_pixel_grid` | detail and technical | Large effective pixel cells with aggressively simplified forms | Cave Story; Papers, Please; Celeste |
| `dense_pixel_clusters` | detail and mark | Small effective pixel cells with dense coherent clusters and controlled texture | Metal Slug; Hyper Light Drifter; Sea of Stars |
| `limited_indexed_palette` | palette | A declared bounded indexed palette with no continuous gradients | Early console and monochrome pixel rows |
| `monochrome_indexed_palette` | palette | A small discrete value ramp within one hue family | Pokemon Red / Green |
| `clustered_banded_shading` | shading | Form described through discrete pixel clusters and bounded value bands | Pixel rows pending asset-family review |
| `flat_color_regions` | shading and color | Broad flat fills with little continuous tonal modeling | EarthBound; RimWorld; cel-cartoon rows |
| `atmospheric_value_depth` | depth | Successive depth planes become lower contrast and quieter in value | Super Metroid; Hollow Knight; Animal Well |
| `saturated_emissive_accents` | lighting and color | Small high-saturation luminous accents against a quieter base | Hotline Miami; selected modern pixel rows |
| `tile_modular_construction` | technical | Seam-aware modular raster construction on a declared tile grid | Spelunky; Terraria |
| `bold_dark_contour` | contour | Heavy dark silhouette and internal contours | Mark of the Ninja; selected cartoon rows |
| `clean_ink_outline` | contour | Controlled continuous ink-like edges with restrained variation | Hollow Knight; GRIS |
| `graphic_shadow_masses` | shading and value | Large designed shadow shapes instead of continuous tonal modeling | Cel and comic-book rows |
| `continuous_tonal_shading` | shading | Smooth modeled value transitions describing volume | Painterly and pre-rendered rows |
| `rounded_geometric_shapes` | shape language | Compact forms constructed from rounded simple geometry | Cartoon rows pending decomposition |
| `chibi_proportions` | proportion | Head-heavy compact build with simplified limbs and measurable `heads_tall` | MapleStory |
| `rubber_hose_character_grammar` | shape and motion | Rounded forms, flexible tube-like limbs, and elastic pose arcs | Cuphead |
| `rotoscoped_motion` | motion | Naturalistic weight and timing associated with traced-motion construction | Prince of Persia |

`tile_modular_construction`, `rotoscoped_motion`, and `chibi_proportions`
occupy different axes and must not masquerade as complete rendering styles.

## Research-only alias corrections

| Raw wording family | Registry treatment |
| --- | --- |
| `8-bit`, `16-bit`, `NES`, `SNES`, `Genesis`, `Game Boy` | Preserve as research aliases; replace in prompts with explicit grid, palette, shading, and cluster constraints |
| `arcade`, `retro`, `neo-retro` | Era or platform context; decompose into visible traits |
| `JRPG`, `gothic`, `military`, `sci-fi`, `fantasy`, `medieval`, `industrial` | Genre, subject, mood, or material context; not rendering style |
| `sprite art`, `background art`, `card illustration`, `card UI` | Asset or production role |
| `isometric`, `top-down`, `side view`, `cutaway` | View or framing aliases routed through the technical taxonomy |
| `cartoon` | Too broad; decompose into contour, fill, shading, and shape language |
| `high-detail`, `low-resolution` | Require measurable effective pixel size or detail-density criteria |
| `animation` | Motion or production evidence, not a still-image style claim |

## Seed-derived style registry

These are routing candidates derived from the supplied labels. `seed_derived`
means that a game row exists but has not yet passed the source and decomposition
gates. The candidate ID is not automatically a complete prompt.

| Candidate ID | Submitted aliases represented | Example seed anchors | Class | Status |
| --- | --- | --- | --- | --- |
| `early_console_limited_pixel` | 8-bit NES pixel art; 8-bit arcade pixel art; NES-style pixel art | Super Mario Bros.; Metroid; Contra; Shovel Knight | raster construction | `seed_derived` |
| `sixteen_bit_style_pixel` | 16-bit SNES pixel art; 16-bit Genesis pixel art; 16-bit-style pixel art | Super Mario World; Sonic the Hedgehog; Stardew Valley | raster construction and era emulation | `seed_derived` |
| `low_resolution_pixel` | Low-resolution pixel art; low-resolution sci-fi sprite art | Cave Story; FTL; Papers, Please; Undertale; Celeste | raster construction | `seed_derived` |
| `tile_based_pixel` | Tile-based pixel art | Spelunky; Terraria | raster and modularity | `seed_derived` |
| `high_detail_pixel` | High-detail arcade pixel art; high-detail pixel art; high-detail 16-bit-style pixel art | Metal Slug; Hyper Light Drifter; Sea of Stars | raster detail density | `seed_derived` |
| `modern_high_resolution_pixel` | Modern high-resolution pixel art | Dead Cells | raster construction | `seed_derived` |
| `atmospheric_pixel` | 16-bit atmospheric pixel art; low-resolution atmospheric pixel art | Super Metroid; Animal Well | raster plus depth/affect compound | `seed_derived` |
| `monochrome_pixel` | Game Boy monochrome pixel art | Pokemon Red / Green | raster and color constraint | `seed_derived` |
| `neon_pixel` | Neon pixel art | Hotline Miami | raster and color compound | `seed_derived` |
| `retro_pixel` | Retro pixel art; retro pixel sprite art; neo-retro pixel art | Loop Hero; Vampire Survivors; Katana ZERO | diagnostic era label | `seed_derived` |
| `isometric_pixel` | Isometric pixel art | SimCity 2000; Transport Tycoon Deluxe; Into the Breach | raster plus projection; split before prompting | `seed_derived` |
| `arcade_character_sprite` | Arcade character sprite art; arcade pixel art | Street Fighter II; Final Fight | asset-family compound | `seed_derived` |
| `rotoscoped_pixel` | Rotoscoped pixel art | Prince of Persia | motion-source and raster compound | `seed_derived` |
| `pre_rendered_cgi_sprite` | Pre-rendered CGI sprite art | Donkey Kong Country; Oddworld | production process | `seed_derived` |
| `pre_rendered_isometric_sprite` | Pre-rendered isometric CGI sprite art; isometric pre-rendered sprite art | Diablo; Fallout; Diablo II; RollerCoaster Tycoon | production plus projection; split before prompting | `seed_derived` |
| `pre_rendered_rts_sprite` | Pre-rendered RTS sprite art | StarCraft; Age of Empires II; Red Alert 2 | production plus role/genre compound | `seed_derived` |
| `painted_isometric_background` | Painted isometric background plus sprite art | Planescape: Torment; Baldur's Gate | background production system | `seed_derived` |
| `hand_drawn_raster_sprite` | Hand-drawn raster sprite art | Rayman; The Binding of Isaac: Rebirth | line/medium plus role | `seed_derived` |
| `hand_drawn_digital_illustration` | Hand-drawn digital illustration; hand-drawn 2D animation | Rayman Origins; Nine Sols | medium/production family | `seed_derived` |
| `hand_painted_2d_digital` | Hand-painted 2D digital art; painterly digital illustration | Ori and the Blind Forest; Braid | medium and edge treatment | `seed_derived` |
| `hand_drawn_ink_outline` | Hand-drawn ink-outline 2D art | Hollow Knight | line language | `seed_derived` |
| `watercolor_and_ink` | Watercolor-and-ink illustration | GRIS | medium and line compound | `seed_derived` |
| `hand_drawn_inked_cutout` | Hand-drawn inked cutout art | Don't Starve | line, surface, and construction compound | `seed_derived` |
| `cel_style_2d_cartoon` | Cel-style 2D cartoon art; 2D cartoon illustration | Mark of the Ninja; Plants vs. Zombies | line and shading family | `seed_derived` |
| `flat_orthographic_sprite` | Flat orthographic 2D sprite art | RimWorld | value/depth plus role | `seed_derived` |
| `monochrome_silhouette` | Monochrome silhouette art | LIMBO | value and silhouette system | `seed_derived` |
| `rubber_hose_cel_animation` | 1930s rubber-hose cel animation | Cuphead | historical character grammar and process | `seed_derived` |
| `chibi_sprite` | 2D chibi sprite art | MapleStory | character grammar plus role | `seed_derived` |
| `cartoon_cutaway` | 2D cartoon cutaway art | Oxygen Not Included | style plus framing; split before prompting | `seed_derived` |
| `comic_book_2d` | Hand-drawn comic-book 2D art | Streets of Rage 4 | broad lineage label | `seed_derived` |
| `card_ui_pixel` | Pixel-art card UI | Balatro | style plus role; specialist track | `seed_derived` |

## Seed game reference catalog

The table below preserves the supplied global reference rows. The source called
its style column `Rendering Style - prompt-ready`; it is renamed here because no
value is an approved provider prompt until it passes the gates above.

| Game                                        | Year | Camera / Framing               | Observed rendering shorthand — research only | Link                                                                        |
| ------------------------------------------- | ---: | ------------------------------ | --------------------------------------------- | --------------------------------------------------------------------------- |
| **Super Mario Bros.**                       | 1985 | Side View                      | **8-bit NES Pixel Art**                       | [↗](https://en.wikipedia.org/wiki/Super_Mario_Bros.)                        |
| **Metroid**                                 | 1986 | Side View                      | **8-bit NES Pixel Art**                       | [↗](https://en.wikipedia.org/wiki/Metroid_%28video_game%29)                 |
| **Castlevania**                             | 1986 | Side View                      | **8-bit Gothic Pixel Art**                    | [↗](https://en.wikipedia.org/wiki/Castlevania_%281986_video_game%29)        |
| **Contra**                                  | 1987 | Side View                      | **8-bit Arcade Military Pixel Art**           | [↗](https://en.wikipedia.org/wiki/Contra_%28video_game%29)                  |
| **Mega Man**                                | 1987 | Side View                      | **8-bit NES Cartoon Pixel Art**               | [↗](https://en.wikipedia.org/wiki/Mega_Man_%281987_video_game%29)           |
| **Prince of Persia**                        | 1989 | Side View                      | **Rotoscoped Pixel Art**                      | [↗](https://en.wikipedia.org/wiki/Prince_of_Persia_%281989_video_game%29)   |
| **Final Fight**                             | 1989 | Side View / Belt-scroller      | **Arcade Pixel Art**                          | [↗](https://en.wikipedia.org/wiki/Final_Fight)                              |
| **Super Mario World**                       | 1990 | Side View                      | **16-bit SNES Pixel Art**                     | [↗](https://en.wikipedia.org/wiki/Super_Mario_World)                        |
| **Sonic the Hedgehog**                      | 1991 | Side View                      | **16-bit Genesis Pixel Art**                  | [↗](https://en.wikipedia.org/wiki/Sonic_the_Hedgehog_%281991_video_game%29) |
| **Street Fighter II**                       | 1991 | Fixed Side View                | **Arcade Character Sprite Art**               | [↗](https://en.wikipedia.org/wiki/Street_Fighter_II)                        |
| **The Legend of Zelda: A Link to the Past** | 1991 | Top-Down / Three-quarter       | **16-bit SNES Top-down Pixel Art**            | [↗](https://en.wikipedia.org/wiki/The_Legend_of_Zelda:_A_Link_to_the_Past)  |
| **Secret of Mana**                          | 1993 | Top-Down / Three-quarter       | **16-bit JRPG Pixel Art**                     | [↗](https://en.wikipedia.org/wiki/Secret_of_Mana)                           |
| **SimCity 2000**                            | 1993 | Isometric                      | **Isometric Pixel Art**                       | [↗](https://en.wikipedia.org/wiki/SimCity_2000)                             |
| **Super Metroid**                           | 1994 | Side View                      | **16-bit Atmospheric Pixel Art**              | [↗](https://en.wikipedia.org/wiki/Super_Metroid)                            |
| **Donkey Kong Country**                     | 1994 | Side View                      | **Pre-rendered CGI Sprite Art**               | [↗](https://en.wikipedia.org/wiki/Donkey_Kong_Country)                      |
| **EarthBound**                              | 1994 | Top-Down / Three-quarter       | **16-bit Flat-color JRPG Pixel Art**          | [↗](https://en.wikipedia.org/wiki/EarthBound)                               |
| **Chrono Trigger**                          | 1995 | Top-Down / Three-quarter       | **16-bit JRPG Pixel Art**                     | [↗](https://en.wikipedia.org/wiki/Chrono_Trigger)                           |
| **Rayman**                                  | 1995 | Side View                      | **Hand-drawn Raster Sprite Art**              | [↗](https://en.wikipedia.org/wiki/Rayman_%28video_game%29)                  |
| **Transport Tycoon Deluxe**                 | 1995 | Isometric                      | **Isometric Pixel Art**                       | [↗](https://en.wikipedia.org/wiki/Transport_Tycoon)                         |
| **Metal Slug**                              | 1996 | Side View                      | **High-detail Arcade Pixel Art**              | [↗](https://en.wikipedia.org/wiki/Metal_Slug)                               |
| **Pokémon Red / Green**                     | 1996 | Top-Down                       | **Game Boy Monochrome Pixel Art**             | [↗](https://en.wikipedia.org/wiki/Pok%C3%A9mon_Red,_Blue,_and_Yellow)       |
| **Diablo**                                  | 1997 | Isometric                      | **Pre-rendered Isometric CGI Sprite Art**     | [↗](https://en.wikipedia.org/wiki/Diablo_%28video_game%29)                  |
| **Fallout**                                 | 1997 | Isometric                      | **Pre-rendered Isometric Sprite Art**         | [↗](https://en.wikipedia.org/wiki/Fallout_%28video_game%29)                 |
| **Oddworld: Abe's Oddysee**                 | 1997 | Side View                      | **Pre-rendered CGI Sprite Art**               | [↗](https://en.wikipedia.org/wiki/Oddworld:_Abe%27s_Oddysee)                |
| **Theme Hospital**                          | 1997 | Isometric                      | **Isometric Cartoon Sprite Art**              | [↗](https://en.wikipedia.org/wiki/Theme_Hospital)                           |
| **StarCraft**                               | 1998 | Isometric / Oblique Top-down   | **Pre-rendered RTS Sprite Art**               | [↗](https://en.wikipedia.org/wiki/StarCraft)                                |
| **Baldur's Gate**                           | 1998 | Isometric                      | **Pre-rendered Isometric Background Art**     | [↗](https://en.wikipedia.org/wiki/Baldur%27s_Gate_%28video_game%29)         |
| **Commandos: Behind Enemy Lines**           | 1998 | Isometric                      | **Pre-rendered Isometric Realist Art**        | [↗](https://en.wikipedia.org/wiki/Commandos:_Behind_Enemy_Lines)            |
| **Heroes of Might and Magic III**           | 1999 | Oblique Top-down               | **Pre-rendered Fantasy Sprite Art**           | [↗](https://en.wikipedia.org/wiki/Heroes_of_Might_and_Magic_III)            |
| **RollerCoaster Tycoon**                    | 1999 | Isometric                      | **Isometric Pre-rendered Sprite Art**         | [↗](https://en.wikipedia.org/wiki/RollerCoaster_Tycoon_%28video_game%29)    |
| **Planescape: Torment**                     | 1999 | Isometric                      | **Painted Isometric Background + Sprite Art** | [↗](https://en.wikipedia.org/wiki/Planescape:_Torment)                      |
| **Age of Empires II**                       | 1999 | Isometric / Oblique Top-down   | **Pre-rendered RTS Sprite Art**               | [↗](https://en.wikipedia.org/wiki/Age_of_Empires_II)                        |
| **Diablo II**                               | 2000 | Isometric                      | **Pre-rendered Isometric CGI Sprite Art**     | [↗](https://en.wikipedia.org/wiki/Diablo_II)                                |
| **Command & Conquer: Red Alert 2**          | 2000 | Isometric / Oblique            | **Pre-rendered RTS Sprite Art**               | [↗](https://en.wikipedia.org/wiki/Command_%26_Conquer:_Red_Alert_2)         |
| **Stronghold**                              | 2001 | Isometric                      | **Pre-rendered Medieval Strategy Sprite Art** | [↗](https://en.wikipedia.org/wiki/Stronghold_%282001_video_game%29)         |
| **MapleStory**                              | 2003 | Side View                      | **2D Chibi Sprite Art**                       | [↗](https://en.wikipedia.org/wiki/MapleStory)                               |
| **Cave Story**                              | 2004 | Side View                      | **Low-resolution Pixel Art**                  | [↗](https://en.wikipedia.org/wiki/Cave_Story)                               |
| **Braid**                                   | 2008 | Side View                      | **Painterly Digital Illustration**            | [↗](https://en.wikipedia.org/wiki/Braid_%28video_game%29)                   |
| **Spelunky**                                | 2008 | Side View                      | **Tile-based Pixel Art**                      | [↗](https://en.wikipedia.org/wiki/Spelunky)                                 |
| **Plants vs. Zombies**                      | 2009 | Fixed Side / Orthographic      | **2D Cartoon Illustration**                   | [↗](https://en.wikipedia.org/wiki/Plants_vs._Zombies_%28video_game%29)      |
| **LIMBO**                                   | 2010 | Side View                      | **Monochrome Silhouette Art**                 | [↗](https://en.wikipedia.org/wiki/Limbo_%28video_game%29)                   |
| **Terraria**                                | 2011 | Side View                      | **Tile-based Pixel Art**                      | [↗](https://en.wikipedia.org/wiki/Terraria)                                 |
| **Rayman Origins**                          | 2011 | Side View                      | **Hand-drawn Digital Illustration**           | [↗](https://en.wikipedia.org/wiki/Rayman_Origins)                           |
| **The Binding of Isaac**                    | 2011 | Top-Down                       | **Hand-drawn Cartoon Sprite Art**             | [↗](https://en.wikipedia.org/wiki/The_Binding_of_Isaac_%28video_game%29)    |
| **FTL: Faster Than Light**                  | 2012 | Top-Down / Cutaway             | **Low-resolution Sci-fi Sprite Art**          | [↗](https://en.wikipedia.org/wiki/FTL:_Faster_Than_Light)                   |
| **Hotline Miami**                           | 2012 | Top-Down                       | **Neon Pixel Art**                            | [↗](https://en.wikipedia.org/wiki/Hotline_Miami)                            |
| **Mark of the Ninja**                       | 2012 | Side View                      | **Cel-style 2D Cartoon Art**                  | [↗](https://en.wikipedia.org/wiki/Mark_of_the_Ninja)                        |
| **Don't Starve**                            | 2013 | Three-quarter Top-down         | **Hand-drawn Inked Cutout Art**               | [↗](https://en.wikipedia.org/wiki/Don%27t_Starve)                           |
| **Papers, Please**                          | 2013 | Fixed First-person / Desk View | **Low-resolution Pixel Art**                  | [↗](https://en.wikipedia.org/wiki/Papers,_Please)                           |
| **Shovel Knight**                           | 2014 | Side View                      | **NES-style Pixel Art**                       | [↗](https://en.wikipedia.org/wiki/Shovel_Knight)                            |
| **The Binding of Isaac: Rebirth**           | 2014 | Top-Down                       | **Hand-drawn Raster Sprite Art**              | [↗](https://en.wikipedia.org/wiki/The_Binding_of_Isaac:_Rebirth)            |
| **Ori and the Blind Forest**                | 2015 | Side View                      | **Hand-painted 2D Digital Art**               | [↗](https://en.wikipedia.org/wiki/Ori_and_the_Blind_Forest)                 |
| **Undertale**                               | 2015 | Top-Down + Fixed Battle View   | **Low-resolution Pixel Art**                  | [↗](https://en.wikipedia.org/wiki/Undertale)                                |
| **Stardew Valley**                          | 2016 | Top-Down / Three-quarter       | **16-bit-style Pixel Art**                    | [↗](https://en.wikipedia.org/wiki/Stardew_Valley)                           |
| **Hyper Light Drifter**                     | 2016 | Top-Down / Three-quarter       | **High-detail Pixel Art**                     | [↗](https://en.wikipedia.org/wiki/Hyper_Light_Drifter)                      |
| **Enter the Gungeon**                       | 2016 | Top-Down                       | **Pixel Art**                                 | [↗](https://en.wikipedia.org/wiki/Enter_the_Gungeon)                        |
| **Hollow Knight**                           | 2017 | Side View                      | **Hand-drawn Ink-outline 2D Art**             | [↗](https://en.wikipedia.org/wiki/Hollow_Knight)                            |
| **Cuphead**                                 | 2017 | Side View                      | **1930s Rubber-hose Cel Animation**           | [↗](https://en.wikipedia.org/wiki/Cuphead)                                  |
| **Dead Cells**                              | 2018 | Side View                      | **Modern High-resolution Pixel Art**          | [↗](https://en.wikipedia.org/wiki/Dead_Cells)                               |
| **Celeste**                                 | 2018 | Side View                      | **Low-resolution Pixel Art**                  | [↗](https://en.wikipedia.org/wiki/Celeste_%28video_game%29)                 |
| **GRIS**                                    | 2018 | Side View                      | **Watercolor-and-Ink Illustration**           | [↗](https://en.wikipedia.org/wiki/Gris)                                     |
| **Into the Breach**                         | 2018 | Isometric / Tactical           | **Isometric Pixel Art**                       | [↗](https://en.wikipedia.org/wiki/Into_the_Breach)                          |
| **RimWorld**                                | 2018 | Top-Down                       | **Flat Orthographic 2D Sprite Art**           | [↗](https://en.wikipedia.org/wiki/RimWorld)                                 |
| **Slay the Spire**                          | 2019 | Fixed / Card-battle View       | **Hand-painted 2D Card Illustration**         | [↗](https://en.wikipedia.org/wiki/Slay_the_Spire)                           |
| **Katana ZERO**                             | 2019 | Side View                      | **Neo-retro Pixel Art**                       | [↗](https://en.wikipedia.org/wiki/Katana_Zero)                              |
| **Blasphemous**                             | 2019 | Side View                      | **High-detail Gothic Pixel Art**              | [↗](https://en.wikipedia.org/wiki/Blasphemous)                              |
| **Oxygen Not Included**                     | 2019 | Side Cutaway                   | **2D Cartoon Cutaway Art**                    | [↗](https://en.wikipedia.org/wiki/Oxygen_Not_Included)                      |
| **Factorio**                                | 2020 | Isometric / Oblique Top-down   | **Pre-rendered Industrial Sprite Art**        | [↗](https://en.wikipedia.org/wiki/Factorio)                                 |
| **Streets of Rage 4**                       | 2020 | Side View / Belt-scroller      | **Hand-drawn Comic-book 2D Art**              | [↗](https://en.wikipedia.org/wiki/Streets_of_Rage_4)                        |
| **Loop Hero**                               | 2021 | Oblique Top-down               | **Retro Pixel Art**                           | [↗](https://en.wikipedia.org/wiki/Loop_Hero)                                |
| **Vampire Survivors**                       | 2022 | Top-Down                       | **Retro Pixel Sprite Art**                    | [↗](https://en.wikipedia.org/wiki/Vampire_Survivors)                        |
| **Pizza Tower**                             | 2023 | Side View                      | **Hand-drawn Cartoon Sprite Art**             | [↗](https://en.wikipedia.org/wiki/Pizza_Tower)                              |
| **Sea of Stars**                            | 2023 | Top-Down / Three-quarter       | **High-detail 16-bit-style Pixel Art**        | [↗](https://en.wikipedia.org/wiki/Sea_of_Stars)                             |
| **Animal Well**                             | 2024 | Side View                      | **Low-resolution Atmospheric Pixel Art**      | [↗](https://en.wikipedia.org/wiki/Animal_Well)                              |
| **Nine Sols**                               | 2024 | Side View                      | **Hand-drawn 2D Animation**                   | [↗](https://en.wikipedia.org/wiki/Nine_Sols)                                |
| **Balatro**                                 | 2024 | Fixed / Tabletop UI            | **Pixel-art Card UI**                         | [↗](https://en.wikipedia.org/wiki/Balatro)                                  |

## Relationship to experiments

The [2D game style dictionary](../concept-studio/style-dictionary/README.md) consumes
selected game records from this catalog, verifies stronger sources, decomposes
them into neutral profiles, and records model-specific prompt and concept-to-asset
evidence. Experimental success does not mutate this global catalog automatically:
accepted changes return through a reviewed keyword record with their basis and
scope intact.

## Initial decisions

- The game list is global documentation, not a recipe or component contract.
- Game names remain searchable research anchors and never enter provider prompts.
- A game-first basis is the default for compound game-art vocabulary.
- Externally sourced art history and technical primitives may broaden the
  candidate vocabulary, but cannot claim game applicability without a linked
  game reference.
- Framing, projection, genre, subject, content, and asset role stay outside
  rendering style.
- The 76 supplied rows are preserved as seeds; verification and decomposition
  happen incrementally rather than rewriting the list from intuition.
