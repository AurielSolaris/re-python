# re:python

A fork of CPython 3.14 — maintenance-focused, with selected feature additions.

> This file is the fork's README. The upstream `README.rst` at the repository
> root is left untouched so upstream merges and cherry-picks apply cleanly.

## Goals

- Maintain a stable, controlled Python 3.14 base
- Track upstream CPython 3.14 security patches via automated CVE monitoring
- Incrementally remove the C++ code and bootstrap dependency
- Eventually: pure C + x86-64 ASM runtime

## Golden Rule

**Remove the Python bootstrap incrementally, without removing functionality
or causing crashes.**

- Changes land in small steps, and each step must leave a working interpreter.
- A Python module is only removed once nothing calls it at runtime.
  "Nothing" includes C code that imports it lazily, and features that only
  the Python version implements.
- Tests that only existed for a removed implementation are deleted or
  rewritten. Tests of user-visible behavior must keep passing.

## Changes from Upstream

Newest first. Each entry says what was removed, what replaced it, and what
was deliberately kept.

### Remove pure-Python fallbacks that have C versions (Tier 0)

Branch: `tier0-drop-py-fallbacks`

| Removed | C version (now required) | Lines removed |
|---------|--------------------------|---------------|
| `Lib/_py_abc.py` | `_abc` (built in) | 152 |
| `Lib/_pydatetime.py` | `_datetime` | 2,734 |
| `Lib/_pyio.py` | `_io` (built in) | 2,764 |

- `abc.py` and `datetime.py` import their C module directly; there is no
  fallback anymore. `zoneinfo` no longer handles the "no `_datetime`" case.
- Tests: the `_Pure`/`Py*` variants of the abc, datetime and io test suites
  were removed, and the C variants are unchanged. Where a `Py*` class was a
  base class (`test_memoryio`), it became a mixin. `test_importlib`'s
  partial-write test now runs through the C `BufferedWriter` instead of
  swapping in `_pyio`. `test_inspect` no longer checks the pure-Python `abc`.
- Verified: full test suite on Windows x64. The only failures are 3
  environment-specific ones that don't involve these modules (`test_os`
  device encoding without a real console, `test_shutil` with
  `NoDefaultCurrentDirectoryInExePath` set, `test_subprocess` with a `cmd`
  AutoRun hook).
- **Kept:** `Lib/_pydecimal.py`. `_decimal` calls it at runtime for format
  specs libmpdec can't parse: `#` alternate form, `_` grouping, grouping in
  the fractional part, and zero-padding with separators. It can only be
  removed after that formatting is ported to C.
- **Kept:** `_py_warnings` (`warnings.py` always uses it) and `_pylong`
  (called from `Objects/longobject.c` for very large ints).

## Setting Up the Fork

```bash
# Clone only the 3.14 branch
git clone --single-branch --branch 3.14 https://github.com/python/cpython.git re-python
cd re-python

# Keep upstream for CVE backports, point origin to the fork
git remote rename origin upstream
git remote add origin https://github.com/AurielSolaris/re-python.git

git push -u origin 3.14
```

Set `3.14` as the default branch on GitHub.

Upstream's own CI workflows (`build.yml`, `jit.yml`, …) come along with the
clone and will run on every push. Disable the ones you don't need under
**Actions → (workflow) → Disable workflow** to save runner minutes.

## CVE Monitoring

| File | Role |
|------|------|
| `.github/workflows/cve-watch.yml` | Runs every Monday 09:00 UTC, or manually via **Run workflow** |
| `.github/scripts/cve-watch.sh` | Finds upstream security commits and opens issues |

### How commits are detected

CPython rarely puts `CVE-…` in commit subjects. Instead, every security fix
ships a NEWS entry under `Misc/NEWS.d/next/Security/`. A commit on upstream
`3.14` is flagged when it either:

1. **adds a file under `Misc/NEWS.d/next/Security/`** (the primary signal), or
2. mentions `CVE-YYYY-NNNN`, `GHSA-xxxx-xxxx-xxxx`, `[security]`,
   `security fix`, or `vulnerabilit…` anywhere in its full message.

Each run scans the last 45 days (adjustable with the `days` input on a manual
run). Every issue carries a hidden `<!-- upstream-commit: <hash> -->` marker, and
commits that already have an issue (open *or* closed) are skipped. Overlapping
windows therefore never produce duplicates.

Issues include the upstream link, any CVE/GHSA IDs, the NEWS entry text, the
changed files, and a backport checklist. The `security` and `upstream` labels
are created automatically on each run.

### Testing locally

```bash
# Prints what would be filed; touches nothing on GitHub
DRY_RUN=1 bash .github/scripts/cve-watch.sh . "45 days ago"
```

## Backport Process

1. An issue is opened automatically by the workflow
2. Assess: does the fix apply to re:python's codebase?
3. If yes, backport on a `security/*` branch:
   ```bash
   git fetch upstream 3.14
   git switch -c security/gh-NNNNNN 3.14
   git cherry-pick -x <upstream-hash>   # -x records the upstream hash
   ```
4. Resolve conflicts, run tests (`make test`, or `PCbuild\rt.bat -q` on Windows)
5. Merge into `3.14` and close the issue with the backport commit hash

While re:python still tracks upstream closely, `git merge upstream/3.14`
picks up all security fixes at once. Switch to per-commit cherry-picks once
the C++/ASM work diverges.

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `3.14` | Main development branch (default) |
| `security/*` | Backport branches for CVE fixes |

## Notes

- Upstream remote (`upstream`) is kept alive for cherry-picking security commits
- C++ removal and bootstrap removal are long-term goals — tracked separately
- Breaking changes during the C→ASM transition are expected and intentional
