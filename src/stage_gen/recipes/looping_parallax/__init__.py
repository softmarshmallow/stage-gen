"""A supplied-layer parallax asset recipe with independent preparation caches."""

from stage_gen.components.sideview_layers.parallax import ParallaxLayer, ParallaxSpec

from .pipeline import create_pipeline

__all__ = ["ParallaxLayer", "ParallaxSpec", "create_pipeline"]
