"""CHAT-1 as a pytest case, so CI can run the same acceptance test.

The assertion message is the report, not a traceback — same reasoning as
test_at1.py: a failure here has to say which promise broke, and pytest's own
output would say which line of Python raised.

Requires a live stack (database, queue, worker, diagram engines) and a
reachable model. `make chat1` starts one; this is for a runner that already
has it.
"""

import asyncio

from chat1 import run_chat1


def test_chat1() -> None:
    report = asyncio.run(run_chat1())
    assert report.passed, "\n" + report.render()
