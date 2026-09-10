# Image adapter quick reference

The quality-first image family is GPT Image 2.5 Sunburst at
`quality="max"`. OpenAI Images and fal expose explicit native-alpha generation,
reference-edit, and masked-edit routes; OpenRouter exposes `auto` and opaque
background modes but never satisfies a native-alpha requirement. Capability
policies seal one exact route per node, with an optional scalar
`STAGE_GEN_IMAGE_PROVIDER` override and no fallback. See the authoritative
repository notes:

- [Provider operations](../models/providers.md)
- [GPT Image 2.5 provider contract](../models/gpt-image-2.5.md)
- [Component contract](../component-contract.md)

## Implementation checklist

- Resolve and seal the exact route before checking its allowlisted key.
- Pin verified endpoint capabilities; never discover or fall back by credential.
- Pass only fields supported by that route or proven by a bounded canary.
- Encode reference inputs as hosted/data URLs and preserve their order.
- Decode OpenAI/OpenRouter `data[].b64_json` inside the shared retry boundary;
  for fal, decode its single `images[].url` data URI or securely download that
  URL inside the same boundary before inspecting the bytes.
- Verify non-empty decodable media and record the returned MIME type.
- Apply exact-dimension normalization as a deterministic recipe step.
- For OpenAI or fal native-alpha work, request `background="transparent"` and PNG,
  then validate decoded nontrivial alpha before persistence.
- Never send `input_fidelity`; Sunburst rejects it with HTTP 400.
- For OpenRouter, refuse transparent and masked-edit requests before spend;
  request `auto` or opaque output exactly as sealed for the selected role and
  pace starts at the configured `STAGE_GEN_OPENROUTER_IMAGE_IPM` ceiling.
- For explicit compatibility `ai`, require validated background removal.
- Reserve exact `#FF00FF` plus deterministic local keying for the explicit
  degraded `chroma` fallback; never switch strategies automatically.
- Leave declared opaque assets unchanged.
- Persist provenance and a final content hash.
- Keep the component service as the sole retry owner: one initial attempt plus
  at most five retries.

Do not project one provider's fields onto another. OpenAI Images and fal
document transparent PNG/WebP output for Sunburst. OpenRouter's verified
Sunburst route advertises only `auto` and `opaque`, and a live transparent
request returned HTTP 400. Flare and the Responses image tool are not registered;
fal is selected only by an exact checked-in policy or the explicit scalar
override.
