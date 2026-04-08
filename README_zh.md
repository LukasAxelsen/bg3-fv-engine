# VALOR `v0.1-alpha`

**Verified Automated Loop for Oracle-driven Rule-checking**

[English](README.md) | [中文](README_zh.md) | [Dansk](README_da.md)

基于 Lean 4 的《博德之门3》战斗机制形式化验证框架。27 个自包含场景，每个场景将一条真实游戏机制编码为可判定命题，并由 Lean 4 内核完成证明（或证伪）。

灵感来自 [sts_lean](https://github.com/collinzrj/sts_lean)。该项目证明《杀戮尖塔》中的无限连击，而 VALOR 证明《博德之门3》中的伤害上界、资源不变量、终止性保证与最优策略。

## 快速开始

```bash
git clone https://github.com/LukasAxelsen/bg3-fv-engine.git && cd bg3-fv-engine
python3 -m pip install -r requirements.txt   # 爬虫 + 测试依赖
python3 -m pytest tests/ -v                  # 23 个测试，<1秒

# Lean 4 验证（需要 elan：https://github.com/leanprover/elan）
cd src/2_fv_core && lake build               # 对全部 27 个场景进行类型检查
```

## 架构

```
 Wiki文本 ──crawler.py──▶ SQLite数据库 ──llm_to_lean.py──▶ Lean 4 公理
                                                              │
       ┌──────────────────────────────────────────────────────┘
       ▼
 Lean 4 内核 ──lake build──▶ 证明 / 反例
       │
       ▼
 lua_generator.py ──▶ BG3 Script Extender Mod ──▶ 战斗日志
       │
       ▼
 log_analyzer.py ──▶ 差异报告 ──▶ LLM修正 ──▶ 循环
```

该循环采用 CEGAR 风格（Clarke et al. 2000），迭代直至形式化模型与游戏引擎达成一致。以下 Lean 场景可独立运行——无需 LLM 或游戏本体。

---

## 证明内容

27 个场景，划分为 7 个证明类别。标记 ✓ 的定理均经 Lean 4 内核机器检查（关于其含义，参见[可靠性](#可靠性)一节）。标记 `sorry` 的为开放问题。

### I. 终止性与良基性

*游戏效果的触发链总是会停止。*

| # | 场景 | 关键定理 | 方法 |
|---|------|----------|------|
| P2 | 反应链 | `reaction_decreases_fuel` — 链长 ≤ 实体数量 | 良基递归 ✓ |
| P6 | 寒冰护甲 + 地狱斥责连锁 | `cascade_always_terminates` — 对任意初始伤害成立 | `simp` ✓（全称） |
| P9 | 地表元素交互 | `rewriting_terminates` — 不存在无限火↔水循环 | 项重写 ✓ |
| P19 | 潮湿 + 闪电 | `wet_consumed_after_aoe` — 潮湿是线性资源，使用即消耗 | Lyapunov 函数 ✓ |

### II. 资源不变量

*游戏资源服从守恒/单调性定律。*

| # | 场景 | 关键定理 | 结果 |
|---|------|----------|------|
| P3 | 专注 | `concentration_uniqueness` — 每个实体至多一个专注法术 | 公理 |
| P5 | 状态叠加 | `ignore_preserves_existing` — 忽略型叠加类型具幂等性 | ✓ |
| P7 | 多职业法术位 | `esl_paladin5_sorc5 = 7` — 所有构建类型的精确有效施法等级 | `native_decide` ✓ |
| P15 | 魔力点经济 | `round_trip_always_lossy` — 每次魔力点↔法术位往返损失 ≥1 | `interval_cases` ✓（全称） |
| P29 | Coffeelock 漏洞 | BG3：`two_cycles_capped` — 上限 4 个额外法术位。5e RAW：`ten_cycles_thirty_slots` — **无上限** | ✓ / ✓ |

### III. 伤害上界与精确计算

*特定构建下的精确伤害数值，依据 bg3.wiki 验证。*

| # | 场景 | 关键定理 | 结果 |
|---|------|----------|------|
| P1 | DRS 伤害组合 | `drs_amplifies_damage` — DRS 导致 O((k+1)×m) 缩放 | `native_decide` ✓ |
| P10 | DRS 伤害上限 | `full_turn_damage` — 投掷流单回合最大伤害 | `native_decide` ✓ |
| P12 | 神圣惩击 + 暴击 | `crit_max = 127`, `crit_preserves_flat` — 骰子翻倍，修正值不变 | `native_decide` ✓ |
| P16 | 升环效率 | `two_base_beats_upcast` — 2×火球术L3 > 1×火球术L6 | `native_decide` ✓ |
| P17 | 双持 vs 双手 | `no_gwm_crossover_at_6` — 双持在力量+6时反超双手 | `omega` ✓（全称） |

### IV. 行动经济上界

*单回合内角色最多可执行的攻击/动作次数。*

| # | 场景 | 关键定理 | 结果 |
|---|------|----------|------|
| P4 | 行动经济 | `max_attacks_is_8`, `max_attacks_honour_is_7` | `native_decide` ✓ |
| P22 | 行动如潮 + 加速术 + 盗贼 | `global_max_is_11` — 穷举全部 192 种构建 | `native_decide` ✓ |

### V. 概率与随机占优

*d20 骰面分布、马尔可夫链、次序统计量。*

| # | 场景 | 关键定理 | 结果 |
|---|------|----------|------|
| P8 | 专注豁免 | `eb_dc_always_10` — 魔能爆发 DC 对所有 d10 结果均为 10 | `omega` ✓（全称） |
| P14 | 优势/劣势代数 | `combine_comm`, `combine_assoc`, `adv_idempotent` — 三元素幺半群定律 | `cases` ✓（全称） |
| P18 | 因果骰 | `karmic_boost_over_standard` — 命中率从 50% 提升至 ~54.8% | 马尔可夫链 ✓ |
| P21 | 死亡豁免 | `survival_less_than_half` — 存活概率 ≈ 46.7%，而非 50% | 吸收链 ✓ |
| P25 | 激励骰 | `advantage_never_beats_d6_bi` — BI(d6) ≥ 优势，对所有 DC 成立 | 穷举 ✓ |
| P28 | 先攻首杀 | `alert_quadruples_first_strike` — 警觉专长：9% → 36%（2v2） | 次序统计 ✓ |

### VI. 博弈论与对抗推理

*施法者/战斗者间策略交互中的最优行动。*

| # | 场景 | 关键定理 | 结果 |
|---|------|----------|------|
| P11 | 反制法术战 | `game_tree_finite` — 博弈树深度 ≤ 施法者数量 | `native_decide` ✓ |
| P23 | 双生加速术 + 专注中断 | `break_round_2 = 0` — 对手盈亏平衡点在第 2 轮 | `native_decide` ✓ |
| P26 | 擒抱/推挤锁定 | `threshold_is_6` — 维持 3 轮锁定需 +6 运动 | `native_decide` ✓ |

### VII. 组合优化

*构建选择、队伍组成、资源调度——通常为 NP 困难，利用 BG3 实例规模小的特点精确求解。*

| # | 场景 | 关键定理 | 结果 |
|---|------|----------|------|
| P13 | 偷袭资格 | `eligible_ratio = 832` — 832/2048 状态允许偷袭（40.6%） | 2¹¹ 枚举 ✓ |
| P20 | 队伍组成 | `minimum_cover_size_is_3` — 3 个职业覆盖全部 8 种角色；2 个不行 | C(12,2) + C(12,3) ✓ |
| P24 | 休息调度 | `smart_beats_greedy6` — 贪心短休策略非最优 | 反例 ✓ |
| P27 | 专长选择 | `greedy_suboptimal` — 协同效应使贪心失败；GWM+PAM+哨兵最优 | C(12,3) QUBO ✓ |
| P30 | 狂野魔法涌动 | `positive_expected_value`, `high_variance` — 期望为正但方差远大于均值 | 统计 ✓ |
| P31 | 治疗效率 | `healing_word_theorem` — 攻击 DPR ≥ 8 时，治疗之言优于疗伤术 | `omega` ✓（全称） |
| P32 | 多职业兼职 | `rogue_dip_improves_fighter` — 纯职业构建非最优 | 穷举整数规划 ✓ |

---

## 可靠性

审稿人首先会问：*"这和测试套件有什么区别？"*

**简要回答**：本仓库中的每一个 `theorem` 都是由 Lean 4 内核类型检查的证明项——包括使用 `native_decide` 的定理。与测试的区别在于，`native_decide` 是**有限域上的穷举模型检查**（由内核认证），而非抽样。

### 可信计算基（TCB）

所有证明归约为 Lean 4 内核及以下公理（可通过 `#print axioms` 验证）：

| 公理 | 来源 | 说明 |
|------|------|------|
| `propext` | Lean 4 核心 | 命题外延性 |
| `Quot.sound` | Lean 4 核心 | 商类型可靠性 |
| `Classical.choice` | Lean 4 核心 | `simp` 策略使用 |
| `Lean.ofReduceBool` | `native_decide` | 信任编译归约；与 mathlib TCB 相同 |

`Scenarios/` 下无任何自定义 `axiom` 声明。`Axioms/BG3Rules.lean` 中的公理（P1–P5）是为 LLM 管线设计的独立形式化目标，**不被**任何场景文件导入。

### 证明技术分类

| 技术 | 证明了什么 | 示例 |
|------|-----------|------|
| `native_decide` + 枚举 | **穷举模型检查**：检查所有状态，生成证明证书 | P13：全部 2048 个布尔状态 |
| `native_decide` + 具体值 | **验证计算**：确认特定实例 | P12：`crit_max = 127` |
| `omega`、`simp`、`cases` | **结构化证明**：对所有输入成立（全称量化） | P6：`cascade_always_terminates` |
| `sorry` | **开放问题**：已陈述但未证明，明确标注 | P7：`esl_le_total_level` |

具体而言：27 个场景中有 11 个包含至少一个由结构化策略（非 `native_decide`）证明的全称量化定理。其余场景使用有限域上的穷举枚举，这是标准的验证型模型检查技术。

### 模型忠实度

Lean 模型编码的是 [bg3.wiki](https://bg3.wiki) 的规则描述，而非游戏二进制文件。这构成了潜在鸿沟：

| 层级 | 信任对象 | 弥合方式 |
|------|----------|----------|
| Lean 模型 | bg3.wiki 正确 | 游戏内预言机将预测与真实引擎比对 |
| bg3.wiki | 社区逆向工程 | 与游戏数据文件交叉验证；wiki 拥有逾万名编辑者 |
| 游戏内预言机 | BG3 Script Extender API | SE 是标准 Mod 框架，为社区广泛使用 |

CEGAR 循环旨在迭代地弥合此鸿沟：当预言机与模型出现分歧，差异将作为修正反馈至 LLM。当前 `v0.1-alpha` 提供 Lean 验证层；预言机集成已可用但需手动游戏交互。

---

## 实际运行效果

### 1. 验证定理（终端）

```
$ cd src/2_fv_core && lake build
Building Scenarios.P13_SneakAttackSAT
Building Scenarios.P21_DeathSaveMarkov
Building Scenarios.P29_CoffeelockInfiniteSlots
...
Build completed successfully.     # 所有定理已通过类型检查
```

### 2. 爬取游戏数据（终端）

```
$ python3 -c "import importlib; importlib.import_module('src.1_auto_formalizer.crawler').crawl_all()"
[INFO] Discovering spells in Category:Spells...
[INFO] Found 347 spell pages
[INFO] Fetching Fireball... OK (Projectile_Fireball, 8d6 Fire)
...
[INFO] Crawl complete: 312 spells stored in dataset/valor.db
```

### 3. 游戏内验证（分步教程）

**示例**：P12 声称圣骑士6/术士6持巨剑，4环神圣惩击暴击亡灵，最大伤害为 127。

```
步骤 1.  安装 BG3 Script Extender（github.com/Norbyte/bg3se）。

步骤 2.  将 VALOR Mod 复制到 Script Extender 目录：
           cp src/4_ingame_oracle/Mods/VALOR_Injector/*.lua "<BG3_SE_Lua目录>/"
         在 BootstrapServer.lua 中添加：
           Ext.Require("main")
         创建目录：
           mkdir -p "<BG3_SE_Lua目录>/VALOR_Scripts"
           mkdir -p "<BG3_SE_Lua目录>/VALOR_Logs"

步骤 3.  启动 BG3，加载存档，打开 SE 控制台（默认 F10）。
         应看到："[VALOR] Session loaded, polling VALOR_Scripts/"

步骤 4.  手动重现场景：
           a. 创建或重置圣骑士6/术士6角色（力量20）
           b. 装备巨剑
           c. 找到或召唤亡灵敌人
           d. 存档
           e. 使用 4 环神圣惩击攻击
           f. 若暴击：记录伤害提示

步骤 5.  比对：
           Lean 预测：最大 127（4d6 武器 + 12d8 惩击 + 7 固定）
           游戏提示：应显示 ≤ 127 总伤害

         若游戏显示不同数值，即为模型-引擎分歧——
         请提交 Issue 或 Pull Request。
```

---

## 目录结构

```
src/
  1_auto_formalizer/     Python：Wiki 爬虫、解析器、SQLite 数据库、LLM 存根
  2_fv_core/
    Core/                Lean 4 游戏本体论 + 状态机
    Axioms/              形式化 BG3 规则（P1–P5，隔离，不被 Scenarios 导入）
    Proofs/              终止性与漏洞利用证明
    Scenarios/           自包含场景 P6–P32（核心贡献）
    lakefile.lean        构建清单
  3_engine_bridge/       Python：Lean 输出 → Lua 脚本 → 日志分析
  4_ingame_oracle/       Lua：BG3 Script Extender Mod
eval/                    反馈循环编排器 + 指标收集
tests/                   23 个 pytest 测试（Python 层）
dataset/                 原始 Wiki 转储 + 手工标注基准
```

## 参考文献

- Clarke et al. (2000). Counterexample-Guided Abstraction Refinement. *CAV*.
- de Moura & Ullrich (2021). The Lean 4 Theorem Prover. *CADE*.
- [sts_lean](https://github.com/collinzrj/sts_lean) — 《杀戮尖塔》无限连击的 Lean 4 形式化验证。
- [bg3.wiki](https://bg3.wiki) — 社区 Wiki，唯一数据来源。

## 许可证

MIT

---

*本文档为 `v0.1-alpha` 版本的归档中文翻译。英文版 README.md 为首要更新版本。*
