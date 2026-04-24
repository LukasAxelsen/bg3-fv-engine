# VALOR `v0.1-alpha`

[![CI](https://github.com/LukasAxelsen/bg3-fv-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/LukasAxelsen/bg3-fv-engine/actions)
[![Lean 4](https://img.shields.io/badge/Lean-4.29.1-blueviolet)](https://leanprover.github.io)

**Verified Automated Loop for Oracle-driven Rule-checking**
(Verificeret, automatiseret løkke til orakel-drevet regelkontrol)

[English](README.md) | [中文](README_zh.md) | [Dansk](README_da.md)

> Denne danske udgave er synkroniseret med [den engelske README](README.md) op til `v0.1-alpha`.
> Projektpolitik: den engelske udgave er den primære; den kinesiske og danske
> udgave opdateres kun ved eksplicit anmodning.

En neuro-symbolsk lukket-løkke-ramme til formel verifikation af kampmekanikker i computerspil, instantieret på Baldur's Gate 3.  `v0.1-alpha` leverer:

- **en verificeret Lean 4-kerne** (`lake build` er grøn — nul `error`, nul advarsler, nul `sorry` i standard­målet);
- **en Python-datapipeline** der crawler [bg3.wiki](https://bg3.wiki) ind i en typestærk lokal database (55 enhedstests);
- **en Lean ↔ Lua-bro** der oversætter Lean-modeksempler til testscripts som kan køre i spillet;
- **et oracle i spillet** udformet som en BG3 Script Extender-mod;
- **ét fuldt mekaniseret forskningsscenarie** (P14, advantage/disadvantage-algebra) med en ikke-triviel åben-vs-lukket algebraisk indsigt: `combine` er kommutativ, men **ikke** associativ — modbevist i Lean.

Yderligere 26 scenarie­udkast (P6–P13, P15–P32) findes under `Scenarios_wip/` og er sporet som v0.2-arbejde.  Se afsnittet [`v0.1`-omfang](#v01-omfang) nedenfor for en eksplicit, maskinkontrollerbar liste over hver eneste påstand.

Arkitekturen er inspireret af [`sts_lean`](https://github.com/collinzrj/sts_lean) (verifikation af uendelige kombinationer i Slay the Spire) og af CEGAR-mønstret (Clarke et al., 2000), tilpasset et spil med dybere og rigere regelflader.

---

## Hurtig start (verificerer hele projektet på <60 s)

```bash
git clone https://github.com/LukasAxelsen/bg3-fv-engine.git
cd bg3-fv-engine

# Python-side: 55 enhedstests af data- og brolagene.
python3 -m pip install -r requirements.txt
python3 -m pytest tests/ -q                # ⇒ 55 passed in 0.04s

# Lean-side: bevisførers verifikation af kernen.
# Kræver elan: https://github.com/leanprover/elan
cd src/2_fv_core
lake update                                # engangs, genererer lake-manifest.json
lake build                                 # ⇒ Build completed successfully (8 jobs).
```

Hvis begge kommandoer rapporterer succes, er hver eneste påstand i [`v0.1`-omfang](#v01-omfang)-afsnittet nedenfor nu maskinkontrolleret på din maskine.

---

## Arkitektur

```
 wiki-tekst ──crawler.py──▶ SQLite-DB ──llm_to_lean.py──▶ Lean 4-aksiomer
                                                              │
       ┌──────────────────────────────────────────────────────┘
       ▼
 Lean 4-kerne ──lake build──▶ bevis / modeksempel
       │
       ▼
 lua_generator.py ──▶ BG3 Script Extender-mod ──▶ kamplog
       │
       ▼
 log_analyzer.py ──▶ divergens­rapport ──▶ LLM-korrektion ──▶ ny runde
```

Den CEGAR-agtige løkke itererer indtil den formelle model og spillets motor stemmer overens.  Lean-kernen i `v0.1-alpha` kører ende-til-ende uden hverken LLM eller et kørende spil; LLM- og oracle-trinnene er til stede som funktionsdygtige stubbe og som integrationspunkter for v0.2.

---

## `v0.1`-omfang

Dette er den udtømmende, maskinkontrollerbare liste over hvad `lake build` beviser i denne udgivelse.  Ingen påstand uden for denne tabel er erklæret verificeret.

### Fundament (`Core/`, `Axioms/`, `Proofs/`)

| Fil                        | Sætning / definition                | Hvad den siger                                                                            | Taktik                     |
| -------------------------- | ----------------------------------- | ----------------------------------------------------------------------------------------- | -------------------------- |
| `Core/Types.lean`          | `Entity`, `GameState`, `Event`, …   | Typeret ontologi for BG3-kamp (entiteter, skade, tilstande, handlinger).                   | (definitioner, derivede).  |
| `Core/Engine.lean`         | `step : GameState → Event → Option` | Total small-step-overgangsfunktion; ikke-rekursiv efter at `stepEndTurn` er trukket ud.    | (definitioner).            |
| `Axioms/BG3Rules.lean`     | `drs_damage_scaling`                | DRS-skadesformlen kommuterer: `(n+1)·r + b = b + r·(n+1)` over `Int`.                      | `Int.mul_comm`             |
| `Axioms/BG3Rules.lean`     | `reaction_chain_bounded`            | At markere en entitet som "har reageret" forøger strengt `reactionsUsed`.                  | `simp`                     |
| `Axioms/BG3Rules.lean`     | `action_economy_bounded`            | `∀ flags, maxAttacksPerTurn flags ≤ 8` (universelt).                                        | `cases × 6`                |
| `Axioms/BG3Rules.lean`     | `overwrite_replaces`                | Efter `addCondition` med `Overwrite` er der ≤ 1 tilstand med samme tag.                    | `simp`                     |
| `Axioms/BG3Rules.lean`     | `ignore_preserves_existing`         | `addCondition` med `Ignore` er identitet, når tag'et allerede er til stede.                 | `simp`                     |
| `Proofs/Exploits.lean`     | `drs_amplifies_damage`              | Det konkrete DRS-exploitscenarie giver strengt mere skade end sin variant uden DRS.        | `native_decide`            |
| `Proofs/Exploits.lean`     | `reaction_chain_terminates`         | Når en entitet har reageret, kan den ikke længere reagere.                                  | `native_decide`            |
| `Proofs/Exploits.lean`     | `max_attacks_is_8`                  | All-feature-build'en rammer præcis den analytiske 8-angrebs grænse.                         | `native_decide`            |
| `Proofs/Exploits.lean`     | `max_attacks_honour_is_7`           | Samme build er begrænset til 7 i Honour Mode.                                               | `native_decide`            |
| `Proofs/Termination.lean`  | `reaction_decreases_fuel`           | Det velfunderede mål `entities.length - reactionsUsed.length` aftager strengt.              | `simp` + `omega`           |
| `Proofs/Termination.lean`  | `max_chain_length`                  | Initialt brændstof er lig med `entities.length`.                                            | `simp`                     |
| `Proofs/Termination.lean`  | `pass_turn_always_valid`            | `step gs (.passTurn e)` er `some _` så længe `e` findes i `gs` (liveness, universelt).      | `cases` på `getEntity`     |
| `Proofs/Termination.lean`  | `tick_preserves_length`             | End-of-turn tilstands­tikning forlænger aldrig tilstandslisten.                              | `List.length_filterMap_le` |

### Scenarie P14 — Advantage/Disadvantage-algebra (`Scenarios/P14_*.lean`)

| Sætning                                    | Hvad den siger                                                                                                                          | Taktik                     |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| `combine_comm`                             | Den binære `combine` er kommutativ.                                                                                                      | `cases × 2; rfl`           |
| `combine_normal_left/right`                | `normal` er tosidet identitet for `combine`.                                                                                             | `cases; rfl`               |
| `adv_idempotent`, `disadv_idempotent`      | Idempotens af `advantage` og `disadvantage` under `combine`.                                                                             | `rfl`                      |
| `adv_disadv_annihilate`                    | `combine advantage disadvantage = normal`.                                                                                              | `rfl`                      |
| **`combine_not_assoc`**                    | **Modbevis.** `combine` er *ikke* associativ; eksplicit vidne `(disadv, adv, adv)`.                                                      | `simp` på vidnet           |
| `classify_singleton`, `classify_pair`      | "Klassificér-så-resolv"-operatoren stemmer overens med `combine` på lister af længde ≤ 2.                                                  | `cases × n; native_decide` |
| `adv_dc11`, `disadv_dc11`, `normal_dc11`   | Lukkede sandsynlighedsudtryk (×400 / ×20) for DC 11-tjek.                                                                                 | `native_decide`            |
| **`advantage_ge_normal`**                  | **Universelt.** `∀ t ∈ [2..20], probAdvantage400 t ≥ probNormal20 t · 20`. Begrænset `Fin 19` afgøres af `decide` og løftes til `Nat`.    | `decide` + `omega`         |
| `advantage_ge_normal_dc{11,15,20}`         | Konkrete vidner for det universelle udsagn ved DC-grænserne.                                                                              | `native_decide`            |

**Akademisk fund (P14):** filens tidligere udkast påstod `combine_assoc` og kaldte strukturen en *kommutativ idempotent monoid*.  Da beviset blev mekaniseret i Lean, dukkede et modeksempel op, så strukturen er nu klassificeret som en **kommutativ, ikke-associativ, annihilerende magma** — strengt svagere end Ginsbergs (1988) tre-elementbilattice langs associativitets­aksen.  Modbeviset er nu i sig selv en sætning (`combine_not_assoc`), og den ægte rækkefølge- og grupperingsuafhængige multi-kilde-operator er `classify`, ikke `resolve`.  Det er præcis denne form for korrektion som lukket-løkke formel verifikation skal bringe op til overfladen.

### Hvad **ikke** er verificeret i `v0.1-alpha`

- De 26 scenarie­udkast `P6–P13, P15–P32` (nu under `Scenarios_wip/`).  De indeholder pladsholder­sætninger der er ældre end Lean 4.29's `List`-API-omdøbning og andre kerneændringer; mange bruger forældede taktikker eller postulerer numerisk forkerte værdier som `native_decide` afviser.  Hvert af dem er et v0.2-arbejdspunkt.
- De seks regel-aksiomer i `Axioms/BG3Rules.lean` (`hellish_rebuke_trigger`, `concentration_uniqueness`, `haste_self_cast_bug`, `fireball_damage`, `counterspell_uses_intelligence`, `hex_crit_bug`).  Disse er **antagelser** om BG3's motor; verifikations­pipelinen er ansvarlig for dem, ikke kernen.  De optræder eksplicit via `#print axioms` i ethvert teorem der afhænger af dem.

---

## Soundhed, TCB og kløften mellem model og spil

Hvert eneste `theorem` i standardmålet er et bevis­term der er typecheck'et af Lean 4-kernen.  `native_decide` er **udtømmende endelig-domæne modelkontrol** med et certifikat som kernen selv verificerer — ikke stikprøver.

**Trusted Computing Base.** Kør `#print axioms <theorem>` i en hvilken som helst fil for at opregne de aksiomer et bevis hviler på.  For den verificerede kerne er aksiomsættet:

| Aksiom                                              | Kilde                  | Bemærkninger                                       |
| --------------------------------------------------- | ---------------------- | -------------------------------------------------- |
| `propext`                                           | Lean 4-kerne           | Propositionel ekstensionalitet                     |
| `Quot.sound`                                        | Lean 4-kerne           | Kvotient-soundhed                                  |
| `Classical.choice`                                  | Lean 4-kerne           | Bruges af `simp`/`decide`-infrastrukturen          |
| `Lean.ofReduceBool`                                 | `native_decide`        | Stoler på kompileret reduktion; samme TCB som Mathlib |
| (de seks BG3-aksiomer i `Axioms/BG3Rules.lean`)     | spilmotor-antagelse    | Vises eksplicit; tjekkes i oracle-trinnet          |

**Kløften mellem model og spil.** Lean-modellen koder reglerne fra [bg3.wiki](https://bg3.wiki), som selv er en community-reverse-engineering af spilbinæren.  CEGAR-løkken er det mekanisme der lukker kløften: når oraklet i spillet observerer en divergens fra modellen, fødes divergensen ind i LLM-trinnet som en korrektion.  I `v0.1-alpha` kører løkken ende-til-ende på syntetiske logs (se `eval/run_feedback_loop.py`); i v0.2 kobles den på et kørende spil.

---

## Selv­verifikation i spillet (P14)

Scenariet `Scenarios/P14_AdvantageAlgebra.lean` beviser blandt andet:

> `adv_dc11`: med advantage på et DC 11 d20-tjek er sandsynligheden for succes præcis `300/400 = 75 %`.

Sådan verificerer du dette empirisk inde i selve spillet:

```
Trin 1.  Installér BG3 Script Extender (https://github.com/Norbyte/bg3se).

Trin 2.  Kopier VALOR-mod'en til SE's Lua-bibliotek:
           cp src/4_ingame_oracle/Mods/VALOR_Injector/*.lua "<BG3_SE_Lua_Dir>/"
           mkdir -p "<BG3_SE_Lua_Dir>/VALOR_Scripts"
           mkdir -p "<BG3_SE_Lua_Dir>/VALOR_Logs"

         Platform­specifik <BG3_SE_Lua_Dir>:
           Linux:    ~/.local/share/Larian Studios/Baldur's Gate 3/Script Extender/Lua/
           Windows:  %LOCALAPPDATA%/Larian Studios/Baldur's Gate 3/Script Extender/Lua/
           macOS:    ~/Library/Application Support/Larian Studios/Baldur's Gate 3/Script Extender/Lua/

Trin 3.  Start BG3, indlæs en hvilken som helst gem-fil, åbn SE-konsollen
         (standardgenvej: F10).  Forventet output:
           "[VALOR] Session loaded, polling VALOR_Scripts/"

Trin 4.  Generér testskriptet for P14 (1000 forsøg ved DC 11, advantage):
           python3 -m src.3_engine_bridge.lua_generator \
             --scenario p14_adv_dc11 --trials 1000 \
             --out "<BG3_SE_Lua_Dir>/VALOR_Scripts/p14.lua"

Trin 5.  I spillet: indlæs en hvilken som helst kampencounter, så motoren
         er "i live".  Mod'en opdager det nye script, kører det og skriver
         en JSON-log:
           "<BG3_SE_Lua_Dir>/VALOR_Logs/p14.json"

Trin 6.  Sammenlign med teorien:
           python3 -m src.3_engine_bridge.log_analyzer \
             --scenario p14_adv_dc11 \
             --log    "<BG3_SE_Lua_Dir>/VALOR_Logs/p14.json" \
             --expect 0.75 --tolerance 0.04
         Forventet output: "AGREE: observed 0.74 ± 0.014, theoretical 0.75".
```

Hvis sammenligningen er uden for tolerancen, er det en *divergens*, og det er inputtet til næste CEGAR-runde.

---

## Repository-struktur

```
src/
  1_auto_formalizer/     Python: wiki-crawler, parser, SQLite-DB, LLM-stub
  2_fv_core/
    lean-toolchain       Pinnet: leanprover/lean4:v4.29.1
    lakefile.lean        Build-manifest (standardmål = verificeret kerne)
    Core/                Lean 4 spil-ontologi + tilstandsmaskine
    Axioms/              Formaliserede BG3-regler (P1–P5)
    Proofs/              Termineringsbeviser + exploit-beviser
    Scenarios/           v0.1 verificerede scenarier (P14)
    Scenarios_wip/       v0.2-udkast (P6–P13, P15–P32; ikke i standardmålet)
  3_engine_bridge/       Python: Lean-output → Lua-scripts → loganalyse
  4_ingame_oracle/       Lua: BG3 Script Extender-mod
eval/                    Feedback-løkke-orkestrator + metrik-indsamling
tests/                   55 pytest-tests (modeller, parser, DB, bro)
dataset/                 Rå wiki-dumps + manuelle annoteringsbenchmarks
```

## Tilføj et nyt scenarie

Opret `src/2_fv_core/Scenarios/P33_YourProblem.lean`:

```lean
namespace VALOR.Scenarios.P33

def myMechanic (x : Nat) : Nat := x * x

theorem my_property : myMechanic 7 = 49 := by native_decide

end VALOR.Scenarios.P33
```

Tilføj `` `Scenarios.P33_YourProblem `` til `roots`-listen i standardmålet `lean_lib VALOR` i `src/2_fv_core/lakefile.lean`, og kør derefter `lake build`.  Ingen andre filer skal ændres.

## Referencer

- Clarke, Grumberg, Jha, Lu & Veith (2000). *Counterexample-Guided Abstraction Refinement.* CAV.
- de Moura & Ullrich (2021). *The Lean 4 Theorem Prover and Programming Language.* CADE.
- Ginsberg (1988). *Multivalued Logics: A Uniform Approach to Inference in Artificial Intelligence.* Computational Intelligence.
- [`sts_lean`](https://github.com/collinzrj/sts_lean) — Verifikation af uendelige kombinationer i Slay the Spire i Lean 4.
- [bg3.wiki](https://bg3.wiki) — Community-wiki, eneste datakilde.

## Licens

MIT
