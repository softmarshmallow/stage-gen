# OSS and IP policy

The repository is open source. Its prompts, examples, fixtures, committed
media, and documentation must be safe to redistribute and useful without
depending on somebody else's identity or catalog.

## Prompt policy

Do not request or imply imitation of a named:

- franchise, brand, product, character, or game;
- artist, studio, creator, performer, or recognizable living-creator style;
- album, composition, recording, track, or soundtrack; or
- proprietary asset pack or confidential project.

Describe the desired result with neutral visual or musical properties instead:
medium, palette, shape language, lighting, density, camera requested by that
recipe, tempo, instrumentation, mood, structure, and technical constraints.
Prompts must ask for original work and must not ask the model to reproduce
logos, signatures, lyrics, melodies, protected characters, or trade dress.

## Inputs and references

Only submit material you own, material you are licensed to transform for the
intended use, or material whose public-domain status you have verified. A URL
being publicly reachable is not permission. Record source, license, author,
and any attribution/notice obligations in the input manifest.

Do not commit a reference merely because it was used transiently in research.
Where a test can use geometry, synthetic color fields, or repository-authored
material, prefer that.

## Outputs

Generated does not mean automatically cleared. Before committing or shipping
an output:

1. review provider terms for the account and endpoint used;
2. inspect for recognizable protected material, logos, signatures, or copied
   text/music;
3. document prompt, provider/model, inputs, hashes, and post-processing;
4. record an artifact-specific redistribution decision and stable rights basis;
   and
5. retain any externally required attribution or provider notice.

The repository's BSD-3-Clause license covers its source code. It does not by
itself license user inputs, generated artifacts, model weights, hosted media,
or provider training data. Provenance is evidence, not a grant of rights.

Runtime-valid output is still `runtime-unreviewed`. It becomes
`repository-approved` only after the artifact-specific rights and human-review
requirements in [Generated-media publication](generated-media-publication.md)
pass. Recording a provider or model is operational provenance, not permission
to redistribute its output.

Music receives the same review. Do not source-separate, remix, transcode, or
otherwise derive a repository placeholder from an unlicensed recording. A
tool's software license does not license the recording processed by that tool.

Do not infer a generated-asset license from the repository's BSD-3-Clause
source license or apply CC0 as a blanket output policy. Any CC0 dedication must
be artifact-specific and supported by the recorded rights basis.

## Provider claims

Documentation may name a provider, model, or endpoint only where needed for
setup, implementation, reproducibility, or verified limitations. Do not turn
operational documentation into endorsement language. A provider endpoint's
existence does not establish training-data provenance or downstream clearance.

## Contribution checklist

- [ ] Prompt is neutral and requests original work.
- [ ] Every input/reference has a recorded rights basis.
- [ ] Every committed generated-media file is enumerated and has matching
      provenance plus a repository-approved rights status and basis.
- [ ] Output was reviewed for protected names, marks, characters, text, and
      recognizable visual or musical copying.
- [ ] No secret, signed URL, or private local path is committed.
- [ ] Documentation and history checks pass.

When rights are uncertain, do not commit the media. Keep the code path and use
a clearly labeled non-media placeholder until a cleared artifact exists.
