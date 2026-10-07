#!/usr/bin/env python3
"""Build release/CallPilot-share.zip: the server, web UI and newest APK, ready for a Windows PC.

Only git-tracked files go in, so the database and logs never ship.
--with-env also packs your .env (your Gemini key) so the receiver skips the key prompt.
"""
import argparse
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = ("android/", "tools/", "tests/", ".githooks/", ".gitattributes", ".gitignore")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--with-env", action="store_true", help="include .env (shares your API key)")
    ap.add_argument("--out", type=Path, default=ROOT / "release" / "CallPilot-share.zip")
    args = ap.parse_args()

    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    files = [f for f in tracked.splitlines() if not f.startswith(SKIP) and (ROOT / f).is_file()]
    if args.with_env:
        if not (ROOT / ".env").is_file():
            raise SystemExit("No .env to include - run run.bat once first.")
        files.append(".env")
    apk = max((ROOT / "release").glob("CallPilot-*.apk"),
              key=lambda p: tuple(int(x) for x in p.stem.split("-")[1].split(".")))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(ROOT / f, f"CallPilot/{f}")
        z.write(apk, f"CallPilot/release/{apk.name}")

    names = zipfile.ZipFile(args.out).namelist()
    assert not any(n.endswith((".db", ".jsonl")) for n in names), "data file in zip"
    assert args.with_env == ("CallPilot/.env" in names)
    print(f"{args.out}  ({args.out.stat().st_size / 1e6:.1f} MB, {len(names)} files, APK {apk.name}"
          + (", includes .env with your API key)" if args.with_env else ")"))


if __name__ == "__main__":
    main()
