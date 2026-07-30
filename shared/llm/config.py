"""Per-task LLM configuration — THE ONLY MODULE THAT KNOWS A MODEL NAME.

Constraint C-2. `shared/tests/test_no_hardcoded_models.py` scans the repository
and fails if a model identifier appears anywhere outside `shared/llm/`, so this
file and `pricing.py` are the whole surface.

Defaults target local inference through Ollama: free, no API key, no quota, and
nothing leaves the machine — which is what makes SRS §6.3 and §9.2 ("input
content shall not be used for model training") true by construction rather than
by a provider's promise. Every free hosted tier trains on submitted content by
default, which for a product handling other people's unpublished project work
is a real problem, not a footnote.

Overridable per deployment via LLM_PROVIDER / LLM_MODEL, which is configuration
rather than code and so does not weaken the constraint.
"""

import os
from dataclasses import dataclass

from llm.errors import UnknownTaskError

DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")

DEFAULT_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")
"""7B at Q4 sits entirely inside 8GB of VRAM, so generation runs on the GPU
rather than spilling to CPU. `qwen2.5:14b` extracts noticeably better and still
runs on an 8GB card with partial offload, at roughly a third of the speed —
switch via LLM_MODEL once you have a feel for the quality you need."""


@dataclass(frozen=True)
class TaskConfig:
    """Everything one task needs, in one place.

    `system_prompt` lives here rather than being passed by callers on purpose:
    a caller supplies data, never instructions, so a compromised or careless
    call site cannot re-task the model.
    """

    provider: str
    model: str
    max_tokens: int
    temperature: float | None
    timeout_seconds: float
    system_prompt: str


_EXTRACTION_PROMPT = """\
You extract a structured project model from a software project description.

Identify the actors, entities and their attributes, the relationships between \
entities, the use cases, the interaction flows, the lifecycle states, the \
components, the deployment nodes, and the stated requirements.

Rules:
- Use only what the description supports. Do not invent entities to look thorough.
- If the description is too thin to support at least three entities and two \
relationships, return what is genuinely there rather than padding it.
- Ids must be lowercase, hyphen-separated, derived from the name.
- Reuse the exact same name for the same concept everywhere it appears.
"""

_FLOW_ORDERING_PROMPT = """\
You order the steps of an interaction flow between the given participants.

Produce the sequence of messages, each with a sender, a receiver, the message \
being sent, and its position in the order. Use only the participants supplied.
"""

_SRS_PROSE_PROMPT = """\
You write the prose sections of a software requirements specification from a \
structured project model.

Write plainly and specifically. Do not restate the model as a list, and do not \
add requirements that are not in the model.
"""


TASKS: dict[str, TaskConfig] = {
    # The one call the whole product depends on. Temperature is pinned to zero:
    # FR-9 wants identical input to give identical output, and sampling works
    # directly against that.
    "cpm_extraction": TaskConfig(
        provider=DEFAULT_PROVIDER,
        model=DEFAULT_MODEL,
        max_tokens=8192,
        temperature=0.0,
        timeout_seconds=180.0,
        system_prompt=_EXTRACTION_PROMPT,
    ),
    # FR-9 permits the LLM only where genuine interpretation is required.
    # Ordering a sequence of messages is one of the few such places.
    "sequence_flow_ordering": TaskConfig(
        provider=DEFAULT_PROVIDER,
        model=DEFAULT_MODEL,
        max_tokens=2048,
        temperature=0.0,
        timeout_seconds=90.0,
        system_prompt=_FLOW_ORDERING_PROMPT,
    ),
    "srs_prose": TaskConfig(
        provider=DEFAULT_PROVIDER,
        model=DEFAULT_MODEL,
        max_tokens=4096,
        temperature=0.2,
        timeout_seconds=120.0,
        system_prompt=_SRS_PROSE_PROMPT,
    ),
}


def get_task(name: str) -> TaskConfig:
    """Configuration for one task, or a diagnostic listing the known ones."""
    try:
        return TASKS[name]
    except KeyError:
        raise UnknownTaskError(name, list(TASKS)) from None
