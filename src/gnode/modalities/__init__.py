"""Ring 1 — per-modality model specs and their retry-owning services.

Each modality package owns the request/response types for one capability, a
versioned one-attempt model protocol, and the single retry owner that
validates and atomically persists the artifact with its provenance. Nothing
here names a provider, reads the environment, or knows a game exists.
"""
