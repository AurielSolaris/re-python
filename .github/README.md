# re:python

A fork of CPython 3.14 — maintenance-focused, with selected feature additions.

> This file is the fork's README. The upstream `README.rst` at the repository
> root is left untouched so upstream merges and cherry-picks apply cleanly.

## Goals

- Maintain a stable, controlled Python 3.14 base
- Linux and Windows only (see Supported Platforms)
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

## Supported Platforms

| Platform | Status |
|----------|--------|
| Linux (x86-64, plus whatever upstream's Linux CI covers) | Supported |
| Windows (x64, plus the Win32/ARM64 builds upstream's CI covers) | Supported |
| macOS, iOS, Android, WebAssembly (WASI, Emscripten) | **Not supported.** Their build trees and CI jobs are removed. |

`configure` still has its macOS/iOS framework and WebAssembly options, but
the directories those builds need are gone, so they fail.

## Changes from Upstream

Newest first. Each entry says what was removed, what replaced it, and what
was deliberately kept.

### Drop macOS, iOS, Android and WebAssembly support

Branch: `drop-non-linux-windows`

re:python only targets Linux and Windows, so the other platforms' build
trees and CI jobs were dead weight.

- **Removed directories** (183 files, about 17,400 lines):

  | Directory | What it was |
  |-----------|-------------|
  | `Android/` | Android build scripts and testbed app |
  | `Apple/`, `iOS/` | iOS/tvOS/watchOS framework builds and Xcode testbed |
  | `Mac/` | macOS installer, framework build, IDLE app, Python Launcher |
  | `Platforms/emscripten/`, `Tools/wasm/` | Emscripten and WASI builds |

- **Removed CI:** the `build-macos`, `build-android`, `build-ios`,
  `build-emscripten` and `build-wasi` jobs in `build.yml` (and the
  `reusable-macos`/`-wasi`/`-emscripten` workflows they called), and the
  macOS jobs in `jit.yml` and `tail-call.yml`. Each PR's CI no longer
  waits on macOS runners.
- **Also removed:** the ruff pre-commit hooks for `Apple/` and `Tools/wasm/`
  (Lint fails on a hook that matches no files), and the `CODEOWNERS` lines
  for the removed directories.
- **Kept on purpose:** the macOS, iOS and Android code inside the shared
  code: `#ifdef __APPLE__` in `Modules/` and `Python/`, `sys.platform ==
  'darwin'` branches in `Lib/`, helper modules like `_osx_support`,
  `_ios_support` and `_android_support`, and the `configure` and
  `Makefile.pre.in` options and targets. That code never runs on Linux or
  Windows, and upstream security fixes often touch those files, so removing
  it would turn every backport into a merge conflict. Public APIs such as
  `platform.mac_ver()`, `platform.ios_ver()` and `platform.android_ver()`
  keep working on every platform.
- **Verified:** no Linux or Windows build step, test, regen target or SBOM
  entry references the removed directories. The edited workflows parse, and
  every `needs:` and reusable workflow they reference exists. CI on Linux
  and Windows is run on this PR.

### Port `_pydecimal`'s formatting to C and drop the `_pydecimal` fallback

Branch: `port-pydecimal-format`

`_decimal` used to import the 6,400-line `_pydecimal` at runtime whenever a
format specifier was one libmpdec doesn't support. Now C handles those too,
so nothing in the runtime imports `_pydecimal`.

- **Added:** `dec_format_ext()` in `Modules/_decimal/_decimal.c`, a C port
  of `_pydecimal`'s PEP 3101 code (`__format__`, `_parse_format_specifier`,
  `_insert_thousands_sep`, `_format_align`). It handles:
  - `#` (alternate form) and `_` as the thousands separator;
  - separators in the fractional part (`.3_f`);
  - `z` combined with those;
  - Unicode digits in the width or precision;
  - the `n` type with any of the above.

  It lives in `_decimal.c`, not libmpdec, so builds that use the system
  libmpdec get it too. It also honours the test-only `override` locale
  dict, which the old fallback silently ignored.
- **Bug fix (upstream has it too):** a NUL after the first character cut the
  specifier short for libmpdec, so `format(Decimal(5), '5\0xyz')` returned
  `'    5'`. Such specifiers now raise `ValueError` like any other invalid one.
- **Changed:** `decimal.py` imports `_decimal` directly. Default builds
  always have `_decimal`: Windows always builds it, and `configure` falls
  back to the bundled libmpdec when no system copy is found. A build that
  turns `_decimal` off on purpose (`Modules/Setup.local`, or
  `py_cv_module__decimal=n/a`) no longer has a `decimal` module at all.
- **CI:** the MSan job used to disable `_decimal`, because a system libmpdec
  that isn't built with MSan causes false positives. It now builds
  `_decimal` against the bundled libmpdec (`--without-system-libmpdec`),
  which is compiled with MSan, so MSan also checks the new C formatter.
- **Moved:** `Lib/_pydecimal.py` to `Lib/test/support/_pydecimal.py`, with
  its content unchanged so upstream fixes still cherry-pick. It is the
  reference implementation for the `Py*` variants of `test_decimal`,
  `test_inspect` and the `Modules/_decimal/tests` scripts. It can no longer
  be imported as `_pydecimal`.
- **Verified:**
  - a differential fuzz of 400,000 random specifiers, values, rounding
    modes and override dicts against `_pydecimal`, with 0 mismatches;
  - 1,100 `n`-format cases under 10 real Windows locales, with 0 mismatches;
  - new tests in `test_decimal` (`CWhitebox`) for the C-vs-reference grid,
    the override dict and the embedded-NUL bug;
  - a partial full-suite run (stopped at about 425 of 537 test files). The
    only failures were `test_os` and `test_shutil`, the known
    environment-specific ones listed under Tier 0.

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
- **Kept (at the time):** `Lib/_pydecimal.py`. `_decimal` called it at
  runtime for format specs libmpdec can't parse. That formatting has since
  been ported to C (see the entry above).
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
