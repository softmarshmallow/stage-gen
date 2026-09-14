"""A provider-free movie sprite definition for the generic pipeline CLI."""

from stage_gen.recipes.movie_sprite_body_idle import create_pipeline

pipeline = create_pipeline(supplied_video_ref="actor.mkv", finish_ref="finish.json")
