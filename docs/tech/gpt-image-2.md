# Image adapter quick reference

The quality-first route is OpenAI's Images API using `gpt-image-2` with native
alpha. OpenRouter remains the image route for explicit `ai` and `chroma`
compatibility modes. See the authoritative repository notes:

- [Provider operations](../providers.md)
- [Model adapter contract](../spec/model-gpt-image-2.md)
- [Component contract](../component-contract.md)

## Implementation checklist

- Read the selected route's allowlisted key server-side without logging it.
- Query or pin verified endpoint capabilities.
- Pass only advertised fields.
- Encode reference inputs as hosted/data URLs and preserve their order.
- Decode `data[].b64_json` inside the shared retry boundary.
- Verify non-empty decodable media and record the returned MIME type.
- Apply exact-dimension normalization as a deterministic recipe step.
- For the default `native` strategy, request `background="transparent"` and
  PNG, then validate decoded nontrivial alpha before persistence.
- For explicit `ai`, request a neutral grey or naturally isolated background
  and require validated background removal.
- Reserve exact `#FF00FF` plus deterministic local keying for the explicit
  degraded `chroma` fallback; never switch strategies automatically.
- Leave declared opaque assets unchanged.
- Persist provenance and a final content hash.
- Use five blind retries for transport and response-contract failures.

Do not project one route's fields onto another. Direct OpenAI supports
`background="transparent"` and PNG output for GPT Image 2. The verified
OpenRouter compatibility endpoint does not expose that transparent option.
