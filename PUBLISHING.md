# Publishing and adopting io-policy

The GitHub repository is `112345brian/io-policy` (public). The PyPI release is deliberately NOT done yet.

## Naming

- Repository: `io-policy`. Import name: `io_policy`.
- Distribution name: `io-policy-engine`. The name `io-policy` is already taken on PyPI by an unrelated project
  (checked 2026-10-25), and `io_policy` normalizes to the same name, so this distribution cannot use it. Keep the
  distribution name different from the taken one; the import name does not need to change.
- Caveat: an unrelated PyPI project may also ship a top-level `io_policy` package. Do not install both into one
  environment.

## Later: publishing to PyPI (not done)

Ready first:

1. `version` in `pyproject.toml` (0.1.0 now; bump per release, bounded `>=x.y,<x.(y+1)` pins while the major is 0).
2. Licence: MIT, `LICENSE` at the root, `license = "MIT"` and `license-files = ["LICENSE"]` (both already set; the
   built wheel and sdist contain it).
3. Classifiers: set (Alpha, Python 3.11 to 3.13, `Typing :: Typed`); `py.typed` ships in the wheel.
4. Project URLs point at the GitHub repo.
5. Trusted publishing: on pypi.org create the project `io-policy-engine` (a "pending publisher" works before the
   first upload) trusting repository `112345brian/io-policy`, a workflow file (e.g. `publish.yml`) and an
   environment name. Then add a `publish.yml` that builds with `python -m build` and uploads with
   `pypa/gh-action-pypi-publish` on a GitHub release. `ci.yml` intentionally has no publish step. Check how
   launch-runner publishes (it is on PyPI) and match it.
6. Tag `v0.1.0` and create the release only when you want that publish to run.
