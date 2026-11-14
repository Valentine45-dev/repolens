"""Running a helper program with a time limit that really ends it.

`subprocess.run(..., timeout=...)` kills only the process it started. A grandchild that holds the
output pipe keeps `communicate()` waiting (on Windows the call does not return until every holder
has exited) and can go on running after the step has "timed out". Here the child gets its own
process group (POSIX) and on a timeout the whole tree is killed: `killpg` on POSIX,
`taskkill /T /F` on Windows.
"""

import os
import signal
import subprocess
from pathlib import Path

# After the kill, how long to wait for the pipes to close before giving up on the output.
DRAIN_S = 10


def _kill_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        taskkill = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "taskkill.exe"
        try:
            subprocess.run([str(taskkill), "/T", "/F", "/PID", str(proc.pid)],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=DRAIN_S, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)  # the child leads its own group (start_new_session)
        except (ProcessLookupError, PermissionError):
            pass
    proc.kill()  # no-op if it is already gone


def run_bounded(cmd: list[str], *, cwd: Path, env: dict[str, str],
                timeout: float) -> subprocess.CompletedProcess:
    """Run `cmd` with stdin closed and stdout/stderr captured as UTF-8 text. On timeout the whole
    process tree is killed and `subprocess.TimeoutExpired` is raised."""
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
        start_new_session=os.name != "nt",
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=DRAIN_S)
        except subprocess.TimeoutExpired:
            pass  # something we could not kill still holds a pipe; its output is not needed
        raise
    except BaseException:
        _kill_tree(proc)
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)
