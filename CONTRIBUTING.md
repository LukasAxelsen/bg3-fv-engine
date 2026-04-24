# Contributing to VALOR

## Development setup

```bash
git clone https://github.com/LukasAxelsen/bg3-fv-engine.git
cd bg3-fv-engine
python3 -m pip install -r requirements.txt
python3 -m pytest tests/ -q                # 55 tests, must pass before any PR

# Lean side (requires elan):
cd src/2_fv_core && lake update && lake build
```

## Coding standards

- **Python**: type-annotated, `Path` over `str` for filesystem, `dataclass` or Pydantic for data.
- **Lean 4**: imports first, then a `/-! ... -/` module doc.  No bare `/-- ... -/` comments unattached to declarations.  The default build target must be `sorry`-free; CI enforces this.
- **Lua**: all globals under the `VALOR` table; wrap external calls in `pcall`.

## Adding a research problem

1. Open an issue describing the game mechanic and why it is interesting for formal verification.
2. Create a self-contained file `src/2_fv_core/Scenarios/P<N>_<Name>.lean` (use `P14_AdvantageAlgebra.lean` as the canonical template).
3. The scenario should be self-contained — do **not** import `Axioms/BG3Rules.lean` unless you intentionally want your proof to depend on those assumed game-rule axioms.
4. Include at least one `theorem` proved via `native_decide`, `omega`, `decide`, or structural tactics.  No `sorry` is permitted in the default build target; open sub-problems can stay in `Scenarios_wip/`.
5. Add `` `Scenarios.P<N>_<Name> `` to the `roots` list of the `VALOR` library in `src/2_fv_core/lakefile.lean`.
6. Run `lake build` (zero errors, zero warnings) and `python3 -m pytest tests/ -q` before submitting.

## Pull request checklist

- [ ] `python3 -m pytest tests/ -q` — all 55 tests pass.
- [ ] `cd src/2_fv_core && lake build` — zero errors, zero warnings.
- [ ] No new `sorry` in the default build target (`Core/`, `Axioms/`, `Proofs/`, `Scenarios/`).
- [ ] No fabricated game data — every numeric constant traceable to bg3.wiki / SRD with a comment.
- [ ] README updated if the verified scope changed.
