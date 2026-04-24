# Contributing to VALOR

## Development Setup

```bash
git clone https://github.com/LukasAxelsen/bg3-fv-engine.git
cd bg3-fv-engine
python3 -m pip install -r requirements.txt
python3 -m pytest tests/ -v  # must pass before any PR
```

## Coding Standards

- **Python**: type-annotated, `Path` over `str` for filesystem, `dataclass` or Pydantic for data.
- **Lean 4**: follow mathlib naming conventions; every `sorry` must have a comment explaining the proof strategy.
- **Lua**: all globals under the `VALOR` table; wrap external calls in `pcall`.

## Adding a Research Problem

1. Open an issue describing the game mechanic and why it is interesting for formal verification.
2. Create a self-contained file `src/2_fv_core/Scenarios/P<N>_<Name>.lean` (see existing files for the template).
3. The scenario must **not** import `Axioms/BG3Rules.lean` — define all types locally so the proof is self-contained.
4. Include at least one `theorem` proved via `native_decide` or structural tactics, and label open questions with `sorry` + a comment describing the proof strategy.
5. Add the scenario title to the `lakefile.lean` if a new library target is needed.
6. Run `lake build` and `python3 -m pytest tests/ -v` before submitting.

## Pull Request Checklist

- [ ] All existing tests pass (`python3 -m pytest tests/ -v`)
- [ ] New code has type hints (Python) or type annotations (Lean)
- [ ] No fabricated game data — all values sourced from bg3.wiki with provenance
- [ ] `lake build` produces no new errors (existing `sorry` is acceptable)
- [ ] README updated if public API changed
