"""A provider-free movie sprite definition for the generic pipeline CLI."""

from stage_gen.workflows.movie_sprite import create_pipeline

pipeline = create_pipeline(supplied_video_ref="actor.mkv", finish_ref="finish.json")
