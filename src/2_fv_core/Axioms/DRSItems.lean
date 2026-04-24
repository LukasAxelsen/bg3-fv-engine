import Core.Types

/-!
# DRSItems.lean — DS / DR / DRS catalogue ingested from bg3.wiki

**Auto-generated** by `src/1_auto_formalizer/drs_lean_export.py`
from `dataset/drs_items_seed.json`.  Do not edit by hand; run the
exporter and commit the regenerated file.  CI fails if this file
drifts from the JSON seed.

Source URL: `https://bg3.wiki/wiki/Damage_Mechanics`
Source section: `DRS effects`
Extraction date: `2026-04-25`

## Why this file exists

The bridge needs a *machine-checkable* enumeration of every Damage
Source / Damage Rider / DRS effect documented on bg3.wiki so that
exploit-search theorems (`Proofs/Exploits.lean`) can be parameterised
over the *real* item set rather than a hand-picked example.  The
Honour-mode demotion flag captures the documented Patch 5 behaviour
where most DRS effects are downgraded to plain DRs.
-/

namespace VALOR.DRSItems

open VALOR

/-- Three-tier classification used by bg3.wiki/wiki/Damage_Mechanics. -/
inductive LayerKind where
  | ds   -- Damage Source (acts on its own)
  | dr   -- Damage Rider (only fires alongside a Source)
  | drs  -- Damage Rider treated as a Source (re-attracts every Rider)
  deriving DecidableEq, Repr

/-- One catalogued layer entry. `riderDice` and `damageType` are
    optional because a few items only document a flat damage value or
    a non-numeric mechanic. -/
structure Item where
  name                : String
  layerKind           : LayerKind
  riderDice           : Option DiceExpr
  damageType          : Option DamageType
  honourDemotesToDR   : Bool
  sourceCategory      : String
  deriving Repr

/-- Curated list ingested from `dataset/drs_items_seed.json`. -/
def all : List Item := [
  { name              := "Lightning Jabber (thrown bonus)"
    layerKind         := .drs
    riderDice         := some ⟨1, 4, 0⟩
    damageType        := some .lightning
    honourDemotesToDR := true
    sourceCategory    := "weapon" },
  { name              := "Arrow of Acid (rider)"
    layerKind         := .drs
    riderDice         := some ⟨2, 4, 0⟩
    damageType        := some .acid
    honourDemotesToDR := true
    sourceCategory    := "consumable" },
  { name              := "Arrow of Fire (rider)"
    layerKind         := .drs
    riderDice         := some ⟨2, 4, 0⟩
    damageType        := some .fire
    honourDemotesToDR := true
    sourceCategory    := "consumable" },
  { name              := "Arrow of Ice (rider)"
    layerKind         := .drs
    riderDice         := some ⟨2, 4, 0⟩
    damageType        := some .cold
    honourDemotesToDR := true
    sourceCategory    := "consumable" },
  { name              := "Arrow of Lightning (rider)"
    layerKind         := .drs
    riderDice         := some ⟨2, 4, 0⟩
    damageType        := some .lightning
    honourDemotesToDR := true
    sourceCategory    := "consumable" },
  { name              := "Sword of Life Stealing (crit)"
    layerKind         := .drs
    riderDice         := none
    damageType        := some .necrotic
    honourDemotesToDR := true
    sourceCategory    := "weapon" },
  { name              := "Craterflesh Gloves: Craterous Wounds (crit)"
    layerKind         := .drs
    riderDice         := some ⟨1, 6, 0⟩
    damageType        := some .force
    honourDemotesToDR := true
    sourceCategory    := "armour" },
  { name              := "Crimson Mischief: Redvein Savagery"
    layerKind         := .drs
    riderDice         := none
    damageType        := some .piercing
    honourDemotesToDR := true
    sourceCategory    := "weapon" },
  { name              := "Render of Mind and Body: Psychic Steel Virtuoso"
    layerKind         := .drs
    riderDice         := some ⟨1, 8, 0⟩
    damageType        := some .psychic
    honourDemotesToDR := true
    sourceCategory    := "weapon" },
  { name              := "Rat Bat (unnamed ability)"
    layerKind         := .drs
    riderDice         := some ⟨1, 6, 0⟩
    damageType        := some .piercing
    honourDemotesToDR := true
    sourceCategory    := "weapon" },
  { name              := "Punch-Drunk Bastard: Tippler's Rage"
    layerKind         := .drs
    riderDice         := some ⟨1, 4, 0⟩
    damageType        := some .thunder
    honourDemotesToDR := true
    sourceCategory    := "weapon" },
  { name              := "Nyrulna: Zephyr Connection (thrown blast)"
    layerKind         := .drs
    riderDice         := some ⟨3, 4, 0⟩
    damageType        := some .thunder
    honourDemotesToDR := true
    sourceCategory    := "weapon" },
  { name              := "Hex (Warlock spell rider)"
    layerKind         := .dr
    riderDice         := some ⟨1, 6, 0⟩
    damageType        := some .necrotic
    honourDemotesToDR := false
    sourceCategory    := "spell" },
  { name              := "Ring of Flinging (rider)"
    layerKind         := .dr
    riderDice         := some ⟨1, 4, 0⟩
    damageType        := some .piercing
    honourDemotesToDR := false
    sourceCategory    := "ring" }
]

/-- Subset by classification. -/
def byKind (k : LayerKind) : List Item :=
  all.filter (fun i => decide (i.layerKind = k))

def damageSources    : List Item := byKind .ds
def damageRiders     : List Item := byKind .dr
def damageRiderSrcs  : List Item := byKind .drs

/-- Sum of worst-case rider damage across a list of items. -/
def totalWorstCase (items : List Item) : Nat :=
  items.foldl (fun acc i =>
    match i.riderDice with
    | some d => acc + d.count * d.sides + d.bonus.toNat
    | none   => acc) 0

/-- The full catalogue contains at least one DRS entry. -/
theorem catalogue_has_drs : 0 < damageRiderSrcs.length := by
  unfold damageRiderSrcs byKind all
  decide

/-- Honour mode demotes every catalogued DRS item to a plain DR — a
    machine-checkable restatement of the wiki's documented Patch 5
    behaviour. -/
theorem all_drs_demoted_in_honour :
    ∀ i ∈ damageRiderSrcs, i.honourDemotesToDR = true := by
  unfold damageRiderSrcs byKind all
  decide

end VALOR.DRSItems
