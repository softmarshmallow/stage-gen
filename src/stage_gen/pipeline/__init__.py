"""Public Python authoring and execution of caller-defined asset pipelines.

Compose ordinary GNode graphs and bind node implementations; no recipe subclass,
repository layout, game contract, provider config, or private module is required.
"""

from stage_gen.pipeline.api import (
    InputFiles,
    NodeBinding,
    PipelineContext,
    PipelineDefinition,
    PipelineGraph,
    PipelinePlan,
    PipelineRun,
    PipelineRunView,
    define,
    inspect,
    load_definition,
    plan,
    run,
    write_plan,
)
from stage_gen.pipeline.ports import (
    artifact_port,
    attempts_port,
    object_digest,
    record_port,
    text_digest,
)

__all__ = [
    "InputFiles",
    "NodeBinding",
    "PipelineContext",
    "PipelineDefinition",
    "PipelineGraph",
    "PipelinePlan",
    "PipelineRun",
    "PipelineRunView",
    "define",
    "inspect",
    "load_definition",
    "plan",
    "run",
    "write_plan",
    "artifact_port",
    "attempts_port",
    "object_digest",
    "record_port",
    "text_digest",
]
