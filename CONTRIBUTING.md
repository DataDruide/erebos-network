# Contributing to Erebos

Thanks for considering a contribution. Erebos is a research prototype
for a privacy-first anonymizing network. Contributions are welcome, but
this is a small project — we prefer **small, well-scoped patches** over
large refactorings, and we prefer **honest bug reports** over feature
wishes.

## Quick Start

```bash
git clone https://github.com/DataDruide/erebos-network.git
cd erebos-network
python3 -m venv .venv
source .venv/bin/activate
make install
make verify
pytest tests/ -q
```

If `make verify` fails, the environment differs from the one the
lockfile was generated in. See `requirements.lock` for the pinned
versions.

## How to Contribute

1. **Open an issue first** for anything beyond a one-line fix. This
   saves you time and avoids duplicate work.
2. **Fork** the repo and create a branch.
3. **Write a test** for any behavior change. The project has 700
   tests; they run in under 20 seconds and are the primary defense
   against regressions.
4. **Commit** with a short, descriptive message. Prefixes we use:
   `feat(scope):`, `fix(scope):`, `docs(scope):`, `test(scope):`,
   `build(scope):`.
5. **Open a pull request** against `main`. Include what the change
   does, why it is needed, and how it was tested.

## What We Are Looking For

- **Bug reports** with a minimal reproduction. If it is a security bug,
  do **not** open an issue — see SECURITY.md for the disclosure path.
- **Tests** that cover a behavior which was previously untested.
- **Calibration data**: additional tcpdump captures of real HTTP
  traffic, so the cover parameters can be refined beyond the single
  session used in v0.4.2. See scripts/analyze_traffic.py.
- **Documentation** improvements, especially clarifying SECURITY.md
  where it is unclear.
- **Small fixes**: typos, dead code removal, build reproducibility
  improvements.

## What We Are Not Looking For

- **Large refactorings without prior discussion.** The code has a
  specific structure that came out of iterative design; a clean
  rewrite would discard context.
- **Feature wishes without a use case.** Describe the problem the
  feature solves, not just the feature itself.
- **Comparisons to Tor or Nym** in the code or docs. We describe what
  Erebos does, not what it does better.
- **Branding changes** (renaming, logos, taglines). Not part of the
  current scope.

## Code Style

No automated linter is enforced. The principles:

- **Explicit over implicit.** Prefer clear variable names over
  abbreviations.
- **Comment the why, not the what.** Code says what it does;
  comments explain why a decision was made.
- **Tests are documentation.** A test that demonstrates a behavior is
  often clearer than a comment.
- **Avoid dependencies** unless they are strictly necessary.
  requirements.lock lists the full set; adding to it is a real cost.

## Security Issues

**Do not open a public issue for security problems.** See SECURITY.md
for the disclosure path. We aim to respond within 72 hours. There is
no monetary bug bounty — this is a research project, not a commercial
product.

## License

Erebos is licensed under MPL-2.0. By contributing, you agree that your
contribution is made under the same license. There is no separate CLA.

## Questions

Open a GitHub Discussion or contact the maintainer via the address in
the repository profile.
