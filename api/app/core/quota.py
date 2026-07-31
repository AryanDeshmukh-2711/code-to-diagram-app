"""Turning a quota refusal into an HTTP response, in one place.

402 Payment Required, with the refusal as structured JSON rather than a
sentence buried in `detail`. The client needs the number the user hit, what
they used, and what the next plan gives, because a message the UI cannot
rebuild is a message the UI will rewrite badly.

Every quota check happens here-side of the boundary. There is no equivalent in
the browser, and there is deliberately no header or query parameter that skips
one: enforcement that can be asked not to run is enforcement against people
who do not know to ask.
"""

from billing.quota import QuotaExceeded
from fastapi import HTTPException, status


def as_http(exc: QuotaExceeded) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail=exc.refusal.as_dict(),
    )
