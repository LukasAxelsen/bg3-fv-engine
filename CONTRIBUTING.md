# Contributing to VALOR

## Development Setup

```bash
git clone https://github.com/<you>/bg3-fv-engine.git
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
2. Add axioms to `src/2_fv_core/Axioms/BG3Rules.lean`.
3. Add proof targets to `src/2_fv_core/Proofs/Exploits.lean` or `Termination.lean`.
4. Add a benchmark annotation to `dataset/manual_annotations/`.
5. Run `lake build` and `python3 -m pytest tests/ -v` before submitting.

## Pull Request Checklist

- [ ] All 23+ existing tests pass
- [ ] New code has type hints (Python) or type annotations (Lean)
- [ ] No fabricated game data — all values sourced from bg3.wiki with provenance
- [ ] `lake build` produces no new errors (existing `sorry` is acceptable)
- [ ] README updated if public API changed
