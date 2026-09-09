# Image adapter quick reference

The quality-first image family is GPT Image 2.5 Sunburst at
`quality="max"`. Direct OpenAI owns native-alpha generation and true multipart
edits; OpenRouter owns designated opaque and reference-conditioned work. fal
has verified native-alpha generation but is not integrated. See the
authoritative repository notes:

- [Provider operations](../models/providers.md)
- [GPT Image 2.5 provider contract](../models/gpt-image-2.5.md)
- [Component contract](../component-contract.md)

## Implementation checklist

- Read the selected route's allowlisted key server-side without logging it.
- Query or pin verified endpoint capabilities.
- Pass only fields supported by that route or proven by a bounded canary.
- Encode reference inputs as hosted/data URLs and preserve their order.
- Decode `data[].b64_json` inside the shared retry boundary.
- Verify non-empty decodable media and record the returned MIME type.
- Apply exact-dimension normalization as a deterministic recipe step.
- For direct native-alpha work, request `background="transparent"` and PNG,
  then validate decoded nontrivial alpha before persistence.
- Never send `input_fidelity`; Sunburst rejects it with HTTP 400.
- For OpenRouter, refuse transparent and masked-edit requests before spend;
  request opaque output for its selected roles and pace starts at the configured
  `STAGE_GEN_OPENROUTER_IMAGE_IPM` ceiling.
- For explicit compatibility `ai`, require validated background removal.
- Reserve exact `#FF00FF` plus deterministic local keying for the explicit
  degraded `chroma` fallback; never switch strategies automatically.
- Leave declared opaque assets unchanged.
- Persist provenance and a final content hash.
- Keep the component service as the sole retry owner: one initial attempt plus
  at most five retries.

Do not project one provider's fields onto another. Direct OpenAI documents
transparent PNG/WebP output for Sunburst. OpenRouter's verified Sunburst route
advertises only `auto` and `opaque`, and a live transparent request returned
HTTP 400. Flare and fal are not automatic substitutes.
