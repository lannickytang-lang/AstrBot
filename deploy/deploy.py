#!/usr/bin/env python3
"""One-command deployment for yuansheng-astrbot.

Orchestrates: push (+tag) -> local dashboard build -> upload dist ->
run server.sh on the VPS via SSH. The server script does the actual
git fetch/reset, docker build, backup, swap and health check.

Usage:
  python deploy/deploy.py                    # full deploy
  python deploy/deploy.py --frontend-only    # dist swap only (no rebuild)
  python deploy/deploy.py --backend-only     # code + rebuild, no frontend
  python deploy/deploy.py --tag <ts>         # (re)deploy a historical deploy/<ts> tag
  python deploy/deploy.py --list             # show deployment history
  python deploy/deploy.py --rollback <ts> [--with-db]
  python deploy/deploy.py --dry-run          # print steps only
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
DIST_OUT = REPO_ROOT / "deploy" / "dist-build.tar.gz"
SERVER_ALIAS = "tudodo-server"
SERVER_APP_DIR = "/root/apps/yuansheng-astrbot"
SERVER_SCRIPT = f"{SERVER_APP_DIR}/server.sh"
BRANCH = "dev"


def run(
    cmd: list[str], *, title: str, cwd: Path | None = None, check: bool = True
) -> str:
    # On Windows, npm-family entrypoints are .cmd shims that CreateProcess
    # cannot launch directly; resolve through PATH first.
    resolved = shutil.which(cmd[0])
    if resolved:
        cmd = [resolved, *cmd[1:]]
    print(f"\n=== {title}\n$ {' '.join(cmd)}")
    started = time.time()
    result = subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (result.stdout or "") + (result.stderr or "")
    print(output.strip()[-3000:] if output.strip() else "(no output)")
    if check and result.returncode != 0:
        raise SystemExit(
            f"[deploy][ERROR] {title} failed (exit {result.returncode}), see output above"
        )
    print(
        f"--- {title}: {'OK' if result.returncode == 0 else 'FAILED'} ({time.time() - started:.0f}s)"
    )
    return output


def sh(server_cmd: str, title: str, check: bool = True) -> str:
    return run(["ssh", SERVER_ALIAS, server_cmd], title=title, check=check)


def git_out(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def do_push_and_tag(ts: str, dry: bool) -> str:
    if git_out("status", "--porcelain"):
        raise SystemExit(
            "[deploy][ERROR] working tree not clean; commit or stash first"
        )
    commit = git_out("log", "--oneline", "-1")
    print(f"deploying commit: {commit}")
    tag = f"deploy/{ts}"
    if dry:
        print(
            f"(dry) git tag -f {tag}; git push origin {BRANCH}; git push -f origin {tag}"
        )
        return tag
    run(["git", "tag", "-f", tag], title=f"git tag {tag}")
    run(["git", "push", "origin", BRANCH], title="git push origin dev")
    run(["git", "push", "-f", "origin", tag], title=f"git push {tag}")
    return tag


def do_frontend_build(dry: bool) -> Path:
    if dry:
        print("(dry) pnpm build -> dist/version marker -> tar deploy/dist-build.tar.gz")
        return DIST_OUT
    run(["pnpm", "build"], title="pnpm build (dashboard)", cwd=DASHBOARD_DIR)
    index = DASHBOARD_DIR / "dist" / "index.html"
    if not index.exists():
        raise SystemExit("[deploy][ERROR] dist/index.html missing after build")
    # version marker must equal core version or startup pulls upstream dist
    core_version = (REPO_ROOT / "astrbot" / "__init__.py").read_text(encoding="utf-8")
    core_version = core_version.split("__version__ = ")[1].strip().strip('"').strip("'")
    version_file = DASHBOARD_DIR / "dist" / "assets" / "version"
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text(f"v{core_version}", encoding="utf-8")
    print(f"dist version marker: v{core_version}")
    if dry:
        return DIST_OUT
    run(
        ["tar", "czf", str(DIST_OUT), "."],
        title="pack dist",
        cwd=DASHBOARD_DIR / "dist",
    )
    print(f"dist package: {DIST_OUT} ({DIST_OUT.stat().st_size / 1e6:.1f} MB)")
    return DIST_OUT


def do_upload(pkg: Path, dry: bool) -> None:
    if dry:
        print(f"(dry) scp {pkg} -> {SERVER_ALIAS}:/tmp/")
        return
    run(
        ["scp", str(pkg), f"{SERVER_ALIAS}:/tmp/dist-upload.tar.gz"],
        title="scp dist to server",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="yuansheng-astrbot deployment")
    parser.add_argument("--frontend-only", action="store_true")
    parser.add_argument("--backend-only", action="store_true")
    parser.add_argument("--tag", metavar="TS", help="deploy historical deploy/<ts> tag")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--rollback", metavar="TS")
    parser.add_argument(
        "--with-db", action="store_true", help="rollback db too (dangerous)"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M")

    if args.list:
        sh(f"cd {SERVER_APP_DIR} && ./server.sh list", title="server list")
        return

    if args.rollback:
        confirm = "YES" if args.with_db else ""
        extra = f" --with-db {confirm}" if args.with_db else ""
        print(f"rollback to deploy/{args.rollback}{extra}")
        if not args.dry_run and args.with_db:
            if (
                input(
                    "this OVERWRITES customer data snapshot; type ROLLBACK to confirm: "
                )
                != "ROLLBACK"
            ):
                raise SystemExit("aborted")
        sh(
            f"cd {SERVER_APP_DIR} && ./server.sh rollback {args.rollback}{extra}",
            title="server rollback",
        )
        return

    print(
        f"== deploy ts={ts} mode={'frontend' if args.frontend_only else 'backend' if args.backend_only else 'full'} =="
    )
    if args.dry_run:
        print("(dry-run: no push, no build, no server change)")

    tag = None
    pkg: Path | None = None

    if not args.frontend_only:
        tag = do_push_and_tag(ts, args.dry_run)
    if not args.backend_only:
        pkg = do_frontend_build(args.dry_run)
        do_upload(pkg, args.dry_run)

    # keep server script fresh on every run
    run(
        [
            "scp",
            str(REPO_ROOT / "deploy" / "server.sh"),
            f"{SERVER_ALIAS}:{SERVER_SCRIPT}",
        ],
        title="sync server.sh",
    )
    if args.dry_run:
        print("(dry) ssh server.sh deploy ...")
        return

    if args.frontend_only:
        assert pkg is not None
        sh(
            f"cd {SERVER_APP_DIR} && ./server.sh frontend /tmp/dist-upload.tar.gz",
            title="server frontend",
        )
    else:
        ref_arg = f"--tag deploy/{args.tag}" if args.tag else f"--tag {tag}"
        dist_arg = "none" if args.backend_only else "/tmp/dist-upload.tar.gz"
        sh(
            f"cd {SERVER_APP_DIR} && ./server.sh deploy {dist_arg} {ref_arg}",
            title="server deploy",
        )

    print(f"\n✅ done. ts={ts}  (rollback: python deploy/deploy.py --rollback {ts})")


if __name__ == "__main__":
    main()
