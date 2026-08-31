# Universe ontology and visual explanation taxonomy

> **Contract maturity: ratified V0 target, documentation-only.**
>
> This document defines the first semantic contract for universe-oriented
> generation in `stage-gen`: the minimal storyworld ontology, relationships,
> identity markers, narrative roles, explanatory asset obligations, and
> ratification rules from which a future universe recipe may be built.
>
> V0 deliberately starts with an agnostic core. It is not the permanent ceiling
> of the taxonomy. Future genre profiles MAY widen the authored vocabulary with
> standard classes such as planets for science fiction, but they MUST project
> those additions onto this core rather than replace it.
>
> This specification does not claim implementation support. It ratifies the
> conceptual source and output roles, including the minimum generic V1
> consumer, but it does not define a serialized schema, root filename, node
> registry, execution graph, provider operation, persisted manifest shape,
> route implementation, or migration plan. The current
> [prepared-game contracts](../../game-contract.md) and recipes remain
> unchanged.

## Purpose

A universe-oriented package exists to make a storyworld understandable and
engaging through art, diagrams, structured relationships, and narrative entry
points. It is not a game package with gameplay removed. A universe may be
organized around a continent, galaxy, city, building, vehicle, institution,
historical rupture, ecological cycle, or another coherent subject.

Franchise-specific browsing categories are useful presentation choices, but
they are not stable ontology roots. A science-fiction universe may expose
`planets`, `droids`, and `vehicles`; a magical-school universe may expose
`houses`, `spells`, and `artifacts`; a universe contained inside one building
may expose `sectors`, `departments`, and `anomalous objects`. The authored core
MUST remain valid when any one of those collections is absent.

V0 therefore separates four concerns:

1. **entities** state what exists;
2. **relationships and roles** state how subjects participate in the world;
3. **explanatory assets** state what an audience needs to see or understand;
4. **engagement projections** arrange those assets for a particular genre and
   audience experience.

## Conceptual source inputs

The first universe-expansion workflow receives three distinct required source
roles. A future serialized contract MAY store their values inline or by
digest-bound reference, but it MUST preserve their roles rather than flatten
them into one undifferentiated prompt.

### Poster

The **poster** is one static visual source: movie poster, key art, cover,
one-sheet, or another image that establishes visual evidence and an initial
design grammar. It is neither an exhaustive world model nor automatic proof of
every depicted detail. Promotional typography, performer likeness, layout,
and marketing composition MUST NOT silently become storyworld canon.

A future executable contract MUST bind the exact source bytes and record the
rights basis for using the image as a reference.

### Synopsis

The **synopsis** is the explicit textual account of the premise, subjects,
conflicts, setting, and present state supplied by the author. Its claims are
source facts unless they are internally contradictory or explicitly marked as
uncertain, disputed, or perspectival.

### Expansion direction

The **expansion direction** is an instruction about how the universe should be
ratified or expanded: its desired scope, emphasis, depth, omissions, audience
entry, and acceptable degree of invention. It is not itself a description of
the world. It MAY request, for example, deeper institutions, a building-scale
explanation, or preservation of mystery. It MUST NOT silently override a
source fact; an intentional reinterpretation or divergence must be exposed as
such.

### Source authority and lineage

Ratification MUST reconcile the three inputs without confusing their
authority. Accepted claims MUST distinguish at least:

- authored facts stated by the synopsis;
- literal visual observations supported by the poster;
- conservative inferences needed to connect supplied evidence; and
- generated extensions admitted because they satisfy the expansion direction.

Unresolved conflicts between sources MUST remain visible for review. The
poster supplies visual evidence and grammar, the synopsis supplies explicit
world claims, and the expansion direction controls the transformation. None of
the three is permission to hide unsupported assumptions.

Source-evidence bindings and expansion rationale are distinct. A direction
requirement MAY justify admitting a generated extension, but it MUST NOT be
recorded as factual evidence that the extension already existed in the poster
or synopsis. Display summaries, audience viewpoints, and asset descriptions
MUST bind to lineaged canonical facts rather than becoming an untracked second
place to invent canon.

## Conceptual target outputs

A successful universe-expansion workflow produces one coherent package with
four connected output roles:

1. an **expanded universe document** containing the premise, viewpoints,
   present state, canonical entities, and the facts needed to explain them;
2. a **relational graph** containing stable entity identities and typed,
   scoped relationships, including perspective or temporal qualification when
   needed;
3. an **explanatory asset set** whose records bind each asset to its purpose,
   canonical subjects, applicable relationships, and expressed world facts;
   and
4. a **ratification record** exposing source lineage, generated extensions,
   unresolved questions, validation findings, coverage decisions, and
   revision identity.

Output cardinality is intentionally irregular. A universe MAY contain no
vehicles, many rooms, one central event, several overlapping place layers, or
hundreds of actor-to-collective relationships. Neither generation nor a
generic consumer may require empty franchise-shaped categories to make the
package look regular.

The relational graph is a semantic storyworld graph and MAY contain cycles.
It is not the acyclic execution graph used to schedule generation work. An
asset record is connected to the graph through stable subject and relationship
identities; a file path or gallery position is not semantic identity.

"Ratified" means admitted as coherent authored meaning. It does not mean that
generated media has passed semantic review, been accepted for publication, or
been activated by a public consumer.

## Ownership and library boundary

Future authored universe inputs will live under `library/games/<project_id>/`
as requested for the shared project library. The directory is an ownership and
discovery boundary; it does not assert that every project is playable.

V0 does not ratify the package root filename or allow universe-only files to be
added to the currently selected prepared-game closure. The current
`game.toml`-rooted validator, selector, and runtime manifest continue to own
prepared games until a separate executable universe contract is implemented.

The universe contract will own semantic subjects and visual-explanation
requirements. A future consumer will own browsing, layout, interaction, and
presentation. Generic `gnode` machinery will own execution mechanics only; it
MUST NOT acquire storyworld, genre, or universe-taxonomy semantics.

This storyworld taxonomy is also distinct from the existing
[asset taxonomy](../asset-taxonomy.md), which names executable module and node
types by asset space, camera, genre, and module. An entity class such as
`place` is authored meaning; it is not itself a node `type_id`. A future recipe
may fan one place into several typed generation and validation nodes without
collapsing those two namespaces.

## Normative language

The words **MUST**, **MUST NOT**, **SHOULD**, and **MAY** below are normative for
future universe contract, recipe, and consumer design. They do not change
current runtime behavior.

## Model overview

```text
universe
├── identity and premise
├── audience viewpoints
├── entities
│   ├── actors
│   ├── collectives
│   ├── places
│   ├── things
│   ├── kinds
│   ├── systems
│   ├── events
│   └── ideas
├── relationships
│   ├── spatial
│   ├── social and political
│   ├── material and functional
│   ├── taxonomic
│   ├── causal and historical
│   └── symbolic
├── identity markers
├── narrative roles
├── explanatory assets
└── engagement projections
```

Each branch is independently extensible. A genre profile MAY add narrower
vocabulary and obligations, but it MUST declare how each addition relates to
the V0 model.

## Canonical entity classes

### Actor

An **actor** is an individual subject capable of action, intention, experience,
or viewpoint within the storyworld.

Actors include people, named creatures, droids with agency, artificial
intelligences, spirits, and sentient artifacts. An actor need not be human,
biological, playable, heroic, or fully autonomous.

A generic creature species is not an actor; it is a `kind`. A named member of
that species MAY be an actor. A non-agent machine is a `thing`, even when it
resembles an actor.

### Collective

A **collective** is a plurality of actors with a shared identity, authority,
purpose, membership, or capacity for coordinated action.

Collectives include nations, houses, clans, factions, companies, religions,
crews, schools, institutions, orders, and political movements. A population
kind does not automatically form one collective: a species is a `kind`, while
a civilization, diaspora, government, or organization formed by its members is
a `collective`.

### Place

A **place** is a locus that can contain subjects, be entered or observed, and
participate in spatial relationships.

Places include realms, planets, regions, cities, settlements, buildings,
rooms, vehicle interiors, dream-spaces, and overlapping dimensions. V0 does
not prescribe a physical subdivision ladder. `planet`, `district`, `floor`,
and `carriage` are domain-specific place kinds, not universal hierarchy levels.

### Thing

A **thing** is a bounded material or informational subject whose identity is
meaningful to the universe.

Things include artifacts, resources, weapons, vehicles, machines, garments,
food, documents, works of art, currencies, substances, and tools. Natural and
manufactured subjects both qualify. A thing MAY also carry a `place` facet when
it contains meaningful locations, or an `actor` facet when it possesses agency.

### Kind

A **kind** is a reusable category whose members share world-significant traits.

Kinds include species, creature types, plant kinds, droid models, vehicle
classes, artifact classes, and other classifications whose common properties
must be explained. A kind is not a substitute for a collective: shared anatomy
or manufacture does not imply shared government, membership, or intent.

### System

A **system** is a repeatable rule, process, infrastructure, or circulation that
causes recognizable consequences in the world.

Systems include magic, ecology, climate, economy, law, transportation,
technology, bureaucracy, education, resource circulation, and ritual practice.
A system MUST be connected to at least one actor, collective, place, thing,
kind, event, or idea that visibly demonstrates its operation.

### Event

An **event** is a bounded change in time that alters the state or interpretation
of the universe.

Events include foundings, wars, migrations, discoveries, catastrophes,
successions, inventions, disappearances, and revelations. An event MUST record
what participated and what changed; a date without consequence is chronology,
not a sufficient universe event.

### Idea

An **idea** is a belief, doctrine, value, prophecy, taboo, law, interpretation,
or other meaning-bearing subject that influences the world.

Ideas include codes of honor, religious beliefs, political doctrines,
scientific theories, blood ideologies, prophecies, public myths, and forbidden
knowledge. An idea MUST be connected to actors or collectives that hold,
contest, enforce, embody, or suffer from it.

## Primary class and additional facets

Entity classes are semantic facets rather than mutually exclusive content
folders. Each entity MUST declare one primary class for identity, indexing, and
default asset obligations. It MAY declare additional facets when those facets
materially change how the subject must be explained.

Examples:

| Subject | Primary class | Additional facet | Consequence |
| --- | --- | --- | --- |
| A freighter used as the crew's home | `thing` | `place` | Needs both object and interior-orientation coverage |
| A sentient starship | `actor` | `thing`, `place` | Needs identity, function, and inhabited-space coverage |
| A named magical sword with agency | `actor` | `thing` | Needs character and artifact relationships |
| A nation-state | `collective` | `place` only when territory is identical to its identity | Government and territory remain distinguishable |
| A droid model | `kind` | — | Individual droids remain separate actors or things |

Facets MUST NOT duplicate one subject into disconnected records. They add
obligations and relationships to one durable identity.

## Audience viewpoint

`player` is not a V0 entity class. The more general invariant is an **audience
viewpoint**: the declared entry through which a person first encounters the
universe.

A viewpoint MAY be anchored to any major entity or question:

- an actor whose experience introduces the world;
- a place the audience enters or surveys;
- a collective whose conflict organizes discovery;
- an event whose causes and consequences reveal the present;
- a thing whose ownership or journey crosses the universe; or
- a mystery whose evidence links otherwise separate subjects.

A viewpoint states what is initially known, what scale is visible, and which
questions lead deeper. A playable consumer MAY bind an actor viewpoint to a
player role, but the universe ontology MUST NOT assume control, simulation, or
gameplay.

Every universe MUST declare at least one audience viewpoint. It SHOULD declare
several when different entry paths explain materially different aspects of the
same world.

## Place topology

V0 standardizes spatial relationships rather than physical subdivision names.
Places MAY form trees, graphs, overlapping layers, or mobile containment.

The initial universal spatial relationships are:

| Relationship | Meaning |
| --- | --- |
| `contains` / `located_in` | Part-whole spatial containment |
| `adjacent_to` | Subjects share a meaningful boundary or immediate vicinity |
| `connected_to` | A route, portal, corridor, service, or other link exists |
| `reachable_from` | Traversal is possible under stated conditions |
| `overlaps` | Places coexist in some spatial extent without simple containment |
| `hidden_within` | Containment exists but is concealed or unavailable to ordinary observation |
| `moves_through` | A mobile place or thing changes location relative to other places |
| `mirrors` | One place structurally or symbolically corresponds to another |
| `replaces` | One place occupies the role or extent of another across time or state |

An orientation asset MUST project the actual topology. It MUST NOT force a
geographical world map onto a building, train, dimension stack, social network,
or other incompatible universe.

## Universal relationship families

Relationships are canonical world facts, not captions invented by a consumer.
Every major entity MUST participate in at least one meaningful relationship.

### Spatial

- located in;
- contains;
- connects to;
- borders;
- originates from; and
- travels through.

### Social and political

- member of;
- leads;
- serves;
- governs;
- represents;
- allied with;
- opposes;
- protects; and
- exploits.

### Material and functional

- owns;
- uses;
- created;
- requires;
- produces;
- consumes;
- made from;
- powers; and
- damages.

### Taxonomic

- instance of;
- variant of;
- descended from; and
- related to.

### Causal and historical

- caused;
- participated in;
- changed by;
- preceded;
- resulted in;
- prevents; and
- depends on.

### Symbolic

- represents;
- identified by;
- sacred to;
- forbidden by; and
- commemorates.

Future schemas MAY define a closed relationship vocabulary with exact inverse,
cardinality, and temporal rules. V0 ratifies the families and ownership
boundary, not their serialization.

## Identity markers, flags, and symbols

A literal flag is not universal. An **identity marker** is.

An identity marker is a perceivable device through which an actor, collective,
place, thing, system, or idea is recognized. Valid forms include:

- flag or banner;
- sigil, crest, or seal;
- logo;
- glyph or rune;
- totem;
- tattoo;
- uniform marking or vehicle livery;
- color pairing or repeated pattern;
- material or architectural motif;
- gesture;
- written script; and
- sound or musical motif.

Every major collective MUST have at least one recognizable identity marker.
The selected form MUST follow the collective's culture, technology, materials,
institutions, and public behavior. A generator MUST NOT create a flag merely
because flags are common in another universe.

Every major place MUST have at least one place marker, such as a landmark,
skyline, material palette, environmental phenomenon, signage system, or
architectural silhouette.

An identity marker remains attached visual identity when it only identifies a
subject. It MUST also become a canonical `thing` when it has independent
history, ownership, power, physical custody, or conflict.

The standard visual set for a major collective's marker is:

1. primary mark;
2. construction and variant sheet;
3. color and material usage;
4. at least one culturally correct applied use;
5. comparison against visually adjacent collectives; and
6. meaning and historical origin when the world assigns either one.

## Culture is composition

`culture` is not a V0 entity class. It is an explanatory composition across:

```text
collective
+ inhabited places
+ held or contested ideas
+ practiced systems
+ made and used things
+ remembered events
+ identity markers
+ relationships with others
```

This composition may produce clothing, architecture, food, tools, rituals,
ornament, language, authority, family structure, and attitudes toward
resources, death, outsiders, magic, technology, or history. The facts remain
owned by their canonical entities and relationships rather than being copied
into one undifferentiated culture record.

## Narrative roles

Entity class states what a subject is. Narrative role states how it functions
for one story, viewpoint, relationship, or explanation. Roles are contextual
and MUST NOT be treated as permanent identity.

Initial actor roles include:

- viewpoint;
- protagonist;
- opponent;
- ally;
- guide;
- gatekeeper;
- witness;
- victim;
- beneficiary;
- catalyst; and
- custodian.

Initial place roles include:

- home;
- destination;
- seat of power;
- frontier;
- sanctuary;
- prison;
- passage;
- threshold;
- contested territory;
- ruin; and
- forbidden zone.

Initial thing roles include:

- tool;
- resource;
- weapon;
- transport;
- key;
- evidence;
- relic;
- burden;
- status marker; and
- symbol.

Initial event roles include:

- origin;
- rupture;
- escalation;
- revelation;
- transformation;
- collapse; and
- aftermath.

The same place MAY be home to one actor and occupied territory to another. The
role therefore belongs to the applicable perspective or relationship, not to
the place in isolation.

## Explanatory asset purposes

An explanatory asset is required because it answers an audience question, not
because its media format is attractive or common in a reference franchise.

| Purpose | Audience question |
| --- | --- |
| `orient` | Where is it, and how can subjects be reached? |
| `identify` | How do I recognize it? |
| `differentiate` | How is it unlike related subjects? |
| `explain` | How does it work? |
| `connect` | What does it affect, use, oppose, or depend on? |
| `historicize` | Why is it like this now? |
| `humanize` | How is it experienced in ordinary life? |
| `immerse` | What does it feel like to encounter or inhabit? |
| `invite` | What question should make the audience continue? |

Every required public asset MUST declare one primary purpose, one or more
canonical subjects, and the world facts it is responsible for expressing. A
beautiful image that answers no contracted question is promotional art, not
required universe coverage.

## Standard visual modules by entity class

These modules are default candidates, not unconditional fan-out. Ratification
selects them according to entity salience, facets, relationships, viewpoint,
genre profile, and identified explanatory gaps.

| Subject | Minimum explanatory coverage | Conditional modules |
| --- | --- | --- |
| Actor | Identity portrait; character-in-world scene | Role pose, signature-thing interaction, relationship tableau, historical or status variant |
| Collective | Identity marker; representative members; public manifestation | Uniform kit, structure diagram, territory, internal groups, rival comparison |
| Place | Orientation representation; establishing view; inhabited view | Floor plan, cutaway, route, material plate, historical reconstruction |
| Thing | Clear hero view; in-use context | Scale sheet, exploded diagram, variants, provenance, ownership history |
| Kind | Representative specimen; comparison or scale plate | Variants, lifecycle, habitat, anatomy, behavior |
| System | Causal explanation; visible manifestation | Inputs and outputs, exception, failure state, social consequence |
| Event | Key-moment tableau; participants and place | Before and after, timeline position, causes, consequences, disputed account |
| Idea | Symbolic expression; practiced or contested scene | Competing interpretation, ritual, propaganda, prohibition |

The universe as a whole MUST receive:

- one entry artwork or equivalent visual invitation;
- at least one topology-appropriate orientation experience;
- at least one relationship overview;
- a present-state or historical overview;
- a visual identity grammar; and
- at least one narrative gateway into deeper material.

## Character world profile and pose derivation

Universe actors do not require gameplay statistics by default. A major actor
SHOULD instead provide world-facing attributes such as:

- origin and home;
- collective and cultural affiliation;
- social or institutional role;
- status and resources;
- capabilities and limitations;
- beliefs;
- goals and obligations;
- important relationships;
- historical involvement;
- signature thing;
- visual codes; and
- present tension or contradiction.

Pose, held object, environment, and action MUST be derived from those facts.
They MUST NOT be selected as disconnected visual decoration. The intended
derivation is:

```text
actor role
+ current intention
+ social status
+ relationship to place
+ relationship to thing or system
→ contextual actor artwork
```

A neutral turnaround MAY be generated for consistency control, but it does not
replace an audience-facing character-in-world explanation.

## Public assets and production-control assets

Audience-facing universe assets and internal generation controls are distinct
contracts.

Public assets explain subjects through maps, vistas, scenes, diagrams,
portraits, dossiers, timelines, symbols, stories, and other presentations.

Production-control assets keep generation coherent and MAY include:

- world visual grammar;
- scale chart;
- regional palette and material language;
- architecture grammar;
- costume grammar;
- symbol and heraldry lexicon;
- technology or magic design rules; and
- actor-to-environment compatibility boards.

An internal control asset MUST NOT be presented as sufficient public universe
coverage merely because it is visually complete.

## Engagement projections

Engagement projections compose canonical entities, relationships, and assets
without becoming ontology classes. Initial projection families include:

- atlas or spatial explorer;
- field guide;
- actor, collective, or artifact dossier;
- timeline explorer;
- blueprint or building explorer;
- artifact archive;
- bestiary;
- illustrated encyclopedia;
- comic or short visual story;
- guided tour;
- investigation board;
- actor journey; and
- culture, era, or faction comparison.

A map and a comic are therefore not peer ontology categories. A map primarily
orients; a comic is an engagement projection that composes actors, places,
things, events, and ideas.

## V1 generic consumer baseline

Because universe outputs have irregular classes, cardinality, topology, and
media, the minimum V1 consumer is a generic **graph explorer plus gallery**.
It is a package reader, not a second universe generator.

The graph explorer MUST:

- read canonical entities and relationships rather than execution nodes;
- support cyclic semantic relationships;
- filter by core class, declared narrower kind, and relationship family;
- expose the selected subject's facts, lineage, neighbors, and bound assets;
  and
- treat layout coordinates and clustering as client-owned presentation, not
  canonical world facts.

The gallery MUST:

- index every explanatory asset record without assuming a fixed asset census;
- filter by explanatory purpose, subject, core class, narrower kind, and media
  kind;
- cross-link selections back to their canonical subjects and relationships;
- expose metadata and a safe open or download path when it cannot present a
  media kind inline; and
- preserve review and publication state rather than treating file presence as
  acceptance.

The existing `/universe/demo` illustrated-map route remains a specialized map
spike. It demonstrates a possible image-space orientation projection, but its
current manifest does not carry the universe subject, relationship, fact,
review, and publication bindings required of a conforming explanatory asset.
A future binding or adapter MAY connect it to the canonical package; the map
manifest is not the root universe contract and MUST NOT be widened into one.
Atlas, timeline, blueprint, dossier, investigation, and other refined
experiences MAY later consume the same canonical package.

## V0 ratification rules

Before generation, a future universe ratifier MUST establish all of the
following:

1. At least one audience viewpoint exists.
2. At least one place exists.
3. Every major entity has meaningful relationships.
4. Every major actor is connected to a place and to at least one collective,
   thing, system, event, or idea.
5. Every major place has both orientation and experiential coverage.
6. Every major collective has a culturally appropriate identity marker and an
   applied manifestation.
7. Every major system has a visible consequence for another entity.
8. Every major event changes the state or interpretation of another entity.
9. No empty franchise-shaped category is required.
10. No public asset is required solely because a reference universe had one.
11. Every required artwork states the audience question it answers.
12. No major entity is explained only through prose when its defining
    properties are visual or spatial.
13. Every accepted world claim records its source or generated-extension
    lineage.
14. The result satisfies the expansion direction without presenting that
    direction as a world fact.
15. Source conflicts and deliberate reinterpretations remain visible for
    review.
16. The semantic graph passes ontology, relationship, identity, and coverage
    admission before paid visual fan-out begins.

Ratification MUST reject or return for revision:

- orphan entities;
- duplicate identities or unresolved aliases;
- contradictory relationships;
- systems without consequences;
- places without inhabitants, activity, or an explicit reason for emptiness;
- actors whose appearance has no world-derived cause;
- identity markers with no cultural or institutional basis;
- things disconnected from economy, occupation, history, system, or plot; and
- concept art that communicates mood but no contracted world fact.

Ratification is semantic admission, not provider retry. A failed world model
must be revised or regenerated as authored meaning before paid visual fan-out.

## Reference-category mapping

The familiar science-fiction databank categories demonstrate how one genre
projection maps into V0 without becoming the universal core:

| Databank category | V0 mapping |
| --- | --- |
| Characters | `actor` |
| Creatures | Named creature: `actor`; creature type: `kind` |
| Droids | `actor`, `thing`, or `kind` according to agency and scope |
| Locations | `place` |
| Organizations | `collective` |
| Species | `kind` |
| Vehicles | `thing`, optionally with a `place` facet |
| Weapons and technology | `thing` and/or `system` |
| More | `event`, `idea`, `system`, or a composed engagement projection |

This mapping allows a science-fiction profile to standardize `planet`,
`droid`, `vehicle`, or `weapon` later without requiring empty equivalents in a
building, historical, or magical universe.

## Genre-profile widening

V0 is the required semantic substrate. A future genre profile MAY widen it
with standard subject classes, subtypes, relationships, fields, asset modules,
and coverage rules when the genre makes those additions consistently useful.

A valid extension MUST declare:

1. the genre or higher-level universe family it serves;
2. the new vocabulary it introduces;
3. the V0 class or facet each addition refines;
4. whether each addition is required, conditionally required, or optional;
5. the relationships and explanatory questions it enables;
6. the visual modules it adds or specializes; and
7. why an open authored kind is insufficient.

For example, a future science-fiction profile could promote `planet` to a
standard place subtype with orbit, environment, settlement, political, and
travel obligations. It could standardize the class even when one particular
universe leaves some instances unused. That decision belongs to the genre
profile, not to V0.

Genre profiles MUST NOT redefine the meaning of an existing V0 class, make
their vocabulary mandatory outside their declared scope, or push genre
semantics into generic `gnode` rings.

## Versioning and next authority

This document is the V0 semantic authority. The next contract work SHOULD test
it against the agreed reference set: region-led fantasy, ecology-led science
fiction, city-led science fiction, building-led mystery, galaxy-scale
databanks, and archaeology-led fantasy.

That comparison should determine:

- which visual modules are universal requirements;
- which are conditionally required by entity or relationship;
- which belong to genre profiles;
- which engagement projections deserve first-party support; and
- where V0 is too agnostic to produce a useful authored discipline.

Only after those decisions are ratified should the exact serialized schema,
staged node topology, persisted manifest shape, implementation, and specialized
consumer contracts be proposed. The conceptual source roles, target output
roles, and generic V1 graph-and-gallery baseline above are already part of this
V0 authority.
