import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from opentearsheet import registry  # noqa: E402
from opentearsheet.cache import HttpCache  # noqa: E402
from opentearsheet.models import Entity  # noqa: E402
from opentearsheet.sec_client import SecClient  # noqa: E402
from tests.fixture_transport import DEMO_AS_OF, FixtureTransport  # noqa: E402

UA = "OpenTearsheet Tests tests@opentearsheet.invalid"


@pytest.fixture(scope="session", autouse=True)
def _builtin_connectors():
    registry.load_builtin()


@pytest.fixture
def transport():
    return FixtureTransport()


@pytest.fixture
def client(transport):
    return SecClient(UA, HttpCache(":memory:"), max_rps=10, transport=transport, sleep=lambda _: None)


@pytest.fixture
def options():
    return {"as_of": DEMO_AS_OF, "max_form4": 40, "form4_lookback_days": 365}


@pytest.fixture
def company():
    return Entity(kind="company", name="Example Robotics Inc.", cik="0001999999", ticker="EXMP")


@pytest.fixture
def firm():
    return Entity(kind="firm", name="Sample Capital Management LLC", cik="0001888888", crd="160001")
