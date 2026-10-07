"""Build, install and verify an actual wheel without altering the user's Aelix."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(command: list[str], *, env: dict[str, str] | None = None, cwd: Path = ROOT) -> None:
    print("Running:", " ".join(command), flush=True)
    subprocess.run(command, check=True, env=env, cwd=cwd, timeout=120)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aelix-source", type=Path, required=True)
    args = parser.parse_args()
    host = args.aelix_source.resolve()
    for name in ("aelix-ai", "aelix-agent-core", "aelix-coding-agent"):
        if not (host / "packages" / name / "pyproject.toml").is_file():
            parser.error(f"Missing host package: {name}")
    with tempfile.TemporaryDirectory(prefix="aelix-webtool-verify-") as directory:
        work = Path(directory)
        run(["uv", "build", "--wheel", "--out-dir", str(work / "dist")])
        wheels = list((work / "dist").glob("aelix_webtool-*.whl"))
        assert len(wheels) == 1
        wheel = wheels[0]
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            assert "aelix_webtool/aelix-plugin.toml" in names
            assert any(n.endswith("entry_points.txt") for n in names)
            assert not any(
                n.startswith(("tests/", "docs/", ".env", ".omc/", ".claude/")) for n in names
            )
        venv = work / "venv"
        run(["uv", "venv", str(venv), "--python", sys.executable])
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                *(
                    str(host / "packages" / name)
                    for name in ("aelix-ai", "aelix-agent-core", "aelix-coding-agent")
                ),
                str(wheel),
            ]
        )
        env = os.environ.copy()
        env["AELIX_CODING_AGENT_DIR"] = str(work / "agent")
        env["AELIX_DEFAULT_CATALOG"] = ""
        # This check is model-free and never needs provider credentials.
        for name in (
            "BRAVE_API_KEY",
            "TAVILY_API_KEY",
            "EXA_API_KEY",
            "AELIX_WEB_OFFLINE",
            "AELIX_WEB_SEARXNG_URL",
            "AELIX_WEB_PROVIDER",
        ):
            env.pop(name, None)
        run(
            [
                str(python),
                "-I",
                "-c",
                "from aelix_coding_agent.cli.entry import main_sync; raise SystemExit(main_sync())",
                "extension",
                "verify",
                "aelix-webtool",
            ],
            env=env,
            cwd=work,
        )
        run([str(python), "-I", str(ROOT / "scripts" / "host_smoke.py")], env=env, cwd=work)
        print(
            "PASS: built wheel, installed manifest BOUND, entry-point discovery and real-host dispatch"
        )


if __name__ == "__main__":
    main()
