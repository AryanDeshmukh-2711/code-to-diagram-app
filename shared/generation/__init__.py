"""Generation runs.

One entry point, `execute_generation_run`, which always validates.
"""

from generation.run import GenerationRunResult, execute_generation_run

__all__ = ["GenerationRunResult", "execute_generation_run"]
