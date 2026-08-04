"""Every enqueue_job call names its queue explicitly.

Found live, twice already this project (P-M6-1's extraction endpoint, then
P-M6-2's chat endpoint), and a third time -- pre-existing, in runs.py's own
regenerate() -- while proving P-M6-9's regeneration flow end to end: a job
enqueued with no `_queue_name` lands on arq's own default queue, which
nothing in this stack consumes (worker listens on arq:default, worker-priority
on arq:priority, never on arq:queue). The job then sits at "pending" forever
with no error, no log line, nothing to notice by until someone happens to
wait on it. Pinned here so the next new job-queueing route cannot reintroduce
the same silent failure.
"""

import ast
from pathlib import Path

ROUTERS = Path(__file__).resolve().parents[2] / "api" / "app" / "routers"


def test_every_enqueue_job_call_names_its_queue() -> None:
    missing: list[str] = []
    for path in ROUTERS.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "enqueue_job"
            ):
                continue
            if not any(keyword.arg == "_queue_name" for keyword in node.keywords):
                job_name = ast.unparse(node.args[0]) if node.args else "<unknown>"
                missing.append(f"{path.name}: enqueue_job({job_name}, ...) has no _queue_name")

    assert not missing, "\n".join(missing)
