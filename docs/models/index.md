# Models

These records capture verified hosted-model and provider request surfaces. They
do not declare runtime bindings; re-check current metadata and live behavior
before widening an adapter contract.

## Model records

- [GPT Image 2](gpt-image-2.md) — direct OpenAI, fal, and OpenRouter image-route
  capabilities and native-alpha evidence.
- [Eleven Text to Sound v2](../spec/model-eleven-text-to-sound-v2.md) — measured
  sound-effect generation boundary.
- [Eleven v3](../spec/model-eleven-v3.md) — measured speech-generation boundary.

## Provider operations

- [Provider operations](providers.md) — credentials, endpoints, retry ownership,
  response handling, and experimental boundaries shared by provider adapters.

Model records describe observed external capabilities. The binding table and
executable graph remain authoritative for what Stage Gen currently uses.
