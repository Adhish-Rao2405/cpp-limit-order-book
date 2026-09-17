# Contributing

The repository is being developed through gated milestones. Changes must remain within the active
milestone and must not introduce claims unsupported by generated evidence.

## Baseline expectations

- Use C++20 and preserve out-of-source builds.
- Keep production ownership explicit; do not use raw owning pointers or naked `new`/`delete`.
- Do not use floating-point values for price ordering.
- Keep normal domain rejection out of exception control flow.
- Do not add concurrency or performance-oriented complexity before correctness qualification is
  frozen and a benchmark baseline exists.
- Pin external dependencies when they are introduced.
- Keep `CMakeUserPresets.json` local and untracked.

## Local foundation check

```powershell
cmake --preset debug
cmake --build --preset debug
git diff --check
git status --short
```

Later milestones will add tests, static-analysis execution, sanitizers, and benchmark qualification.
Those checks are not yet available in M0.

## Change discipline

Before a change, state its milestone, scope, allowed files, and potentially affected invariants.
After a change, inspect the diff and repository status and report verification output and residual
risk. Keep unrelated repairs in separate changes.
