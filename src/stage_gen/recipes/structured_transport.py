"""Compatibility import for pipeline-owned structured transport helpers."""

import sys

from stage_gen.pipeline import structured_transport as _implementation
from stage_gen.pipeline.structured_transport import ATTEMPT_LEDGER_KIND as ATTEMPT_LEDGER_KIND
from stage_gen.pipeline.structured_transport import AttemptLedger as AttemptLedger
from stage_gen.pipeline.structured_transport import StructuredOperation as StructuredOperation
from stage_gen.pipeline.structured_transport import (
    decode_completion_wrapper as decode_completion_wrapper,
)
from stage_gen.pipeline.structured_transport import generate_structured as generate_structured
from stage_gen.pipeline.structured_transport import (
    inline_local_schema_refs as inline_local_schema_refs,
)
from stage_gen.pipeline.structured_transport import known_cost as known_cost

sys.modules[__name__] = _implementation
