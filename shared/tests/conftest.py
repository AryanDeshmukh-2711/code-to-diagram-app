import copy
from typing import Any

import pytest

from cpm.fixtures import library_management_system_payload


@pytest.fixture
def payload() -> dict[str, Any]:
    """A deep copy of the Library Management System fixture.

    Deep-copied so a test can mutate it into an invalid state without leaking
    that mutation into the next test.
    """
    return copy.deepcopy(library_management_system_payload())
