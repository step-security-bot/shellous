"Unit tests for the Prompt class."

import asyncio
import os
import platform
import sys

import pytest

from shellous import cooked, sh
from shellous.prompt import Prompt

# True if we are running on PyPy.
_IS_PYPY = platform.python_implementation() == "PyPy"

# True if we're running on alpine linux.
_IS_ALPINE = os.path.exists("/etc/alpine-release")

# True if we're running on FreeBSD.
_IS_FREEBSD = sys.platform.startswith("freebsd")

# True if we're running on MacOS.
_IS_MACOS = sys.platform == "darwin"

# True if we're in Github Actions.
_IS_GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS") is not None

# The interactive prompt on PyPY3 is ">>>> ".
if _IS_PYPY:
    _PS1 = ">>>> "
else:
    _PS1 = ">>> "

_NO_ECHO = cooked(echo=False)

_requires_unix = pytest.mark.skipif(sys.platform == "win32", reason="requires unix")

_requires_pty = pytest.mark.skipif(
    os.environ.get("SHELLOUS_LOOP_TYPE") == "uvloop" or sys.platform == "win32",
    reason="requires pty",
)


@_requires_pty
async def test_prompt_python_pty():
    "Test the prompt class with the Python REPL (PTY)."
    cmd = sh(sys.executable).stdin(sh.CAPTURE).stdout(sh.CAPTURE).stderr(sh.STDOUT)

    async with cmd.set(pty=_NO_ECHO) as run:
        repl = Prompt(run, _PS1, default_timeout=3.0)

        greeting = await repl.send()
        assert "Python" in greeting

        result = await repl.send("print('abc')")
        if _IS_MACOS and _IS_GITHUB_ACTIONS:
            assert result == "print('abc')\nabc"
        else:
            assert result == "abc"

        await repl.send("exit()")

    assert run.result().exit_code == 0


async def test_prompt_python_interactive():
    "Test the prompt class with the Python REPL (non-PTY using -i)."
    cmd = (
        sh(sys.executable, "-i").stdin(sh.CAPTURE).stdout(sh.CAPTURE).stderr(sh.STDOUT)
    )

    async with cmd as run:
        repl = Prompt(run, _PS1, default_timeout=3.0)

        greeting = await repl.send()
        assert "Python" in greeting

        result = await repl.send("print('abc')")
        assert result == "abc"

        await repl.send("exit()")

    assert run.result().exit_code == 0


@_requires_pty
async def test_prompt_python_interactive_ps1():
    "Test the Python REPL but change the prompt to something unique."
    alt_ps1 = "????"
    cmd = (
        sh(sys.executable, "-i").stdin(sh.CAPTURE).stdout(sh.CAPTURE).stderr(sh.STDOUT)
    )

    async with cmd as run:
        repl = Prompt(run, alt_ps1)

        greeting = await repl.send(f"import sys; sys.ps1='{alt_ps1}'")
        assert _PS1 in greeting

        result = await repl.send("print('def')")
        assert result == "def"

        await repl.send("exit()")

    assert run.result().exit_code == 0


@_requires_pty
async def test_prompt_python_timeout():
    "Test the prompt class with the Python REPL."
    cmd = (
        sh(sys.executable, "-i").stdin(sh.CAPTURE).stdout(sh.CAPTURE).stderr(sh.STDOUT)
    )

    async with cmd as run:
        repl = Prompt(run, _PS1)

        greeting = await repl.send()
        assert "Python" in greeting

        with pytest.raises(asyncio.TimeoutError):
            await repl.send("import time; time.sleep(1)", timeout=0.1)

        await repl.send("exit()")

    assert run.result().exit_code == 0


@_requires_pty
async def test_prompt_python_missing_newline():
    "Test the prompt class with the Python REPL."
    cmd = (
        sh(sys.executable, "-i").stdin(sh.CAPTURE).stdout(sh.CAPTURE).stderr(sh.STDOUT)
    )

    async with cmd as run:
        repl = Prompt(run, _PS1)

        greeting = await repl.send()
        assert "Python" in greeting

        result = await repl.send("print(3, end='.')")
        assert result == "3."

        await repl.send("exit()")

    assert run.result().exit_code == 0


@_requires_pty
async def test_prompt_unix_shell():
    "Test the prompt class with a shell (PTY no echo)."
    cmd = (
        sh("sh")
        .stdin(sh.CAPTURE)
        .stdout(sh.CAPTURE)
        .stderr(sh.STDOUT)
        .set(pty=_NO_ECHO, inherit_env=False)
    )

    async with cmd.env(PS1="$", TERM="dumb") as run:
        repl = Prompt(run, "$")

        greeting = await repl.send()
        if _IS_FREEBSD:
            # FIXME: FreeBSD is complaining that it can't access tty?
            assert "job control" in greeting
        else:
            assert greeting == ""

        result = await repl.send("echo 123")
        if _IS_FREEBSD:
            # FIXME: I don't understand why FreeBSD is still echoing?
            assert result == "echo 123\n123"
        else:
            assert result == "123"

        await repl.send("exit")

    assert run.result().exit_code == 0


@_requires_pty
async def test_prompt_unix_shell_echo():
    "Test the prompt class with a shell (PTY default cooked mode)."
    cmd = (
        sh("sh")
        .stdin(sh.CAPTURE)
        .stdout(sh.CAPTURE)
        .stderr(sh.STDOUT)
        .set(pty=True, inherit_env=False)
    )

    async with cmd.env(PS1="$", TERM="dumb") as run:
        repl = Prompt(run, "$")

        greeting = await repl.send()
        if _IS_FREEBSD:
            # FIXME: FreeBSD is complaining that it can't access tty?
            assert "job control" in greeting
        else:
            assert greeting == ""

        result = await repl.send("echo 123")
        if _IS_ALPINE:
            # Alpine is including terminal escape chars.
            assert result == "\x1b[6necho 123\n123"
        else:
            assert result == "echo 123\n123"

        await repl.send("exit")

    assert run.result().exit_code == 0


@_requires_unix
async def test_prompt_unix_shell_interactive():
    "Test the prompt class with an interactive shell (non-PTY, forced)."
    cmd = (
        sh("sh", "-i")
        .stdin(sh.CAPTURE)
        .stdout(sh.CAPTURE)
        .stderr(sh.STDOUT)
        .set(inherit_env=False)
    )

    async with cmd.env(PS1="$", TERM="dumb") as run:
        repl = Prompt(run, "$")

        greeting = await repl.send()
        assert "job control" in greeting  # expect message about job control

        result = await repl.send("echo 123")

        if _IS_MACOS and not _IS_GITHUB_ACTIONS:
            # On my *own* Mac, the result is 'echo 123\n123'.
            # Result is "123" on MacOS in Github Actions?
            assert result == "echo 123\n123"
        else:
            assert result == "123"

        await repl.send("exit")

    assert run.result().exit_code == 0


async def test_prompt_asyncio_repl():
    "Test the prompt class with the asyncio REPL."

    cmd = (
        sh(sys.executable, "-m", "asyncio")
        .stdin(sh.CAPTURE)
        .stdout(sh.CAPTURE)
        .stderr(sh.STDOUT)
    )

    async with cmd as run:
        repl = Prompt(run, ">>> ")

        greeting = await repl.send()
        assert "asyncio" in greeting

        extra = await repl.send()
        assert "import asyncio" in extra

        result = await repl.send("print('hello')")
        assert result == "hello"

        repl.close()

    assert run.result().exit_code == 0
