# VALOR `v0.1-alpha`

**Verified Automated Loop for Oracle-driven Rule-checking**

[English](README.md) | [中文](README_zh.md) | [Dansk](README_da.md)

Formel verifikation af Baldur's Gate 3-kampmekanikker i Lean 4. 27 selvstændige scenarier, der hver koder en reel spilmekanik som en afgørbar proposition og beviser (eller modbeviser) den via Lean 4-kernen.

Inspireret af [sts_lean](https://github.com/collinzrj/sts_lean). Hvor det projekt beviser uendelige kombinationer i Slay the Spire, beviser VALOR skadesgrænser, ressourceinvarianter, termineringsgarantier og optimale strategier i BG3.

## Hurtig start

```bash
git clone https://github.com/LukasAxelsen/bg3-fv-engine.git && cd bg3-fv-engine
python3 -m pip install -r requirements.txt   # crawler + tests
python3 -m pytest tests/ -v                  # 23 tests, <1s

# Lean 4-verifikation (kræver elan: https://github.com/leanprover/elan)
cd src/2_fv_core && lake build               # typetjekker alle 27 scenarier
```

## Arkitektur

```
 Wiki-tekst ──crawler.py──▶ SQLite DB ──llm_to_lean.py──▶ Lean 4-aksiomer
                                                              │
       ┌──────────────────────────────────────────────────────┘
       ▼
 Lean 4-kerne ──lake build──▶ bevis / modeksempel
       │
       ▼
 lua_generator.py ──▶ BG3 Script Extender-mod ──▶ kamplog
       │
       ▼
 log_analyzer.py ──▶ afvigelsesrapport ──▶ LLM-korrektion ──▶ gentag
```

Løkken (CEGAR-stil, Clarke et al. 2000) itererer indtil den formelle model og spilmotoren er enige. Lean-scenarierne nedenfor fungerer selvstændigt — ingen LLM eller spil påkrævet.

---

## Hvad vi beviser

27 scenarier fordelt på 7 beviskategorier. Alle sætninger markeret med ✓ er maskintjekket af Lean 4-kernen (se [Pålidelighed](#pålidelighed) for hvad dette indebærer). Åbne problemer er markeret med `sorry`.

### I. Terminering og velfunderethed

*Kæder af udløste spileffekter standser altid.*

| # | Scenarie | Nøglesætning | Metode |
|---|----------|--------------|--------|
| P2 | Reaktionskæde | `reaction_decreases_fuel` — kædelængde ≤ antal entiteter | velfunderet rekursion ✓ |
| P6 | Agathys + Hellish Rebuke-kaskade | `cascade_always_terminates` — for ENHVER startskade | `simp` ✓ (universel) |
| P9 | Overfladeelementinteraktioner | `rewriting_terminates` — ingen uendelig ild↔vand-løkke | termomskrivning ✓ |
| P19 | Våd + Lyn | `wet_consumed_after_aoe` — Våd er en lineær ressource, forbruges ved brug | Lyapunov-funktion ✓ |

### II. Ressourceinvarianter

*Spilressourcer overholder bevarelses-/monotonicitetsregler.*

| # | Scenarie | Nøglesætning | Resultat |
|---|----------|--------------|----------|
| P3 | Koncentration | `concentration_uniqueness` — højst én koncentrationsbesværgelse pr. entitet | aksiom |
| P5 | Statusstabling | `ignore_preserves_existing` — Ignore StackType er idempotent | ✓ |
| P7 | Multiklasse-besværgelsespladser | `esl_paladin5_sorc5 = 7` — præcis ESL for alle byggetyper | `native_decide` ✓ |
| P15 | Sorcery Point-økonomi | `round_trip_always_lossy` — hver SP↔plads-cyklus taber ≥1 SP | `interval_cases` ✓ (universel) |
| P29 | Coffeelock-udnyttelse | BG3: `two_cycles_capped` — begrænset til 4 ekstra pladser. 5e RAW: `ten_cycles_thirty_slots` — **ubegrænset** | ✓ / ✓ |

### III. Skadesgrænser og præcis beregning

*Præcise skadestal for specifikke builds, verificeret mod bg3.wiki.*

| # | Scenarie | Nøglesætning | Resultat |
|---|----------|--------------|----------|
| P1 | DRS-sammensætning | `drs_amplifies_damage` — DRS forårsager O((k+1)×m)-skalering | `native_decide` ✓ |
| P10 | DRS-skadesloft | `full_turn_damage` — maks. skade pr. tur for kastebygningen | `native_decide` ✓ |
| P12 | Smite + kritisk træffer | `crit_max = 127`, `crit_preserves_flat` — terninger fordobles, modifikatorer ikke | `native_decide` ✓ |
| P16 | Opcast-effektivitet | `two_base_beats_upcast` — 2× Fireball N3 > 1× Fireball N6 | `native_decide` ✓ |
| P17 | Dobbeltført vs tohåndet | `no_gwm_crossover_at_6` — præcis STR-mod hvor DW overhaler TH | `omega` ✓ (universel) |

### IV. Handlingsøkonomi-grænser

*Maksimalt antal handlinger/angreb en karakter kan udføre pr. tur.*

| # | Scenarie | Nøglesætning | Resultat |
|---|----------|--------------|----------|
| P4 | Handlingsøkonomi | `max_attacks_is_8`, `max_attacks_honour_is_7` | `native_decide` ✓ |
| P22 | Action Surge + Haste + Tyv | `global_max_is_11` — udtømmende søgning over alle 192 builds | `native_decide` ✓ |

### V. Sandsynlighed og stokastisk dominans

*d20-fordelinger, Markov-kæder, ordensstatistik.*

| # | Scenarie | Nøglesætning | Resultat |
|---|----------|--------------|----------|
| P8 | Koncentrationsredninger | `eb_dc_always_10` — Eldritch Blast DC bundlinjer ved 10 for alle d10-resultater | `omega` ✓ (universel) |
| P14 | Fordels-algebra | `combine_comm`, `combine_assoc`, `adv_idempotent` — 3-element monoid-love | `cases` ✓ (universel) |
| P18 | Karmiske terninger | `karmic_boost_over_standard` — træfrate stiger fra 50% til ~54,8% | Markov-kæde ✓ |
| P21 | Dødsredninger | `survival_less_than_half` — P(overlev) ≈ 46,7%, ikke 50% | absorberende kæde ✓ |
| P25 | Bardisk inspiration | `advantage_never_beats_d6_bi` — BI(d6) ≥ fordel for ALLE DC'er | udtømmende ✓ |
| P28 | Initiativ-førsteslå | `alert_quadruples_first_strike` — Alert: 9% → 36% alle-først (2v2) | ordensstatistik ✓ |

### VI. Spilteori og modstanderræsonnement

*Optimalt spil i strategiske interaktioner mellem castere/kombattanter.*

| # | Scenarie | Nøglesætning | Resultat |
|---|----------|--------------|----------|
| P11 | Counterspell-krig | `game_tree_finite` — dybde ≤ antal castere | `native_decide` ✓ |
| P23 | Tvillinget Haste + koncentrationsbrud | `break_round_2 = 0` — modstanderens break-even ved runde 2 | `native_decide` ✓ |
| P26 | Grapple/Shove-lås | `threshold_is_6` — +6 Atletik kræves for 50% 3-rundelås | `native_decide` ✓ |

### VII. Kombinatorisk optimering

*Build-valg, holdsammensætning, ressourceplanlægning — mange NP-hårde generelt, løst eksakt for BG3's små instansstørrelser.*

| # | Scenarie | Nøglesætning | Resultat |
|---|----------|--------------|----------|
| P13 | Sneak Attack-berettigelse | `eligible_ratio = 832` — 832/2048 tilstande tillader SA (40,6%) | 2¹¹ optælling ✓ |
| P20 | Holdsammensætning | `minimum_cover_size_is_3` — 3 klasser dækker alle 8 roller; 2 kan ikke | C(12,2) + C(12,3) ✓ |
| P24 | Hvileplanlægning | `smart_beats_greedy6` — grådig kort hvile-placering er suboptimal | modeksempel ✓ |
| P27 | Feat-valg | `greedy_suboptimal` — synergier gør grådig fejlagtig; GWM+PAM+Sentinel optimal | C(12,3) QUBO ✓ |
| P30 | Wild Magic Surge | `positive_expected_value`, `high_variance` — netto +EV men σ ≫ μ | statistik ✓ |
| P31 | Helbredelseseffektivitet | `healing_word_theorem` — HW > Cure Wounds for angribs-DPR ≥ 8 | `omega` ✓ (universel) |
| P32 | Multiklasse-dip | `rogue_dip_improves_fighter` — rene builds er suboptimale | udtømmende IP ✓ |

---

## Pålidelighed

Enhver `theorem` i dette repository er et bevisterm typetjekket af Lean 4-kernen — inklusive dem der bruger `native_decide`. Forskellen fra test er, at `native_decide` er **udtømmende modeltjek over endelige domæner** (certificeret af kernen), ikke stikprøvetagning.

### Trusted Computing Base (TCB)

Alle beviser reducerer til Lean 4-kernen plus disse aksiomer (verificerbare via `#print axioms`):

| Aksiom | Kilde | Bemærkninger |
|--------|-------|--------------|
| `propext` | Lean 4-kerne | Propositionel ekstensionalitet |
| `Quot.sound` | Lean 4-kerne | Kvotient-pålidelighed |
| `Classical.choice` | Lean 4-kerne | Bruges af `simp`-taktik |
| `Lean.ofReduceBool` | `native_decide` | Stoler på kompileret reduktion; samme TCB som mathlib |

Ingen scenarier i `Scenarios/` introducerer brugerdefinerede `axiom`-deklarationer. Aksiomerne i `Axioms/BG3Rules.lean` (P1–P5) er isolerede formaliseringsmål til LLM-pipelinen og importeres **ikke** af nogen scenariefil.

### Bevismetoder: hvad tæller som hvad

| Teknik | Hvad den beviser | Eksempel |
|--------|-----------------|----------|
| `native_decide` over optalt domæne | **Udtømmende modeltjek**: alle tilstande tjekket, bevisattest genereret | P13: alle 2048 boolske tilstande |
| `native_decide` på konkrete værdier | **Verificeret beregning**: specifik instans bekræftet | P12: `crit_max = 127` |
| `omega`, `simp`, `cases` | **Strukturelt bevis**: gælder for ALLE input (universelt kvantificeret) | P6: `cascade_always_terminates` |
| `sorry` | **Åbent problem**: formuleret men ikke bevist, tydeligt markeret | P7: `esl_le_total_level` |

Konkret: 11 af 27 scenarier indeholder mindst én universelt kvantificeret sætning bevist med strukturelle taktikker (ikke `native_decide`). De resterende bruger udtømmende optælling over endelige domæner, hvilket er en standard verificeret modeltjek-teknik.

### Modeltrofasthed

Lean-modellen koder regler fra [bg3.wiki](https://bg3.wiki), ikke spilbinæren. Dette skaber et potentielt gab:

| Lag | Hvad den stoler på | Hvordan gabet adresseres |
|-----|--------------------|--------------------------|
| Lean-model | bg3.wiki er korrekt | In-game-orakel validerer forudsigelser mod den rigtige spilmotor |
| bg3.wiki | Fællesskabs-reverse engineering | Krydsrefereret med spilfiler; wiki'en har >10.000 redaktører |
| In-game-orakel | BG3 Script Extender API | SE er standard modding-framework, bredt brugt af fællesskabet |

CEGAR-løkken er designet til iterativt at lukke dette gab: når oraklet afviger fra modellen, fødes afvigelsen tilbage som en korrektion. Den aktuelle `v0.1-alpha` leverer Lean-verifikationslaget; orakel-integrationen er funktionel men kræver manuel spilinteraktion.

---

## Sådan ser det ud i praksis

### 1. Verificering af sætninger (terminal)

```
$ cd src/2_fv_core && lake build
Building Scenarios.P13_SneakAttackSAT
Building Scenarios.P21_DeathSaveMarkov
Building Scenarios.P29_CoffeelockInfiniteSlots
...
Build completed successfully.     # alle sætninger typetjekket
```

### 2. In-game-verifikation (trin-for-trin)

**Eksempel**: P12 hævder at en Paladin 6 / Sorcerer 6 med Greatsword, niveau 4 Divine Smite, kritisk træffer mod Undead giver maksimalt 127 skade.

```
Trin 1.  Installér BG3 Script Extender (github.com/Norbyte/bg3se).

Trin 2.  Kopiér VALOR-modden til Script Extender-mappen:
           cp src/4_ingame_oracle/Mods/VALOR_Injector/*.lua "<BG3_SE_Lua_Sti>/"
         Tilføj til BootstrapServer.lua:
           Ext.Require("main")

Trin 3.  Start BG3. Indlæs et save. Åbn SE-konsollen (standard: F10).
         Du bør se: "[VALOR] Session loaded, polling VALOR_Scripts/"

Trin 4.  Genskab scenariet manuelt:
           a. Opret en Paladin 6 / Sorcerer 6-karakter (STR 20)
           b. Udstyr et Greatsword
           c. Find en Undead-fjende
           d. Gem spillet
           e. Angrib med Divine Smite (niveau 4-plads)
           f. Ved kritisk træffer: notér skadevisningen

Trin 5.  Sammenlign:
           Lean-forudsigelse: maks. 127 (4d6 våben + 12d8 smite + 7 fast)
           Spilvisning: bør vise ≤ 127 total skade
```

---

## Katalogstruktur

```
src/
  1_auto_formalizer/     Python: wiki-crawler, parser, SQLite DB, LLM-stub
  2_fv_core/
    Core/                Lean 4 spil-ontologi + tilstandsmaskine
    Axioms/              Formaliserede BG3-regler (P1–P5, isoleret)
    Proofs/              Terminerings- og exploit-beviser
    Scenarios/           Selvstændige scenarier P6–P32 (hovedbidrag)
    lakefile.lean        Build-manifest
  3_engine_bridge/       Python: Lean-output → Lua-scripts → loganalyse
  4_ingame_oracle/       Lua: BG3 Script Extender-mod
eval/                    Feedback-løkke-orkestrator + metrikindsamling
tests/                   23 pytest-tests (Python-lag)
dataset/                 Rå wiki-dumps + manuelt annoterede benchmarks
```

## Referencer

- Clarke et al. (2000). Counterexample-Guided Abstraction Refinement. *CAV*.
- de Moura & Ullrich (2021). The Lean 4 Theorem Prover. *CADE*.
- [sts_lean](https://github.com/collinzrj/sts_lean) — Slay the Spire uendelig-combo-verifikation i Lean 4.
- [bg3.wiki](https://bg3.wiki) — Fællesskabswiki, eneste datakilde.

## Licens

MIT

---

*Dette dokument er den arkiverede danske oversættelse af `v0.1-alpha`. Den engelske README.md er den primært opdaterede version.*
