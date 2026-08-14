# Image adapter quick reference

The current image route is OpenRouter's dedicated image API using
`openai/gpt-image-2`. See the authoritative repository notes:

- [Provider operations](../providers.md)
- [Model adapter contract](../spec/model-gpt-image-2.md)
- [Component contract](../component-contract.md)

## Implementation checklist

- Read `OPENROUTER_API_KEY` server-side without logging it.
- Query or pin verified endpoint capabilities.
- Pass only advertised fields.
- Encode reference inputs as hosted/data URLs and preserve their order.
- Decode `data[].b64_json` inside the shared retry boundary.
- Verify non-empty decodable media and record the returned MIME type.
- Apply exact-dimension normalization as a deterministic recipe step.
- For the default `ai` strategy, request a neutral grey or naturally isolated
  background and require validated background removal when alpha is required.
- Reserve exact `#FF00FF` plus deterministic local keying for the explicit
  degraded `chroma` fallback; never switch strategies automatically.
- Leave declared opaque assets unchanged.
- Persist provenance and a final content hash.
- Use five blind retries for transport and response-contract failures.

Do not revive assumptions from the previous gateway integration. In
particular, arbitrary `size`, transparent background, fixed output format, and
provider-native edit/mask fields are not part of the currently verified
OpenRouter endpoint contract unless live capability metadata adds them.
