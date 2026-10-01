"""Worktree launcher: force-import astrbot from THIS worktree.

The .venv in a git worktree is cloned from the main checkout and its internal
paths still resolve there, so plain ``python main.py`` would silently run the
main tree's code. This wrapper pins sys.path to this directory first, then
runs the real main.py.
"""

import os
import runpy
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import astrbot  # noqa: E402

astrbot_root = os.path.dirname(os.path.abspath(astrbot.__file__))
expected = os.path.join(ROOT, "astrbot")
assert os.path.samefile(astrbot_root, expected), (
    f"astrbot resolved outside worktree: {astrbot.__file__}"
)
print(f"[worktree] astrbot root = {astrbot_root}")

runpy.run_path(os.path.join(ROOT, "main.py"), run_name="__main__")
