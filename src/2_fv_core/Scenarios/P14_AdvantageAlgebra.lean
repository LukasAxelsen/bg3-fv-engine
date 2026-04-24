/-!
# P14 — Advantage/Disadvantage as a Commutative, Non-Associative,
        Annihilating Magma

## Background (bg3.wiki / 5e SRD §7)

The advantage/disadvantage system has four design properties:

1. **Idempotency**: `adv ⊕ adv = adv`; `disadv ⊕ disadv = disadv`
2. **Annihilation**: `adv ⊕ disadv = normal` (regardless of multiplicity)
3. **Identity**: `normal` is two-sided neutral
4. **Commutativity**: order of sources doesn't matter

## Academic finding (formalised below)

A natural binary-combine reading of the rules turns out to be
**commutative but NOT associative**:

```
(disadv ⊕ adv) ⊕ adv = normal ⊕ adv = adv
disadv ⊕ (adv ⊕ adv) = disadv ⊕ adv = normal
```

We refute associativity with an explicit witness (`combine_not_assoc`).
The actually-correct multi-source rule is a *classify-then-resolve*
operator (`classify`) which is order- and grouping-independent because
it depends only on the *presence/absence* of each advantage/disadvantage
source, not their interleaving.  We prove `classify` agrees with the
binary `combine` on lists of length ≤ 2 (`classify_pair`).

This places the system in the algebraic family of
**commutative non-associative magmas with absorbing element**, related
to the three-element bilattice of Ginsberg (1988) but strictly weaker
on the associativity axis.

## Quantifier structure of the main probability theorem

  ∀ t ∈ [2..20], probAdvantage400 t ≥ probNormal20 t · 20

Bounded over `Fin 19`, discharged by `decide` and lifted to `Nat`.
-/

namespace VALOR.Scenarios.P14

-- ── The three-element roll modifier algebra ─────────────────────────────

inductive RollMod where
  | advantage    -- roll 2d20, take higher
  | disadvantage -- roll 2d20, take lower
  | normal       -- roll 1d20
  deriving DecidableEq, Repr

/-- Binary resolution: any adv + any disadv = normal. -/
def RollMod.combine (a b : RollMod) : RollMod :=
  match a, b with
  | .normal, x => x
  | x, .normal => x
  | .advantage, .advantage => .advantage
  | .disadvantage, .disadvantage => .disadvantage
  | .advantage, .disadvantage => .normal
  | .disadvantage, .advantage => .normal

/-- Resolve a list of modifiers left-to-right. -/
def resolve : List RollMod → RollMod
  | [] => .normal
  | [x] => x
  | x :: xs => RollMod.combine x (resolve xs)

-- ── Algebraic laws ──────────────────────────────────────────────────────

/-- Commutativity of binary combine. -/
theorem combine_comm (a b : RollMod) :
    RollMod.combine a b = RollMod.combine b a := by
  cases a <;> cases b <;> rfl

/-- **Refutation of associativity.**
    `combine` is a commutative, idempotent magma — but NOT a semigroup.
    The witness `(disadv, adv, adv)` distinguishes left- and right-grouping:
    LHS = `(disadv ⊕ adv) ⊕ adv = normal ⊕ adv = adv`,
    RHS = `disadv ⊕ (adv ⊕ adv) = disadv ⊕ adv = normal`. -/
theorem combine_not_assoc :
    ¬ (∀ a b c : RollMod,
        RollMod.combine (RollMod.combine a b) c =
        RollMod.combine a (RollMod.combine b c)) := by
  intro h
  have := h .disadvantage .advantage .advantage
  simp [RollMod.combine] at this

/-- Normal is the identity element. -/
theorem combine_normal_left (a : RollMod) :
    RollMod.combine .normal a = a := by cases a <;> rfl

theorem combine_normal_right (a : RollMod) :
    RollMod.combine a .normal = a := by cases a <;> rfl

/-- Idempotency: advantage + advantage = advantage. -/
theorem adv_idempotent :
    RollMod.combine .advantage .advantage = .advantage := by rfl

theorem disadv_idempotent :
    RollMod.combine .disadvantage .disadvantage = .disadvantage := by rfl

/-- Annihilation: advantage + disadvantage = normal. -/
theorem adv_disadv_annihilate :
    RollMod.combine .advantage .disadvantage = .normal := by rfl

-- ── The three-source summary lemma ──────────────────────────────────────

/-- Any list of modifiers can be classified by whether it contains at
    least one advantage, at least one disadvantage, or neither. -/
def classify (ms : List RollMod) : RollMod :=
  let hasAdv := ms.any (· == .advantage)
  let hasDis := ms.any (· == .disadvantage)
  match hasAdv, hasDis with
  | true, true   => .normal
  | true, false  => .advantage
  | false, true  => .disadvantage
  | false, false => .normal

/-- Classification matches resolve for singleton lists. -/
theorem classify_singleton (m : RollMod) :
    classify [m] = m := by
  cases m <;> native_decide

/-- Classification matches resolve for all pair combinations. -/
theorem classify_pair (a b : RollMod) :
    classify [a, b] = RollMod.combine a b := by
  cases a <;> cases b <;> native_decide

-- ── d20 probability impact ──────────────────────────────────────────────

/-- P(d20 ≥ target) with advantage, out of 400. -/
def probAdvantage400 (target : Nat) : Nat :=
  if target ≤ 1 then 400
  else if target > 20 then 0
  else 400 - (target - 1) * (target - 1)  -- 1 - ((t-1)/20)^2

/-- P(d20 ≥ target) with disadvantage, out of 400. -/
def probDisadvantage400 (target : Nat) : Nat :=
  if target ≤ 1 then 400
  else if target > 20 then 0
  else (21 - target) * (21 - target)  -- ((21-t)/20)^2

/-- P(d20 ≥ target) with normal roll, out of 20. -/
def probNormal20 (target : Nat) : Nat :=
  if target ≤ 1 then 20
  else if target > 20 then 0
  else 21 - target

/-- Advantage on a DC 11 check (need ≥ 11): P = 1 - (10/20)^2 = 75%. -/
theorem adv_dc11 : probAdvantage400 11 = 300 := by native_decide

/-- Disadvantage on DC 11: P = (10/20)^2 = 25%. -/
theorem disadv_dc11 : probDisadvantage400 11 = 100 := by native_decide

/-- Normal DC 11: P = 10/20 = 50%. -/
theorem normal_dc11 : probNormal20 11 = 10 := by native_decide

/-- Advantage is always ≥ normal (×20 to compare).

    Proof strategy: discharge the bounded universal quantifier over the
    finite type `Fin 19` by `decide`, then transfer the result to an
    arbitrary `t ∈ [2..20]` via the canonical bijection
    `t ↦ ⟨t - 2, _⟩ : Fin 19`. -/
theorem advantage_ge_normal (t : Nat) (h1 : t ≥ 2) (h2 : t ≤ 20) :
    probAdvantage400 t ≥ probNormal20 t * 20 := by
  have hAll : ∀ k : Fin 19,
      probAdvantage400 (k.val + 2) ≥ probNormal20 (k.val + 2) * 20 := by
    decide
  have hbnd : t - 2 < 19 := by omega
  have heq  : t - 2 + 2 = t := by omega
  have key  := hAll ⟨t - 2, hbnd⟩
  rw [heq] at key
  exact key

/-- Concrete witnesses for `advantage_ge_normal` at boundary checks. -/
theorem advantage_ge_normal_dc11 :
    probAdvantage400 11 ≥ probNormal20 11 * 20 := by native_decide
theorem advantage_ge_normal_dc15 :
    probAdvantage400 15 ≥ probNormal20 15 * 20 := by native_decide
theorem advantage_ge_normal_dc20 :
    probAdvantage400 20 ≥ probNormal20 20 * 20 := by native_decide

/-! ## Open problem (P14a)

Prove that the expected value of `advantage(d20) = 13.825` (×1000 = 13825)
and `disadvantage(d20) = 7.175` (×1000 = 7175).  This requires summing
`max(d1,d2)` over all 400 (d1,d2) pairs.
-/

end VALOR.Scenarios.P14
