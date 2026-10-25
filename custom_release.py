#!/usr/bin/env python3
"""Release selection and explicit build preparation. Python standard library only."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

UPSTREAM = "dev4harmony/PiliPlus"
API = "https://api.github.com"
FLUTTER_REPO = "https://gitcode.com/CPF-Flutter/flutter_flutter.git"
WORKSPACE = Path(os.environ.get("GITHUB_WORKSPACE", Path.cwd())).resolve()
KIT = Path(__file__).resolve().parent.parent
SOURCE = WORKSPACE / "source"
STATE = WORKSPACE / "build-state.json"
OUTPUT = WORKSPACE / "output"


def fail(message):
    raise RuntimeError(message)


def run(*args, cwd=None, capture=False):
    result = subprocess.run(args, cwd=cwd, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else None


def api(path, method="GET", data=None, raw=None, content_type=None):
    url = path if path.startswith("https://") else API + path
    if urlparse(url).hostname not in {"api.github.com", "uploads.github.com"}:
        fail("Unexpected GitHub API hostname")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "PiliPlus-custom-release"}
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    payload = raw
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    request = Request(url, data=payload, headers=headers, method=method)
    # Do not blindly retry writes: a failed response can follow a successful write.
    with urlopen(request, timeout=120) as response:
        body = response.read()
    return json.loads(body) if body else None


def pages(path):
    """Read every REST page, including a final empty page when count is a multiple of 100."""
    result = []
    separator = "&" if "?" in path else "?"
    for page in range(1, 10001):
        items = api(f"{path}{separator}per_page=100&page={page}")
        if not isinstance(items, list):
            fail("Expected a paginated JSON array")
        result.extend(items)
        if len(items) < 100:
            return result
    fail("Unexpectedly large pagination result; refusing to truncate")


def valid_release(release):
    return (not release.get("draft") and not release.get("prerelease")
            and isinstance(release.get("id"), int) and release.get("published_at"))


def release_key(release):
    # GitHub returns UTC ISO-8601 strings in this fixed representation.
    date = release["published_at"]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", date):
        fail("Unrecognized published_at timestamp")
    return date, release["id"]


def success_ids(custom_releases):
    ids = set()
    for release in custom_releases:
        match = re.fullmatch(r"custom-upstream-([1-9][0-9]*)", release.get("tag_name", ""))
        if not match or release.get("draft"):
            continue
        upstream_id = int(match.group(1))
        expected = f"PiliPlus_custom_upstream_{upstream_id}_unsigned.hap"
        if any(asset.get("name") == expected and asset.get("state") == "uploaded"
               and asset.get("size", 0) > 0 for asset in release.get("assets", [])):
            ids.add(upstream_id)
    return ids


def select_releases(upstream, custom, requested_tag=""):
    releases = sorted((r for r in upstream if valid_release(r)), key=release_key)
    if not releases:
        fail("No published stable upstream releases found")
    if requested_tag:
        matches = [r for r in releases if r.get("tag_name") == requested_tag]
        if len(matches) != 1:
            fail("Requested tag must identify exactly one published stable upstream release")
        return matches
    completed = success_ids(custom)
    previous = [r for r in releases if r["id"] in completed]
    if not completed:
        return releases[-1:]  # Bootstrap deliberately skips the historical backlog.
    if not previous:
        fail("Completed release records exist but all corresponding upstream releases disappeared; choose an explicit tag")
    baseline = min(release_key(r) for r in previous)
    return [r for r in releases if release_key(r) >= baseline and r["id"] not in completed]


def output(name, value):
    text = str(value)
    if "\n" in text or "\r" in text:
        fail("Refusing multiline GitHub output")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
        handle.write(f"{name}={text}\n")


def load_state():
    return json.loads(STATE.read_text(encoding="utf-8"))


def save_state(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def plan():
    repo = os.environ["GITHUB_REPOSITORY"]
    upstream = pages(f"/repos/{UPSTREAM}/releases")
    custom = pages(f"/repos/{repo}/releases")
    # Release-list responses may truncate assets, so paginate the candidate assets too.
    for release in custom:
        if re.fullmatch(r"custom-upstream-[1-9][0-9]*", release.get("tag_name", "")):
            release["assets"] = pages(f"/repos/{repo}/releases/{release['id']}/assets")
    selected = select_releases(upstream, custom, os.environ.get("REQUESTED_TAG", ""))
    # GitHub matrices have a 256-job limit; the next schedule continues the backlog.
    selected = selected[:200]
    output("matrix", json.dumps({"release_id": [r["id"] for r in selected]}, separators=(",", ":")))
    output("has_work", "true" if selected else "false")
    print("Selected release IDs:", [r["id"] for r in selected])


def validate_tag(tag):
    if not isinstance(tag, str) or not tag or "\n" in tag or "\r" in tag:
        fail("Invalid upstream tag")
    run("git", "check-ref-format", "refs/tags/" + tag)
    return tag


def resolve(release_id):
    release = api(f"/repos/{UPSTREAM}/releases/{release_id}")
    if not valid_release(release) or release["id"] != release_id:
        fail("Release is no longer a published stable release")
    tag = validate_tag(release["tag_name"])
    tag_ref = "refs/tags/" + tag
    refs = run("git", "ls-remote", "--tags", "https://github.com/" + UPSTREAM + ".git",
               tag_ref, tag_ref + "^{}", capture=True)
    mapping = {}
    for line in refs.splitlines():
        sha, ref = line.split("\t", 1)
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            fail("Invalid upstream object SHA")
        mapping[ref] = sha
    sha = mapping.get(tag_ref + "^{}", mapping.get(tag_ref))
    if not sha:
        fail("Upstream release tag does not exist")
    save_state({"upstream_repository": UPSTREAM, "upstream_release_id": release_id,
                "upstream_tag": tag, "upstream_commit": sha,
                "upstream_published_at": release["published_at"],
                "upstream_url": release["html_url"],
                "kit_commit": os.environ["GITHUB_SHA"]})
    output("commit", sha)


def action_input(workflow, action, key):
    lines = workflow.splitlines()
    matches = [i for i, line in enumerate(lines)
               if re.fullmatch(r"\s*uses:\s*" + re.escape(action) + r"@[A-Za-z0-9_.-]+\s*", line)]
    if len(matches) != 1:
        fail(f"Unsupported upstream recipe: expected one {action}")
    index = matches[0]
    indent = len(lines[index]) - len(lines[index].lstrip())
    block = []
    for line in lines[index + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            break
        block.append(line)
    values = []
    for line in block:
        match = re.fullmatch(r"\s+" + re.escape(key) + r":\s*[\"']?([A-Za-z0-9_.-]+)[\"']?\s*", line)
        if match:
            values.append(match.group(1))
    if len(values) != 1:
        fail(f"Unsupported upstream recipe: missing/ambiguous {action} {key}")
    return values[0]


def extract_toolchain(workflow, profile):
    """Read data from the upstream recipe; never eval/execute its YAML/run blocks."""
    ohos = action_input(workflow, "ErBWs/setup-ohos", "version")
    java = action_input(workflow, "actions/setup-java", "java-version")
    if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", ohos) or java not in {"17", "21"}:
        fail("Unsupported SDK/Java version format; update the local adapter")
    clones = re.findall(r"^\s*git clone -b (oh-[A-Za-z0-9._-]+) "
                        r"(https://gitcode\.com/CPF-Flutter/flutter_flutter\.git) "
                        r"\$GITHUB_WORKSPACE/flutter\s*$", workflow, re.M)
    if len(clones) != 1 or clones[0][1] != FLUTTER_REPO:
        fail("Unsupported Flutter clone recipe; update the local adapter")
    target = re.findall(r"[\"']?targetSdkVersion[\"']?\s*:\s*[\"'](\d+\.\d+\.\d+)[\"']", profile)
    if len(target) != 1 or not ohos.startswith(target[0] + "."):
        fail("Harmony SDK and targetSdkVersion do not match; update the local adapter")
    required = "flutter build hap --release --dart-define-from-file=.vscode/env.json"
    if not any(line.strip() == "run: " + required or line.strip() == required
               for line in workflow.splitlines()):
        fail("Upstream HAP build command changed; update the local adapter")
    return {"ohos_version": ohos, "java_version": java,
            "flutter_ref": clones[0][0], "flutter_repo": clones[0][1]}


def prepare():
    state = load_state()
    if run("git", "rev-parse", "HEAD", cwd=SOURCE, capture=True) != state["upstream_commit"]:
        fail("Checkout does not match the resolved upstream commit")
    if run("git", "rev-parse", "--is-shallow-repository", cwd=SOURCE, capture=True) != "false":
        fail("Full git history is required for the upstream version code")
    # Read toolchain BEFORE applying our patch so it always describes the release baseline.
    settings = extract_toolchain((SOURCE / ".github/workflows/release.yml").read_text(encoding="utf-8"),
                                (SOURCE / "ohos/build-profile.json5").read_text(encoding="utf-8"))
    patches = sorted((KIT / "patches").glob("*.patch"))
    if not patches:
        fail("No patches/*.patch found")
    digest = hashlib.sha256()
    patch_records = []
    for patch in patches:
        content = patch.read_bytes()
        digest.update(patch.name.encode() + b"\0" + content + b"\0")
        patch_records.append({"file": patch.name, "sha256": hashlib.sha256(content).hexdigest()})
    run("git", "config", "user.name", "PiliPlus Custom Builder", cwd=SOURCE)
    run("git", "config", "user.email", "custom-builder@users.noreply.github.com", cwd=SOURCE)
    run("git", "am", "--3way", *[str(path) for path in patches], cwd=SOURCE)
    if not (SOURCE / "test/custom_patch").is_dir():
        fail("Patch regression test directory test/custom_patch is required")
    state.update(toolchain=settings, patches=patch_records, patch_set_sha256=digest.hexdigest(),
                 patched_commit=run("git", "rev-parse", "HEAD", cwd=SOURCE, capture=True),
                 upstream_commit_count=int(run("git", "rev-list", "--count", state["upstream_commit"],
                                               cwd=SOURCE, capture=True)))
    save_state(state)
    for name, value in settings.items():
        output(name, value)


def configure():
    state = load_state()
    flutter = WORKSPACE / "flutter"
    state["flutter_commit"] = run("git", "rev-parse", "HEAD", cwd=flutter, capture=True)
    run("dart", ".vscode/build_env.dart", state["upstream_tag"], cwd=SOURCE)
    env_path = SOURCE / ".vscode/env.json"
    if not env_path.is_file():
        fail("Upstream build_env.dart did not produce .vscode/env.json")
    build_env = json.loads(env_path.read_text(encoding="utf-8"))
    count = int(run("git", "rev-list", "--count", "HEAD", cwd=SOURCE, capture=True))
    if build_env.get("pili.code") != count or count <= state["upstream_commit_count"]:
        fail("Upstream version-code generation changed; update the local adapter")
    state["app_build_code"] = count
    pubspec_path = SOURCE / "pubspec.yaml"
    pubspec = pubspec_path.read_text(encoding="utf-8")
    names = re.findall(r"^name:\s*(\w+)\s*$", pubspec, re.M)
    if names not in [["PiliPlus"], ["piliplus"]]:
        fail("Unexpected Dart package name")
    if names == ["PiliPlus"]:
        pubspec_path.write_text(re.sub(r"^name:\s*PiliPlus\s*$", "name: piliplus", pubspec, flags=re.M), encoding="utf-8")
        for folder in [SOURCE / "lib", SOURCE / "test"]:
            for file in folder.rglob("*.dart"):
                text = file.read_text(encoding="utf-8")
                changed = text.replace("package:PiliPlus/", "package:piliplus/")
                if changed != text:
                    file.write_text(changed, encoding="utf-8")
    save_state(state)


def package():
    state = load_state()
    hap = SOURCE / "ohos/entry/build/default/outputs/default/entry-default-unsigned.hap"
    if not hap.is_file() or hap.stat().st_size == 0:
        fail("Unsigned HAP output missing; upstream output path may have changed")
    OUTPUT.mkdir(exist_ok=True)
    filename = f"PiliPlus_custom_upstream_{state['upstream_release_id']}_unsigned.hap"
    shutil.copy2(hap, OUTPUT / filename)
    state["hap_sha256"] = hashlib.sha256(hap.read_bytes()).hexdigest()
    state["hap_filename"] = filename
    source_filename = f"PiliPlus_custom_upstream_{state['upstream_release_id']}_source.tar.gz"
    run("git", "archive", "--format=tar.gz", "--output=" + str(OUTPUT / source_filename),
        "HEAD", cwd=SOURCE)
    state["source_filename"] = source_filename
    state["source_sha256"] = hashlib.sha256((OUTPUT / source_filename).read_bytes()).hexdigest()
    state["source_archive_note"] = ("Patched Git HEAD, before generated environment/version metadata "
                                    "and Dart package-name normalization. These build transforms "
                                    "are defined by the referenced kit commit's configure command.")
    (OUTPUT / "build-provenance.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save_state(state)


def publish():
    state = load_state()
    repo = os.environ["GITHUB_REPOSITORY"]
    tag = f"custom-upstream-{state['upstream_release_id']}"
    notes = (f"Custom unsigned PiliPlus HAP\n\n"
             f"- Upstream: {state['upstream_url']}\n"
             f"- Upstream tag: `{state['upstream_tag']}`\n"
             f"- Upstream commit: `{state['upstream_commit']}`\n"
             f"- Patch-set SHA-256: `{state['patch_set_sha256']}`\n"
             f"- Kit commit: `{state['kit_commit']}`\n"
             f"- HAP SHA-256: `{state['hap_sha256']}`\n\n"
             "Sign this unsigned HAP with your usual signing tool before installation. "
             "Keep the application ID and signing identity compatible with your existing installation.\n\n"
             "See build-provenance.json for toolchain versions, Flutter commit, and individual patch checksums. "
             "The source archive contains patched Git HEAD, before generated build metadata and "
             "package-name normalization performed by the public kit script.\n")
    existing = [r for r in pages(f"/repos/{repo}/releases") if r.get("tag_name") == tag]
    if len(existing) > 1:
        fail("Multiple custom releases found for the same tag")
    if existing:
        release = existing[0]
        # A manual retry replaces this tool's output, while unrelated release assets remain.
        release = api(f"/repos/{repo}/releases/{release['id']}", "PATCH", data={"draft": True})
    else:
        release = api(f"/repos/{repo}/releases", "POST", data={
            "tag_name": tag, "target_commitish": state["kit_commit"], "draft": True,
            "name": "Custom " + state["upstream_tag"], "body": notes, "prerelease": False})
    for asset in pages(f"/repos/{repo}/releases/{release['id']}/assets"):
        if asset["name"] in {state["hap_filename"], state["source_filename"], "build-provenance.json"}:
            api(f"/repos/{repo}/releases/assets/{asset['id']}", "DELETE")
    upload_url = release["upload_url"].split("{", 1)[0]
    for name in [state["hap_filename"], state["source_filename"], "build-provenance.json"]:
        asset = api(upload_url + "?name=" + quote(name, safe=""), "POST",
                    raw=(OUTPUT / name).read_bytes(), content_type="application/octet-stream")
        if asset.get("state") != "uploaded" or asset.get("size") != (OUTPUT / name).stat().st_size:
            fail("Asset upload was not confirmed; release remains draft and will be retried")
    # This final mutation is the success marker. Failed uploads never mark a release complete.
    published = api(f"/repos/{repo}/releases/{release['id']}", "PATCH", data={
        "draft": False, "prerelease": False, "name": "Custom " + state["upstream_tag"],
        "body": notes, "make_latest": "false"})
    if published.get("draft"):
        fail("Release did not become published")
    print("Published:", published["html_url"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["plan", "resolve", "prepare", "configure", "package", "publish"])
    parser.add_argument("--release-id", type=int)
    args = parser.parse_args()
    if args.command == "resolve":
        if not args.release_id or args.release_id <= 0:
            parser.error("--release-id must be a positive integer")
        resolve(args.release_id)
    else:
        globals()[args.command]()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, HTTPError, subprocess.CalledProcessError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
