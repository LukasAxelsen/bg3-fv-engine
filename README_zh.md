# VALOR `v0.1-alpha`

[![CI](https://github.com/LukasAxelsen/bg3-fv-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/LukasAxelsen/bg3-fv-engine/actions)
[![Lean 4](https://img.shields.io/badge/Lean-4.29.1-blueviolet)](https://leanprover.github.io)

**Verified Automated Loop for Oracle-driven Rule-checking**
（基于神谕反馈的电子游戏战斗机制形式化验证闭环框架）

[English](README.md) | [中文](README_zh.md) | [Dansk](README_da.md)

> 本中文版与 [英文 README](README.md) 同步至 `v0.1-alpha`。
> 项目策略：以英文版为主版本，中文 / 丹麦文版本仅在显式请求时同步。

一个面向电子游戏战斗机制的神经-符号闭环形式化验证框架，以《博德之门 3》为实例化对象。`v0.1-alpha` 提供：

- **一个已验证的 Lean 4 核心**（默认构建目标 `lake build` 全绿：零 `error`、零 warning、零 `sorry`）；
- **一条 Python 数据管道**：从 [bg3.wiki](https://bg3.wiki) 抓取并写入带类型的本地数据库（55 项单元测试）；
- **一座 Lean ↔ Lua 桥**：把 Lean 反例编译为可在游戏内执行的 Lua 测试脚本；
- **一个游戏内神谕（oracle）**：以 BG3 Script Extender mod 形式提供；
- **一个完整机械化的研究场景**（P14：优势 / 劣势代数），并在该场景中给出一项非平凡的代数结论——`combine` 满足交换律但**不**满足结合律（在 Lean 中以反例予以证伪）。

另有 26 份场景草稿（P6–P13、P15–P32）置于 `Scenarios_wip/`，作为 v0.2 工作项跟踪。下文 [`v0.1` 已验证范围](#v01-已验证范围) 一节给出了**逐条可机械验证**的清单。

整体架构受 [`sts_lean`](https://github.com/collinzrj/sts_lean)（《杀戮尖塔》无限连击的 Lean 4 验证）以及 CEGAR 框架（Clarke 等，2000）启发，并针对规则面更复杂的 BG3 进行调整。

---

## 快速开始（< 60 秒内验证整个项目）

```bash
git clone https://github.com/LukasAxelsen/bg3-fv-engine.git
cd bg3-fv-engine

# Python 端：数据层 + 桥层共 55 项单元测试。
python3 -m pip install -r requirements.txt
python3 -m pytest tests/ -q                # ⇒ 55 passed in 0.04s

# Lean 端：定理证明器对验证核心的完整检查。
# 需要先安装 elan: https://github.com/leanprover/elan
cd src/2_fv_core
lake update                                # 一次性，生成 lake-manifest.json
lake build                                 # ⇒ Build completed successfully (8 jobs).
```

若两条命令均输出成功，则下文 [`v0.1` 已验证范围](#v01-已验证范围) 中所列的每一条命题都已在你本地完成机械验证。

---

## 整体架构

```
 wiki 文本 ──crawler.py──▶ SQLite 数据库 ──llm_to_lean.py──▶ Lean 4 公理
                                                              │
       ┌──────────────────────────────────────────────────────┘
       ▼
 Lean 4 内核 ──lake build──▶ 证明 / 反例
       │
       ▼
 lua_generator.py ──▶ BG3 Script Extender mod ──▶ 战斗日志
       │
       ▼
 log_analyzer.py ──▶ 偏差报告 ──▶ LLM 修正 ──▶ 下一轮
```

CEGAR 风格的闭环不断迭代，直至形式模型与游戏引擎一致。`v0.1-alpha` 的 Lean 核心可独立、端到端运行，无需 LLM 或运行中的游戏；LLM 与神谕阶段以可工作的桩函数形式提供，并预留了 v0.2 的集成入口。

---

## `v0.1` 已验证范围

下表是本版本中 `lake build` 所证明命题的**完整、可机械验证**清单。任何不在本节中的论断都不视为已验证。

### 基础层（`Core/`、`Axioms/`、`Proofs/`）

| 文件                       | 定理 / 定义                          | 内容                                                                                       | 战术                       |
| -------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------ | -------------------------- |
| `Core/Types.lean`          | `Entity`、`GameState`、`Event`、…     | BG3 战斗的类型化本体（实体、伤害、状态、动作）。                                               | （定义 + 派生实例）。         |
| `Core/Engine.lean`         | `step : GameState → Event → Option`  | 全函数化的小步转移函数；通过抽出 `stepEndTurn` 后已是非递归的。                                  | （定义）。                  |
| `Axioms/BG3Rules.lean`     | `drs_damage_scaling`                 | DRS 伤害公式可交换：`(n+1)·r + b = b + r·(n+1)` （`Int` 上）。                                | `Int.mul_comm`             |
| `Axioms/BG3Rules.lean`     | `reaction_chain_bounded`             | 把一名实体标记为「已反应」严格扩展 `reactionsUsed`。                                            | `simp`                     |
| `Axioms/BG3Rules.lean`     | `action_economy_bounded`             | `∀ flags, maxAttacksPerTurn flags ≤ 8`（全称）。                                              | `cases × 6`                |
| `Axioms/BG3Rules.lean`     | `overwrite_replaces`                 | 以 `Overwrite` 调用 `addCondition` 后，同标签状态至多保留 1 条。                                | `simp`                     |
| `Axioms/BG3Rules.lean`     | `ignore_preserves_existing`          | 以 `Ignore` 调用 `addCondition`，若标签已存在则等同恒等。                                       | `simp`                     |
| `Proofs/Exploits.lean`     | `drs_amplifies_damage`               | 具体的 DRS 套路场景的伤害严格高于其去 DRS 版本。                                                | `native_decide`            |
| `Proofs/Exploits.lean`     | `reaction_chain_terminates`          | 一名实体反应过后，即不再具备反应资格。                                                          | `native_decide`            |
| `Proofs/Exploits.lean`     | `max_attacks_is_8`                   | 全特性 build 恰好达到分析上的 8 次攻击上界。                                                    | `native_decide`            |
| `Proofs/Exploits.lean`     | `max_attacks_honour_is_7`            | 同一 build 在 Honour 模式下被压至 7 次。                                                       | `native_decide`            |
| `Proofs/Termination.lean`  | `reaction_decreases_fuel`            | 良基测度 `entities.length - reactionsUsed.length` 在每次反应后严格下降。                         | `simp` + `omega`           |
| `Proofs/Termination.lean`  | `max_chain_length`                   | 初始燃料等于 `entities.length`。                                                              | `simp`                     |
| `Proofs/Termination.lean`  | `pass_turn_always_valid`             | 只要 `e` 存在于 `gs`，则 `step gs (.passTurn e)` 必为 `some _`（活性，全称）。                    | 对 `getEntity` 作 `cases`   |
| `Proofs/Termination.lean`  | `tick_preserves_length`              | 回合末状态计时不会拉长状态列表。                                                                | `List.length_filterMap_le` |

### 场景 P14：优势 / 劣势代数（`Scenarios/P14_*.lean`）

| 定理                                       | 内容                                                                                                                              | 战术                       |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| `combine_comm`                             | 二元 `combine` 满足交换律。                                                                                                          | `cases × 2; rfl`           |
| `combine_normal_left/right`                | `normal` 是 `combine` 的双侧单位元。                                                                                                 | `cases; rfl`               |
| `adv_idempotent`、`disadv_idempotent`       | `advantage`、`disadvantage` 在 `combine` 下幂等。                                                                                   | `rfl`                      |
| `adv_disadv_annihilate`                    | `combine advantage disadvantage = normal`。                                                                                       | `rfl`                      |
| **`combine_not_assoc`**                    | **反例式证伪。** `combine` *不* 满足结合律；显式见证 `(disadv, adv, adv)`。                                                            | 对见证作 `simp`             |
| `classify_singleton`、`classify_pair`       | 「分类后定型」算子在长度 ≤ 2 的列表上与 `combine` 一致。                                                                                 | `cases × n; native_decide` |
| `adv_dc11`、`disadv_dc11`、`normal_dc11`     | DC 11 检定下的闭式概率（×400 / ×20）。                                                                                                | `native_decide`            |
| **`advantage_ge_normal`**                  | **全称。** `∀ t ∈ [2..20], probAdvantage400 t ≥ probNormal20 t · 20`。在 `Fin 19` 上以 `decide` 化解后回升至 `Nat`。                  | `decide` + `omega`         |
| `advantage_ge_normal_dc{11,15,20}`         | 上述全称命题在边界 DC 上的具体见证。                                                                                                  | `native_decide`            |

**P14 中的学术发现**：原稿断言 `combine_assoc` 并把该结构称为「交换幂等幺半群」。在 Lean 中尝试机械化证明时直接得到反例，结构因此被改归为**带零元的、交换、非结合的 magma**——比 Ginsberg（1988）所述的三元 bilattice 在结合律一维上严格更弱。该反例本身现已成为定理 `combine_not_assoc`，而真正与顺序 / 分组无关的多源算子是 `classify`，而不是逐对 `resolve`。这正是闭环形式化验证应当浮现的修正。

### `v0.1-alpha` **未** 验证的部分

- 26 份场景草稿 `P6–P13、P15–P32`（现位于 `Scenarios_wip/`）。其中包含若干使用了已弃用接口（如 Lean 4.29 重命名后的 `List` API）或在 `native_decide` 下被判为假的占位定理，每一项均作为 v0.2 工作项跟踪。
- `Axioms/BG3Rules.lean` 中的六条规则公理（`hellish_rebuke_trigger`、`concentration_uniqueness`、`haste_self_cast_bug`、`fireball_damage`、`counterspell_uses_intelligence`、`hex_crit_bug`）：这些是**对 BG3 引擎行为的假设**，由验证管道中的神谕阶段负责，而非由内核负责。所有依赖它们的定理通过 `#print axioms` 都会显式列出这些公理。

---

## 可信性、TCB 与「模型–游戏」缺口

默认构建目标中的每一条 `theorem` 均为经过 Lean 4 内核类型检查的证明项。`native_decide` 是**有限域穷举模型检查**，结论附带内核可校验的证书，并非抽样。

**可信计算基（TCB）**：在任意文件中执行 `#print axioms <theorem>` 即可枚举该证明所依赖的全部公理。已验证核心的公理集合为：

| 公理                                            | 来源                       | 备注                                                |
| ----------------------------------------------- | -------------------------- | --------------------------------------------------- |
| `propext`                                       | Lean 4 核心                | 命题外延性                                           |
| `Quot.sound`                                    | Lean 4 核心                | 商类型可靠性                                         |
| `Classical.choice`                              | Lean 4 核心                | 由 `simp`/`decide` 基础设施使用                      |
| `Lean.ofReduceBool`                             | `native_decide`            | 信任已编译的归约；TCB 与 Mathlib 一致                |
| （`Axioms/BG3Rules.lean` 中六条 BG3 公理）        | 对游戏引擎的假设           | 显式列出；由神谕阶段负责对其加以校验                  |

**模型–游戏缺口**：Lean 模型对应 [bg3.wiki](https://bg3.wiki) 上的规则描述，而 wiki 本身是社区对游戏二进制的逆向工程。CEGAR 闭环正是用以收敛该缺口的机制——一旦游戏内神谕观察到与模型的偏差，该偏差便回灌至 LLM 阶段作为修正素材。在 `v0.1-alpha` 中，闭环以合成日志端到端运行（见 `eval/run_feedback_loop.py`），v0.2 将接入运行中的游戏。

---

## 游戏内自验证教程（P14）

`Scenarios/P14_AdvantageAlgebra.lean` 中除其他命题外证明了：

> `adv_dc11`：在 DC 11 的 d20 检定上拥有优势时，成功概率恰为 `300/400 = 75 %`。

下面给出在游戏内对该结论作经验验证的步骤。

```
步骤 1.  安装 BG3 Script Extender (https://github.com/Norbyte/bg3se)。

步骤 2.  把 VALOR mod 复制到 SE 的 Lua 目录：
           cp src/4_ingame_oracle/Mods/VALOR_Injector/*.lua "<BG3_SE_Lua_Dir>/"
           mkdir -p "<BG3_SE_Lua_Dir>/VALOR_Scripts"
           mkdir -p "<BG3_SE_Lua_Dir>/VALOR_Logs"

         各平台对应的 <BG3_SE_Lua_Dir>：
           Linux：   ~/.local/share/Larian Studios/Baldur's Gate 3/Script Extender/Lua/
           Windows： %LOCALAPPDATA%/Larian Studios/Baldur's Gate 3/Script Extender/Lua/
           macOS：   ~/Library/Application Support/Larian Studios/Baldur's Gate 3/Script Extender/Lua/

步骤 3.  启动 BG3，加载任意存档，打开 SE 控制台（默认快捷键：F10）。
         应当看到："[VALOR] Session loaded, polling VALOR_Scripts/"

步骤 4.  生成 P14 的测试脚本（DC 11、优势、1000 次重复）：
           python3 -m src.3_engine_bridge.lua_generator \
             --scenario p14_adv_dc11 --trials 1000 \
             --out "<BG3_SE_Lua_Dir>/VALOR_Scripts/p14.lua"

步骤 5.  在游戏内进入任意战斗（保证引擎处于「活跃」状态）。
         mod 会自动检测并执行该脚本，并写出 JSON 日志：
           "<BG3_SE_Lua_Dir>/VALOR_Logs/p14.json"

步骤 6.  与理论值比较：
           python3 -m src.3_engine_bridge.log_analyzer \
             --scenario p14_adv_dc11 \
             --log    "<BG3_SE_Lua_Dir>/VALOR_Logs/p14.json" \
             --expect 0.75 --tolerance 0.04
         期望输出："AGREE: observed 0.74 ± 0.014, theoretical 0.75"。
```

若比较结果在容忍区间外，则视为一次 *偏差*（divergence），即下一轮 CEGAR 的输入。

---

## 仓库结构

```
src/
  1_auto_formalizer/     Python：wiki 爬虫、解析器、SQLite 数据库、LLM 桩
  2_fv_core/
    lean-toolchain       已固定为：leanprover/lean4:v4.29.1
    lakefile.lean        构建清单（默认目标 = 已验证核心）
    Core/                Lean 4 游戏本体 + 状态机
    Axioms/              形式化的 BG3 规则（P1–P5）
    Proofs/              终止性 + 套路证明
    Scenarios/           v0.1 已验证场景（P14）
    Scenarios_wip/       v0.2 草稿（P6–P13、P15–P32；不在默认构建中）
  3_engine_bridge/       Python：Lean 输出 → Lua 脚本 → 日志分析
  4_ingame_oracle/       Lua：BG3 Script Extender mod
eval/                    反馈循环编排器 + 指标采集
tests/                   55 项 pytest（模型、解析器、数据库、桥层）
dataset/                 原始 wiki 转储 + 人工标注基准
```

## 添加新场景

新建 `src/2_fv_core/Scenarios/P33_YourProblem.lean`：

```lean
namespace VALOR.Scenarios.P33

def myMechanic (x : Nat) : Nat := x * x

theorem my_property : myMechanic 7 = 49 := by native_decide

end VALOR.Scenarios.P33
```

将 `` `Scenarios.P33_YourProblem `` 加入 `src/2_fv_core/lakefile.lean` 中默认目标 `lean_lib VALOR` 的 `roots` 列表，然后执行 `lake build`。无需改动其他文件。

## 参考文献

- Clarke、Grumberg、Jha、Lu 与 Veith（2000）。*Counterexample-Guided Abstraction Refinement.* CAV.
- de Moura 与 Ullrich（2021）。*The Lean 4 Theorem Prover and Programming Language.* CADE.
- Ginsberg（1988）。*Multivalued Logics: A Uniform Approach to Inference in Artificial Intelligence.* Computational Intelligence.
- [`sts_lean`](https://github.com/collinzrj/sts_lean) —— 《杀戮尖塔》无限连击的 Lean 4 验证。
- [bg3.wiki](https://bg3.wiki) —— 社区维护的 wiki，唯一数据来源。

## 许可证

MIT
