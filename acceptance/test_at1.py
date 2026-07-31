"""AT-1 as a pytest case, so CI can run the same acceptance test.

The assertion message is the report, not a traceback: a failure here has to
say which promise broke, and pytest's own output would say which line of
Python raised.

Requires a live stack (database, queue, worker, diagram engines). `make at1`
starts one; this is for a runner that already has it.
"""

import asyncio

from at1 import run_at1


def test_at1() -> None:
    report = asyncio.run(run_at1())
    assert report.passed, "\n" + report.render()
