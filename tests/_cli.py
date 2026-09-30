"""Run `python -m engine ...` for the tests.

By default the CLI runs in-process (same entry point, same exit codes, same output), which skips a fresh Python
start-up and SRD load per command and makes the suite about ten times faster. Set DND_TEST_SUBPROCESS=1 to run
every command in a real subprocess instead, exactly as a player's shell would.

Each test class keeps its campaigns in its own temp folder. `point_at` aims the engine's path settings at that
folder. The modules are never reloaded: a reload would mint a second copy of classes like RuleError, and
`except RuleError` would stop matching.
"""
import contextlib
import io
import os
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def point_at(env):
    """Aim the engine at this test class's campaign folder and key store (what DND_* would set at start-up)."""
    os.environ.update({k: v for k, v in env.items() if k.startswith("DND_")})
    import engine.store as store
    import engine.cli as cli
    campaigns = Path(env.get("DND_CAMPAIGNS", ROOT / "campaigns"))
    store.CAMPAIGNS = cli.CAMPAIGNS = campaigns
    store.ACTIVE_FILE = cli.ACTIVE_FILE = campaigns / "ACTIVE"
    store.KEY_DIR = Path(env.get("DND_ENGINE_HOME", Path.home() / ".dnd-engine")) / "keys"


def game(env):
    """A fresh Game on the active campaign of this test class."""
    point_at(env)
    import engine.core as core
    import engine.store as store
    return core.Game(store.active_dir())


def run(env, *args):
    if os.environ.get("DND_TEST_SUBPROCESS"):
        p = subprocess.run([sys.executable, "-m", "engine", *args], cwd=ROOT, env=env, capture_output=True,
                           text=True, encoding="utf-8")
        return p.returncode, p.stdout + p.stderr
    point_at(env)
    import engine.cli as cli
    cwd = os.getcwd()
    os.chdir(ROOT)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                code = cli.main(list(args))
                code = 0 if code is None else code
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
            except Exception:  # an engine crash, as the subprocess would report it
                traceback.print_exc()
                code = 1
    finally:
        os.chdir(cwd)
    return code, buf.getvalue()
