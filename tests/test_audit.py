import os
import shutil
import sys

import pytest
import shellous
from shellous import AUDIT_EVENT_SUBPROCESS_SPAWN

pytestmark = pytest.mark.asyncio

_HOOK = None
_IGNORE = {"object.__getattr__", "sys._getframe", "code.__new__", "builtins.id"}


def _audit_hook(event, args):
    if _HOOK and event not in _IGNORE:
        _HOOK(event, args)


sys.addaudithook(_audit_hook)


def _is_uvloop():
    "Return true if we're running under uvloop."
    return os.environ.get("SHELLOUS_LOOP_TYPE") == "uvloop"


def _has_posix_spawn():
    return not _is_uvloop() and sys.platform in ("darwin", "linux")


async def test_audit():
    "Test PEP 578 audit hooks."

    global _HOOK
    events = []

    def _hook(*info):
        events.append(repr(info))

    try:
        _HOOK = _hook

        sh = shellous.context()
        result = await sh(sys.executable, "-c", "print('hello')")

    finally:
        _HOOK = None

    assert result.rstrip() == "hello"

    for event in events:
        # Work-around Windows UnicodeEncodeError: '_winapi.CreateNamedPipe' evt.
        print(event.encode("ascii", "backslashreplace").decode("ascii"))

    # Check for my audit event.
    assert any(
        event.startswith(f"('{AUDIT_EVENT_SUBPROCESS_SPAWN}',") for event in events
    )

    if not _is_uvloop():
        # uvloop doesn't implement audit hooks.
        assert any(event.startswith("('subprocess.Popen',") for event in events)

    if _has_posix_spawn():
        assert any(event.startswith("('os.posix_spawn',") for event in events)


@pytest.mark.skipif(not _has_posix_spawn(), reason="posix_spawn")
async def test_audit_posix_spawn():
    "Test PEP 578 audit hooks."

    global _HOOK
    events = []

    def _hook(*info):
        events.append(repr(info))

    try:
        _HOOK = _hook

        # This command does not include a directory path, so it is resolved
        # through PATH.
        sh = shellous.context()
        result = await sh("ls", "README.md")

    finally:
        _HOOK = None

    assert result.rstrip() == "README.md"

    for event in events:
        # Work-around Windows UnicodeEncodeError: '_winapi.CreateNamedPipe' evt.
        print(event.encode("ascii", "backslashreplace").decode("ascii"))

    # Check for my audit event.
    assert any(
        event.startswith(f"('{AUDIT_EVENT_SUBPROCESS_SPAWN}',") for event in events
    )

    # Check for subprocess.Popen and os.posix_spawn.
    assert any(event.startswith("('subprocess.Popen',") for event in events)
    assert any(event.startswith("('os.posix_spawn',") for event in events)


@pytest.mark.xfail(_is_uvloop(), reason="uvloop")
async def test_audit_block_popen():
    "Test PEP 578 audit hooks."

    global _HOOK

    def _hook(event, args):
        if event == "subprocess.Popen":
            raise RuntimeError("Popen blocked")

    try:
        _HOOK = _hook

        sh = shellous.context()
        with pytest.raises(RuntimeError, match="Popen blocked"):
            await sh(sys.executable, "-c", "print('hello')")

    finally:
        _HOOK = None


async def test_audit_block_subprocess_spawn():
    "Test PEP 578 audit hooks."

    global _HOOK

    def _hook(event, _args):
        if event == AUDIT_EVENT_SUBPROCESS_SPAWN:
            raise RuntimeError("subprocess_spawn blocked")

    try:
        _HOOK = _hook

        sh = shellous.context()
        cmd = sh(sys.executable, "-c", "print('hello')")
        with pytest.raises(RuntimeError, match="subprocess_spawn"):

            if sys.platform == "win32":
                # Process substitution doesn't work on Windows.
                await cmd
            else:
                # Test process substitution cleanup also.
                await cmd(cmd())

    finally:
        _HOOK = None


async def test_audit_block_pipe_specific_cmd():
    "Test PEP 578 audit hooks to block a specific command (in a pipe)."

    global _HOOK
    grep_path = shutil.which("grep")

    def _hook(event, args):
        if event == AUDIT_EVENT_SUBPROCESS_SPAWN and args[0] == grep_path:
            raise RuntimeError("grep blocked")

    callbacks = []

    def _callback(phase, info):
        runner = info["runner"]
        failure = info.get("failure")
        exit_code = runner.returncode
        if exit_code is not None:
            exit_code = "Zero" if exit_code == 0 else "NonZero"
        callbacks.append(f"{phase}:{runner.name}:{exit_code}:{failure}")

    try:
        _HOOK = _hook

        sh = shellous.context().set(audit_callback=_callback)
        hello = sh(sys.executable, "-c", "print('hello')").set(alt_name="hello")
        cmd = hello | sh("grep")
        with pytest.raises(RuntimeError, match="grep blocked"):
            await cmd

    finally:
        _HOOK = None

    assert callbacks == [
        "start:hello:None:None",
        "start:grep:None:None",
        "stop:grep:None:RuntimeError",
        "signal:hello:None:None",
        "stop:hello:NonZero:CancelledError",
    ]
