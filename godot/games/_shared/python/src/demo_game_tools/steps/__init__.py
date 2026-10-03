"""gnode node types and builder helpers the games share.

Each module is one family: its node types (``@node``) and an ``add_*_steps`` helper that writes
the family's steps into a game's builder. A game's own ``nodes/*.py`` re-exports the types it
uses, so a workflow names them as its project's types and ``gnode.lock`` guards them there.
"""
