# Contributing

The repository is developed through gated milestones. Changes must remain within the active
milestone and must not introduce claims unsupported by generated evidence.

## Baseline expectations

- Use C++20 and preserve out-of-source builds.
- Keep production ownership explicit; do not use raw owning pointers or naked `new`/`delete`.
- Do not use floating-point values for price ordering.
- Preserve the normative contract in `docs/MATCHING_SEMANTICS.md` and `docs/INVARIANTS.md`.
- Keep normal domain rejection out of exception control flow.
- Preserve single-writer deterministic matching semantics unless a later architecture decision
  explicitly changes that boundary.
- Do not add concurrency or performance-oriented complexity before a benchmark baseline exists.
- Pin external dependencies to reproducible identities and verify available integrity metadata.
- Do not bypass dependency hash failures.
- Keep `CMakeUserPresets.json` local and untracked.
- Apply warning policy to first-party code without imposing project warnings on external
  dependencies.
- Do not weaken qualification-only invariant or exhaustion coverage merely to simplify an
  implementation change.

## Local qualification baseline

Use an active compiler environment before configuring.

Debug:

~~~powershell
cmake --preset debug --fresh
cmake --build --preset debug
ctest --preset debug --output-on-failure
~~~

Release:

~~~powershell
cmake --preset release --fresh
cmake --build --preset release
ctest --preset release --output-on-failure
~~~

Then verify repository hygiene:

~~~powershell
git diff --check
git status --short
git status --ignored --short
~~~

At the original M3 implementation freeze, the repository contained 74 CTest tests and the exact
implementation commit passed all 74 in both Debug and Release locally and in GitHub Actions.

The current M3-r1 qualified inventory contains 77 CTest tests. Corrective merged-main commit
`afaf6f4466d47811593d66ddc96d5eb30921159d` passed all 77 in both Debug and Release in GitHub Actions run
`35386634152`; local M3E.3 qualification also passed 77/77 in both configurations. M3-r1 also retains the
separately qualified `BUILD_TESTING=OFF` Release production build boundary.

The original and corrective M3 tags are immutable qualification provenance and must not be moved or rewritten
merely to make later documentation appear current.

This does not qualify static analysis, sanitizers, a standalone replay harness, benchmarking,
performance, concurrency, persistence, recovery, networking or exchange fidelity. Those capabilities
require later bounded milestones and explicit evidence.

## Change discipline

Before a change, state its milestone, scope, allowed files, and potentially affected invariants.
After a change, inspect the diff and repository status and report verification output and residual
risk. Keep unrelated repairs in separate changes.

Do not weaken, remove, skip, or conditionally disable a failing qualification gate merely to obtain
a passing result. Preserve the failure, identify its cause, and make any correction within an
explicitly bounded scope.

Historical ADRs are records of decisions at their acceptance point. Do not rewrite them merely to
make later implementation status look current; use current-state documentation or a new ADR when a
decision changes.
