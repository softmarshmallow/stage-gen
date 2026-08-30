"""Ring 2 — first-party provider adapters.

This package deliberately imports nothing: adapters load only when their own
package is imported, so ``import gnode`` never pays for an HTTP client. Each
adapter is one attempt with injected credentials; retry, caller validation,
and persistence live in the ring-1 services.
"""
