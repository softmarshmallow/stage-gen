# World generation: the words, the prior art, and the split

> **Status: orientation, before any code.** Written 2026-09-06 for the survival
> world pass ("more interesting and more real: biome–object relationships, spawn
> rate and uniqueness, a larger map, sparse but clumped placement, parameterised
> and agnostic like Don't Starve or Minecraft"). Executable authority for what
> exists today: `src/stage_gen/recipes/oblique_survival/layout.py`; authored
> input: `[world]` in `survival.toml`, `[[biomes]]`, `[clutter]`, `[forage]`,
> `[plants]` in `ground.toml`, `family`/`density_share`/`biome_weights` per prop
> in `props.toml`. Nothing here is a contract yet.

## 1. What we have, in the words this note adopts

The current layout, described in the vocabulary of section 2 so the gaps are
visible at a glance:

| Stage | What `layout.py` does today | The term for it |
| --- | --- | --- |
| world | one 256 m square, flat, one seed, one random stream (`mulberry32`) | **world extent**; **single-stream determinism** |
| landmass | value noise + radial falloff, thresholded to `land_share` by quantile; camp bump; water ring at the edge | **height-less coast**; **quantile solve** |
| biomes | one value-noise field per non-base biome on an 8-cell lattice, thresholded to its share, plus a finer "islet" octave; overlaps go to the field furthest above its threshold | **threshold-field biomes** with **two octaves**; shares solved, not assumed |
| population | per family, `density × area` props; each candidate is a uniform point, rejected by camp clearing, **biome weight** (a Bernoulli thin), shore margin, and a **hard-core** separation radius; up to 40 tries per prop | **dart throwing with thinning** (a thinned Poisson process with a hard core) |
| pieces | litter, forage, plants: the same dart throwing at the biome's `density_per_100m2`, cell chosen from the biome's allowed list | **per-biome density map**, uniform within it |
| mobs | `mob_count` darts, off the camp | flat count, no habitat |
| set pieces | the camp: a tent and a firepit at fixed offsets; one road walked out of the clearing | **one hard-coded set piece**; one **path** |
| record | `layout.json` (entities, pieces, decals, road, counts, shares), two structural plates (`splat.png`, `biome_splat.png`) | the **layout record** and the **masks** |
| checks | `check_layout`: no overlap, on the square, nothing in the clearing, counts under their ceiling | **structural refusals** only; nothing measures the pattern |

What the record holds for `ember-hollow-v1` at 256 m: 2,471 entities
(786 grass tufts, 393 reeds, 295 boulders, 288 pines, 201 birches, 157 thorn
bushes, 126 ferns, 110 twig bushes, 101 snags, 12 hounds, the tent and the
fire), 6,554 litter pieces, 1,049 forage pieces, 4,588 plants. Uniform inside
each biome: a forest is the same forest everywhere, the meadow is the same
meadow. That evenness is the "not real" the request names.

Against the five asks:

1. **Biome–object relationship.** Exists as one number per prop per biome
   (`biome_weights`, a thinning probability). Missing: exclusives, co-occurrence
   (a thing that stands near another thing), avoidance, edge preference
   (reeds at the water, snags at the scree edge), and anything a biome says about
   its own roster.
2. **Spawn rate and uniqueness.** Everything is a density. There is no chance,
   no quota, no "at most three in the world", no "exactly one", no guarantee of
   a minimum.
3. **Larger map.** 256 m already. The record scales linearly with area; the host
   draws every card as a node (frustum-culled by Godot, never streamed), so a
   larger world is first a **runtime** question (chunked visibility) and only
   then a layout one. Sparse-but-clumped placement makes it cheaper: a 512 m
   world at a quarter of the density holds the same number of cards.
4. **Sparse but clumped.** The one thing dart throwing cannot produce. It needs a
   **cluster process** (section 2.4) and a measurement that says how clumped
   the result is (section 3).
5. **Agnostic, parameterised.** The generator already knows no prop names except
   two leaks: `_render_splat` paints canopy shade for `family == "tree"` in state
   `standing`, and `CAMP_PROP_IDS` hard-codes the set piece. Both should become
   authored attributes (a `canopy` on the prop; a set piece in the world file).

## 2. The vocabulary

Terms in bold are the ones this note proposes we use in code, docs and TOML.
Each row says what it means, where the games put it, and what we have.

### 2.1 The world and its fields

| Term | Meaning | Don't Starve | Minecraft | Us |
| --- | --- | --- | --- | --- |
| **world extent** | the playable area and its shape | a graph of rooms drawn into a fixed tile grid, sized small/medium/large | infinite, generated per 16×16 **chunk** | one square, `size_meters` |
| **field** | a scalar over the world (noise, distance, moisture) that other rules read | implicit in room placement | six **climate parameters** (temperature, humidity, continentalness, erosion, weirdness, depth) sampled from noise | value-noise fields for biomes and the coast |
| **noise** | the family of smooth random fields: value, Perlin, simplex; **octaves**/fBm stack scales; **lattice** or **frequency** sets the feature size; **domain warp** bends it | — | Perlin-based, many octaves, per-parameter | value noise, two octaves per biome (continent, islet), fixed lattice counts so a wider world has wider continents |
| **threshold solve** | pick the field level that yields an authored share (a quantile), rather than hoping the noise lands there | — | — | yes, for land and for every biome, with a 16-round correction; worth keeping, it is what makes `share = 0.24` true |
| **height field** | elevation; cliffs, water level, slopes | flat with tile height | 3D density field carved into terrain | none; the world is flat, water is a mask, not a level |
| **mask** | a rasterised yes/no or weight plate the runtime reads (walkable, biome, road, canopy) | tile ids | block ids | `splat.png` (road, canopy, land) and `biome_splat.png` (one channel per non-base biome) |

### 2.2 Biomes

| Term | Meaning | Don't Starve | Minecraft | Us |
| --- | --- | --- | --- | --- |
| **biome** | a region with one ground material, one climate and one roster | a **room** (a biome patch with its own contents), grouped into **tasks** (a cluster of rooms with a purpose), joined into a graph with **locks and keys** (progression gating) | a biome is a lookup on the six climate parameters (a **Whittaker**-style table generalised to 6-D); a biome owns its **feature** list | four `[[biomes]]`, one plate each, share-solved fields; the base owns the remainder |
| **adjacency** | which biomes may touch, and how a boundary is drawn | rooms are placed by graph edges, then Voronoi-relaxed, so adjacency is authored | climate continuity: neighbours differ by one parameter, so no desert beside snow | none; whichever field wins at a point; boundaries are feathered in the shader |
| **edge / ecotone** | the band where two biomes meet; many things live only there (reeds at water, scrub at a forest edge) | "edge" rooms exist as authored rooms | placement by **surface** or **heightmap** and by **block predicate** (e.g. next to water) | none; would be a distance-to-boundary field, cheap to derive from the plates |
| **roster / palette** | the objects a biome may hold | per room: `distributeprefabs = { evergreen = 6, rocks = 0.05, ... }` with a room-wide `distributepercent` | per biome: an ordered list of **placed features** by **decoration step** | inverted: the object names its biomes (`biome_weights`, `biomes = [...]` on a cell) |

### 2.3 Objects, population, spawning

| Term | Meaning | Don't Starve | Minecraft | Us |
| --- | --- | --- | --- | --- |
| **population** (world-gen) vs **spawning** (runtime) | placing at generation vs producing during play | prefabs at gen; spawners (bee boxes, burrows) at runtime; regrowth | features at gen; **mob spawning** by biome weights at runtime | population only; forage **regrow** is our one runtime respawn |
| **density** | expected count per area | `distributeprefabs` weights × `distributepercent` (fraction of a room's tiles that get something) | **count** placement modifier, per chunk | `[world.density]` per family per 100 m², split by `density_share` |
| **habitat / suitability** | how much an object likes a place; the ecology term is **habitat suitability**, the game term is **biome weight** | implicit in which rooms list the prefab | the biome's feature list; plus **noise_threshold_count** (count varies with a noise field) | `biome_weights`, a thin probability |
| **rarity** | probability that a candidate site is used at all | low `distributeprefabs` weights | **rarity_filter** (`chance = 1/N`) | none |
| **quota** | min and max per world; **unique** means exactly one | `countprefabs` (exact counts per room), `required` prefabs, **set pieces** placed once | structure sets with **spacing/separation**; no hard max, but spacing bounds it | a ceiling per prop, derived from density; no floor, no unique |
| **separation / hard core** | minimum distance between two things | prefab collision radius | structure **separation**; features check block predicates | `scatter_radius_meters`, respected with a bucket hash |
| **exclusion** | keep-out zones (the camp, the road, the shore) | room borders | block predicates | camp clearing, road margin, shore margin, prop footprints for pieces |
| **co-occurrence / attachment** | a thing placed relative to another thing (mushrooms under trees; pigs by pig houses) | set pieces; spawner prefabs that emit children | feature **environment_scan** and **block predicates**; compound features | none |
| **variant** | which look an instance takes | prefab variants | block state | `variants` with weights, from the instance's seed |
| **set piece / prefab arrangement / structure** | an authored composition dropped into the world | **set pieces** and **static layouts**, placed by count per world or per room | **structures** (villages, temples) with **structure sets** | the camp, hard-coded |
| **path / road / river** | linear features that connect or divide | roads between rooms in the graph | rivers as a noise band; no roads | one random walk out of the camp |

### 2.4 The mathematics of placement (the "scientific" side)

Point-pattern statistics is the field that names what we want. Its vocabulary
is exact, gateable, and it does not know what a tree is.

| Term | Meaning | Why it matters to us |
| --- | --- | --- |
| **point process** | a random set of points in the plane | every scatter is one; naming it lets us swap the process without touching the rules around it |
| **Poisson process** | points independent of each other, intensity λ per area; **inhomogeneous** when λ varies over a field | what dart throwing without collision is; `λ = density × habitat(x)` is the inhomogeneous version we already run |
| **hard-core process** (Matérn I/II) | a Poisson process thinned so no two points are closer than r | our collision radius; Matérn II (keep the earlier) is exactly "first accepted wins" |
| **Poisson-disk / blue noise** (Bridson) | points at least r apart *and* filling the space evenly | the opposite of clumped; right for things that must not stack but should cover (grass), wrong for forests |
| **cluster process** (Neyman–Scott; **Thomas** with Gaussian offspring, **Matérn cluster** with disc offspring) | invisible **parents** are a Poisson process; each parent has Poisson(μ) **children** scattered within σ or r | "sparse but clumped" in three numbers: parent density, mean cluster size, cluster radius; a grove is a parent, its pines are children |
| **Cox process** | a Poisson process whose intensity is itself a random field | a "density from noise" clumping, softer than parents; what Minecraft's noise-based counts are |
| **Gibbs / Strauss process** | pairwise attraction or repulsion between types | co-occurrence and avoidance as one model; heavier to sample (MCMC), probably not needed when attachment does the job |
| **marked point process** | points carrying a type and attributes | our entities: the mark is prop id, state, seed, radius |
| **intensity function** | λ(x): expected points per area at x | the product the generator computes: density × habitat × edge preference × exclusion |
| **aggregation index** (Clark–Evans R) | mean nearest-neighbour distance over its Poisson expectation: R < 1 clumped, 1 random, > 1 regular | one number per prop that says how clumped it came out; computable from the record; the gate can refuse a pattern that is not what was authored |
| **Ripley's K / pair-correlation g(r)** | how many neighbours within r compared with Poisson | the same, by scale: says *at what radius* the clumping lives, which is what "sparse but clumped" actually specifies |

Ecology adds two words that read well in authored files: **aggregation**
(clumping) and **dispersion** (evenness).

### 2.5 Determinism

| Term | Meaning | Minecraft | Us |
| --- | --- | --- | --- |
| **seed** | the one number that reproduces the world | world seed | `[world] seed` |
| **single stream** | one RNG consumed in order; any edit upstream reshuffles everything after it | — | yes: raising tree density moves every rock, bush and puddle |
| **salted / hashed draws** | each feature, chunk or cell draws from `hash(seed, salt, x, z)`; an edit moves only its own points | every placed feature has a **salt**; each chunk its own random | no; the biggest reason a parameter is not tunable today, and the first thing a new generator should do |
| **byte identity** | same inputs, same record, same bytes | — | required by the run's identity and the picture gate |

## 3. Scientific or borrowed?

Both, and they are not in conflict. The games are the *authoring* model; the
point-process vocabulary is the *engine* model and the *measurement*.

- **Take the authoring shape from Don't Starve and Minecraft.** Both are data
  tables an author edits with no engine knowledge: Don't Starve's room says
  "this much of me is covered, by these prefabs in these proportions, plus these
  exact counts and these set pieces"; Minecraft's biome says "these features in
  this order, each with a list of placement modifiers (count, rarity, where)".
  Both engines are agnostic: they know rooms and prefabs, or features and
  modifiers, never "forest" or "tree". That is the ask in item 5.
- **Take the engine from point processes**, because a cluster process *is*
  sparse-but-clumped with three authored numbers, an inhomogeneous intensity
  *is* biome weighting, and a hard core *is* our collision rule. We keep what we
  have and add the one thing missing, parents. Nothing needs MCMC.
- **Take the gate from point-pattern statistics.** Clark–Evans per prop and a
  pair correlation at the authored cluster radius are computed from the record
  in milliseconds. "Never gate what you can compute" applies: clumpiness is
  computable, so it is a refusal, not a review.
- **What not to take.** Minecraft's 3-D density carving and chunk streaming
  (we are flat and finite); Don't Starve's room graph with locks and keys
  (progression gating is a game decision, not a world one, and our biomes are
  fields, not tiles); Voronoi relaxation (our threshold-field biomes already
  give organic boundaries and solved shares).

## 4. The split: author, algorithm, contract

### 4.1 What the author controls (the attributes that "play the significant role")

World level, in a `world.toml` sibling of `ground.toml` (today's `[world]`
moves there; it has outgrown a table in `survival.toml`):

| Knob | Today | Proposed |
| --- | --- | --- |
| extent, seed | `size_meters`, `seed` | same, plus an optional shape (square, disc, band) |
| landmass | `land_share`, coast lattice, crinkle, shore margin | same |
| biomes | share, islet lattice and share | + `adjacency` (may touch / never), + an optional `edge_meters` band the roster can address |
| set pieces | the camp, in code | `[[set_pieces]]`: id, members (prop, state, offset), clearing, count per world (1 for the camp), where (biome, distance band from the spawn) |
| paths | one road | `[[paths]]`: from, to (a set piece or the coast), width, wander |
| population order | fixed in code (props, mobs, decals, pieces) | `[population] steps = [...]`, so a later step can attach to an earlier one |

Object level, per prop, per mob and per sheet cell (the object owns its
habitat, so adding an object never edits every biome):

| Knob | Today | Proposed |
| --- | --- | --- |
| habitat | `biome_weights` (0–1) | same, plus `edge = "water" | "biome" | "none"` and an `edge_meters` band |
| density | `[world.density]` per family × `density_share` | `density_per_100m2` on the object (the family budget goes; it was a workaround) |
| aggregation | none | `cluster = { parents_per_100m2, mean_size, radius_meters }`; absent means Poisson |
| rarity | none | `chance` per candidate cluster or site |
| quota | ceiling only | `min_per_world`, `max_per_world`; `unique = true` is min = max = 1 |
| attachment | none | `near = { prop = "pine", radius_meters = 2.5, chance = 0.4 }` (children of another type's points); `avoid = { ... }` |
| separation | `footprint` and `shadow` radii | same, plus optional `spacing_meters` for things that space themselves (Poisson-disk) |
| canopy, clearing | `family == "tree"` in code | `canopy_radius_meters` and `clearing_radius_meters` attributes |

### 4.2 What the algorithm does (and never knows)

1. Solve the fields: land, biomes, distance-to-water, distance-to-biome-edge,
   distance-to-set-piece. Quantile-solved to the authored shares.
2. Place set pieces (quota, where), then paths between them.
3. For each population step, for each object: build the intensity λ(x) from
   density × habitat × edge band × exclusion; sample by the object's process
   (Poisson, cluster with parents, attached to another object's points, or
   Poisson-disk); thin by rarity; enforce hard cores and quotas; top up to the
   minimum from the best remaining candidates.
4. Draw every point from `hash(seed, object_id, cell)`, so one knob moves one
   object.
5. Rasterise the masks: land, biomes, road, canopy (from the canopy attribute).
6. Measure and refuse: overlaps, quotas, Clark–Evans R per object against the
   authored aggregation (clustered objects must come out R < 1; spaced ones
   R > 1), and the pair correlation at the authored cluster radius.
7. Emit the record and a report (counts, shares, R and g(r) per object).

The algorithm knows objects by id, radii, habitat weights, process parameters
and quotas. It never knows "tree", "forest", "camp" or "hound". That is the
agnostic module: a `worldgen` component in `src/stage_gen/` (fields, processes,
masks, measures) that the survival recipe's `layout.py` binds to its props, the
way every recipe binds `gnode`. It is not `gnode` (media-free, but game-specific
by nature) and not `media`.

### 4.3 What the contract looks like

Three documents, each with a checked schema:

- **Authored input**: `world.toml` (`oblique-survival-world-v1`) for extent,
  landmass, biomes' spatial rules, set pieces, paths, population steps; and the
  per-object placement block on props, mobs and sheet cells (habitat, density,
  cluster, rarity, quota, attachment, canopy). Unknown keys refused; every
  number bounded; every reference (prop, biome, set piece) resolved offline.
- **Layout record**: `layout.json` as today, plus per-entity `cluster` (the
  parent id, so a runtime can treat a grove as a thing) and `set_piece`
  membership; plus a `report` block (counts, shares, R and g per object). The
  masks stay as they are, with canopy from the attribute instead of the family.
- **Invariants**, checked by the recipe and pinned by tests: byte identity per
  seed; an edit to one object's block moves only that object's points; shares
  and quotas hold; nothing overlaps, nothing stands off the land, nothing in a
  clearing; the measured aggregation matches the authored kind.

The Godot host and the web viewer read the record as they do now; a larger
world reaches them as more entities, and the chunked visibility that makes 512 m
cheap is a host change on its own, after this.

## 5. Open questions to settle before the first line

1. **Who owns the roster: the object or the biome?** This note says the object
   (habitat on the prop), with a biome allowed to add exclusives and caps. Don't
   Starve says the room. Object-owned keeps the generator agnostic and additive;
   biome-owned reads better to an author writing "the bog". Both can be
   projected to the same intensity; the question is which file an author opens.
2. **How large is "larger", and is it larger or emptier?** 512 m at a quarter
   density is the same card count and four times the walk. The host's
   visibility work decides whether 1 km is on the table.
3. **Does the world need a height field?** Cliffs and a water level are what
   make Minecraft and Don't Starve's coasts read. Ours is flat by the look
   contract (cards on a plane). A height *field* for rules (reeds low, scree
   high) without rendered relief is cheap and may be enough.
4. **Is progression gating (Don't Starve's locks and keys) a world rule or a
   game rule?** This note keeps it out of the generator.
