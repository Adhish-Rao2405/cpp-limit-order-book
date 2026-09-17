# Contributing

The repository is developed through gated milestones. Changes must remain within the active
milestone and must not introduce claims unsupported by generated evidence.

## Baseline expectations

- Use C++20 and preserve out-of-source builds.
- Keep production ownership explicit; do not use raw owning pointers or naked `new`/`delete`.
- Do not use floating-point values for price ordering.
- Keep normal domain rejection out of exception control flow.
- Do not add concurrency or performance-oriented complexity before correctness qualification is
  frozen and a benchmark baseline exists.
- Pin external dependencies to reproducible identities and verify available integrity metadata.
- Do not bypass dependency hash failures.
- Keep `CMakeUserPresets.json` local and untracked.
- Apply warning policy to first-party code without imposing project warnings on external
  dependencies.

## Local M1 qualification

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

M1 provides automated tests but does not yet qualify static analysis, sanitizers, matching
correctness, benchmarking, performance, or concurrency. Those capabilities belong to later
milestones and must not be claimed early.

## Change discipline

Before a change, state its milestone, scope, allowed files, and potentially affected invariants.
After a change, inspect the diff and repository status and report verification output and residual
risk. Keep unrelated repairs in separate changes.

Do not weaken, remove, skip, or conditionally disable a failing qualification gate merely to obtain
a passing result. Preserve the failure, identify its cause, and make any correction within an
explicitly bounded scope.
