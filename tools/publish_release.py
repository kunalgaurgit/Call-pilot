#!/usr/bin/env python3
"""Publish Call Pilot release to GitHub."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

DEFAULT_TOOLS_DIR = Path(r"D:\Victoris\.tools\sdk\build-tools\35.0.0")


def resolve_tool_paths() -> tuple[Path, Path]:
    tools_dir = DEFAULT_TOOLS_DIR
    if not tools_dir.exists():
        repo_relative = Path(__file__).resolve().parent.parent / ".tools" / "sdk" / "build-tools" / "35.0.0"
        if repo_relative.exists():
            tools_dir = repo_relative

    aapt2_path = tools_dir / "aapt2.exe"
    if not aapt2_path.exists() and (tools_dir / "aapt2").exists():
        aapt2_path = tools_dir / "aapt2"

    apksigner_path = tools_dir / "apksigner.bat"
    if not apksigner_path.exists() and (tools_dir / "apksigner").exists():
        apksigner_path = tools_dir / "apksigner"

    return aapt2_path, apksigner_path


def verify_apk_signature(apksigner_path: Path, apk_path: Path) -> None:
    if not apksigner_path.exists():
        print(f"Error: apksigner not found at '{apksigner_path}'", file=sys.stderr)
        sys.exit(1)

    cmd = [str(apksigner_path), "verify", str(apk_path)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    except Exception as e:
        print(f"Error executing apksigner: {e}", file=sys.stderr)
        sys.exit(1)

    if res.returncode != 0:
        err_msg = (res.stderr or res.stdout or "").strip()
        print(f"Error: APK signature verification failed (exit code {res.returncode}):\n{err_msg}", file=sys.stderr)
        sys.exit(1)


def read_apk_version_info(aapt2_path: Path, apk_path: Path) -> tuple[int | str, str]:
    if not aapt2_path.exists():
        print(f"Error: aapt2 not found at '{aapt2_path}'", file=sys.stderr)
        sys.exit(1)

    try:
        res = subprocess.run(
            [str(aapt2_path), "dump", "badging", str(apk_path)],
            capture_output=True,
            text=True,
            shell=False,
        )
    except Exception as e:
        print(f"Error executing aapt2: {e}", file=sys.stderr)
        sys.exit(1)

    if res.returncode != 0:
        err_msg = (res.stderr or res.stdout or "").strip()
        print(f"Error: aapt2 dump badging failed (exit code {res.returncode}):\n{err_msg}", file=sys.stderr)
        sys.exit(1)

    out = res.stdout
    vc_match = re.search(r"versionCode=['\"]([^'\"]+)['\"]", out)
    vn_match = re.search(r"versionName=['\"]([^'\"]+)['\"]", out)

    if not vc_match or not vn_match:
        print("Error: Could not extract versionCode or versionName from aapt2 badging output.", file=sys.stderr)
        sys.exit(1)

    vc_raw = vc_match.group(1)
    version_name = vn_match.group(1)
    version_code = int(vc_raw) if vc_raw.isdigit() else vc_raw
    return version_code, version_name


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_github_token() -> str:
    try:
        res = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            check=True,
            shell=False,
        )
    except subprocess.CalledProcessError:
        print("Error: Failed to obtain GitHub credentials from git credential helper.", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: 'git' command not found in PATH.", file=sys.stderr)
        sys.exit(1)

    token = None
    for line in res.stdout.splitlines():
        if line.startswith("password="):
            token = line[len("password="):].strip()
            break

    if not token:
        print("Error: GitHub token not found in git credential output (missing password=).", file=sys.stderr)
        sys.exit(1)

    return token


def make_github_request(url: str, data: bytes, content_type: str, token: str) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "CallPilot-publisher",
        "Content-Type": content_type,
        "Content-Length": str(len(data)),
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    # Unredirected: urllib copies normal headers onto redirects, which would hand the token to another host.
    req.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            resp_bytes = resp.read()
            if resp_bytes:
                return json.loads(resp_bytes.decode("utf-8"))
            return {}
    except urllib.error.HTTPError as err:
        err_msg = ""
        try:
            err_raw = err.read().decode("utf-8", errors="replace")
            err_json = json.loads(err_raw)
            err_msg = err_json.get("message", err_raw)
            if "errors" in err_json:
                err_msg += f" (errors: {err_json['errors']})"
        except Exception:
            err_msg = str(err.reason)

        if token:
            err_msg = err_msg.replace(token, "[REDACTED]")

        if err.code == 422:
            print(f"HTTP Error 422: Release or tag already exists or validation failed: {err_msg}", file=sys.stderr)
        else:
            print(f"HTTP Error {err.code}: {err_msg}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as err:
        reason = str(err.reason)
        if token:
            reason = reason.replace(token, "[REDACTED]")
        print(f"Network error: {reason}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish Call Pilot release to GitHub.")
    parser.add_argument("--apk", required=True, type=Path, help="Path to APK file")
    parser.add_argument("--notes", required=True, type=str, help="Release notes text")
    parser.add_argument(
        "--repo",
        default="kunalgaurgit/Call-pilot",
        help="GitHub repository (owner/repo), default: kunalgaurgit/Call-pilot",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform local checks and print update.json without network operations",
    )

    args = parser.parse_args()

    apk_path = args.apk.resolve()
    if not apk_path.is_file():
        print(f"Error: APK file not found at '{apk_path}'", file=sys.stderr)
        sys.exit(1)

    aapt2_path, apksigner_path = resolve_tool_paths()

    # Verify signature before proceeding
    verify_apk_signature(apksigner_path, apk_path)

    # 1) read versionCode/versionName from APK using aapt2
    version_code, version_name = read_apk_version_info(aapt2_path, apk_path)

    # 2) sha256 of the APK
    sha256_hash = compute_sha256(apk_path)

    # 3) build update.json
    update_data = {
        "versionCode": version_code,
        "versionName": version_name,
        "sha256": sha256_hash,
        "notes": args.notes,
    }

    if args.dry_run:
        print(json.dumps(update_data, indent=2))
        return

    # 4) get GitHub token without printing it
    token = get_github_token()

    # 5) POST release
    release_payload = {
        "tag_name": f"v{version_name}",
        "name": f"Call Pilot {version_name}",
        "body": args.notes,
        "draft": False,
        "prerelease": False,
    }
    release_url = f"https://api.github.com/repos/{args.repo}/releases"
    release_bytes = json.dumps(release_payload).encode("utf-8")
    release_res = make_github_request(release_url, release_bytes, "application/json", token)

    upload_url_template = release_res.get("upload_url", "")
    if not upload_url_template:
        print("Error: 'upload_url' not found in GitHub release response.", file=sys.stderr)
        sys.exit(1)

    upload_base = upload_url_template.split("{")[0]

    # 6) upload update.json then the APK
    update_bytes = json.dumps(update_data, indent=2).encode("utf-8")
    upload_json_url = f"{upload_base}?name=update.json"
    make_github_request(upload_json_url, update_bytes, "application/json", token)

    apk_asset_name = f"CallPilot-{version_name}.apk"
    upload_apk_url = f"{upload_base}?name={apk_asset_name}"
    with open(apk_path, "rb") as f:
        apk_bytes = f.read()
    make_github_request(upload_apk_url, apk_bytes, "application/vnd.android.package-archive", token)

    # 7) print release URL, versionCode, sha256
    html_url = release_res.get("html_url", "")
    print(f"Release URL: {html_url}")
    print(f"versionCode: {version_code}")
    print(f"sha256: {sha256_hash}")


if __name__ == "__main__":
    main()
