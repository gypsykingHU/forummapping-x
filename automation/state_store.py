#!/usr/bin/env python3
"""Durable, conflict-safe state writing for the Forummapping posters.

WHY THIS EXISTS
---------------
The 7-day no-repeat lock only works if the record of "this ID was posted"
actually survives the run. Until now that record was written by the workflow's
"Save state" step: git add / commit / rebase / push. That has three failure
modes, and we hit all three:

  1. the rebase could fail and kill the step (fixed separately),
  2. two overlapping runs race and one push is lost,
  3. the runner's checkout can already be stale, so it pushes a CSV that
     silently reverts another run's stamps.

Any of those means the next run reads a database that has forgotten what was
posted -- and posts it again. That is exactly how two maps went out twice.

WHAT THIS DOES INSTEAD
----------------------
Writes the CSV through the GitHub Contents API as an atomic
read-modify-write against the remote file:

    GET  the file  -> content + blob sha
    apply our one-row change to THE REMOTE CONTENT (not our local copy)
    PUT  the file  with that sha as a precondition

If anyone else wrote in between, the sha no longer matches, GitHub rejects it
with 409, and we loop: re-read, re-apply, re-PUT. So concurrent runs merge
instead of clobbering, and a stale checkout cannot revert anything.

Authentication uses the GITHUB_TOKEN that Actions injects automatically on
every run (the workflows already declare `permissions: contents: write`).
No new secret to configure.

Outside Actions -- on Milan's machine -- there is no token and no
GITHUB_REPOSITORY, so it writes the local file and reports that git will
carry it. Same call signature either way.
"""
import base64
import csv
import io
import json
import os
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
ATTEMPTS = 5


def _token():
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def _repo():
    return os.environ.get("GITHUB_REPOSITORY")


def available():
    """True when we can write straight to the remote (i.e. inside Actions)."""
    return bool(_token() and _repo())


def _request(method, url, body=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {_token()}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=data, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode() or "{}")


def _get_remote(path, branch):
    url = f"{API}/repos/{_repo()}/contents/{path}?ref={branch}"
    status, payload = _request("GET", url)
    text = base64.b64decode(payload["content"]).decode("utf-8")
    return text, payload["sha"]


def _put_remote(path, branch, text, sha, message):
    url = f"{API}/repos/{_repo()}/contents/{path}"
    return _request("PUT", url, {
        "message": message,
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "sha": sha,
        "branch": branch,
    })


def _rows_to_csv(rows, fieldnames):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def update_csv_row(path, id_column, id_value, changes, message, branch="main"):
    """Set `changes` on the row whose `id_column` == `id_value`, durably.

    Returns True if the change is safely persisted (remotely, or locally when
    running off-Actions). Returns False if it could not be persisted -- and the
    caller MUST treat False as "do not post", because an unrecorded post is a
    duplicate waiting to happen.
    """
    local = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)

    if not available():
        # Local / no-token run: write the file and let the workflow's git step
        # (or Milan) carry it. Nothing to merge against.
        rows, fields = _read_local(local)
        if not _apply(rows, id_column, id_value, changes):
            print(f"state: {id_value} not found in {path}")
            return False
        with open(local, "w", newline="", encoding="utf-8") as f:
            f.write(_rows_to_csv(rows, fields))
        print(f"state: {id_value} stamped locally in {path} (no GITHUB_TOKEN — git will carry it)")
        return True

    for attempt in range(1, ATTEMPTS + 1):
        try:
            text, sha = _get_remote(path, branch)
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
            fields = reader.fieldnames
            if id_column not in (fields or []):
                print(f"state: {path} on {branch} has no {id_column} column yet — "
                      f"push the ID migration before relying on remote state")
                return False
            if not _apply(rows, id_column, id_value, changes):
                print(f"state: {id_value} not found in remote {path}")
                return False
            _put_remote(path, branch, _rows_to_csv(rows, fields), sha,
                        f"{message} [{id_value}]")
            # keep the working copy in step so the rest of the run sees it
            with open(local, "w", newline="", encoding="utf-8") as f:
                f.write(_rows_to_csv(rows, fields))
            print(f"state: {id_value} recorded on {branch} (attempt {attempt})")
            return True
        except urllib.error.HTTPError as e:
            if e.code in (409, 422) and attempt < ATTEMPTS:
                print(f"state: someone else wrote {path} first; re-reading "
                      f"(attempt {attempt})")
                time.sleep(1.5 * attempt)
                continue
            print(f"state: HTTP {e.code} writing {path}: {(e.read() or b'')[:200]!r}")
            return False
        except Exception as e:                      # network, JSON, anything
            if attempt < ATTEMPTS:
                print(f"state: {type(e).__name__} on attempt {attempt}: {e}; retrying")
                time.sleep(1.5 * attempt)
                continue
            print(f"state: gave up writing {path}: {e}")
            return False
    return False


def read_csv(path, branch="main"):
    """Read a CSV from the remote branch. Returns (rows, fieldnames) or None.

    The poster uses this instead of its own checkout, because the checkout is a
    snapshot taken at job start and another run may have stamped rows since.
    """
    if not available():
        return None
    try:
        text, _ = _get_remote(path, branch)
    except Exception as e:
        print(f"state: could not read {path} from {branch}: {e}")
        return None
    reader = csv.DictReader(io.StringIO(text))
    return list(reader), reader.fieldnames


def _read_local(local):
    with open(local, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader), reader.fieldnames


def _apply(rows, id_column, id_value, changes):
    for r in rows:
        if r.get(id_column) == id_value:
            r.update(changes)
            return True
    return False
