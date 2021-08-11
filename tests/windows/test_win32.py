"Unit tests for shellous module (Windows)."

import sys

import pytest
from shellous import context

unix_only = pytest.mark.skipif(
    sys.platform != "win32", reason="Supported on Windows only"
)

pytestmark = [pytest.mark.asyncio, unix_only]


@pytest.fixture
def sh():
    return context()


@pytest.fixture
def echo(sh):
    return sh("cmd", "/c", "echo")


async def test_python(sh):
    "Test running the python executable."
    result = await sh(sys.executable, "-c", "print('test1')")
    assert result == "test1\r\n"


async def test_echo(sh):
    "Test running the echo command."
    result = await echo("foo")
    assert result == "foo\r\n"
