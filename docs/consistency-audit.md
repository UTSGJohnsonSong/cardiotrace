# 文档一致性对账 —— 提案，未执行任何修改

> **状态**：提案。本文件是本次唯一新增，**没有改动任何其它文件**。
> **不做的事**：不宣布任何文件为权威版本，不重排目录结构（按全局约定，这由你定）。
> **审查基线**：`HEAD = 98d96cd` + **当前未提交的工作区改动**。
>
> ⚠️ **审查过程中工作区被并发修改过两轮。** 开始时 `git status` 干净；
> 第一轮出现 17 个修改 + 6 个新文件（`src/descriptive.py` 换访谈权重 ·
> `scripts/render_report.py` 改 t 区间 · `src/models.py` 实现加权 C ·
> `scripts/crosscheck_survey.{py,R}` + `docs/crosscheck-survey.md` 新增 R 交叉核对）；
> 第二轮又改了 `scripts/fit_survival_models.py` · `src/discrimination.py` ·
> `reports/model_results.json` 与三份测试。
> 下表**已按工作区当前状态逐条复核**，并用 ✅ 标出「已经修好」的条目——
> 它们仍然列出，因为**文档侧还没跟上**，或**已发布的产物还没重跑**。
> 如果那条主线还在动，执行前请对第 4、6、9、19、32、36 条再确认一次。
>
> **口径**：每条附 `file:line` 与原文；数字类断言附实测值（复算见 §B）。
> **范围**：`README.md` · `docs/research-design.md` · `docs/pce-benchmark.md` ·
> `docs/advisor-briefing.md` · `docs/methodology-review.md` · `src/*.py` 模块 docstring。
> 顺带扫到的 `Makefile` · `scripts/render_report.py` · `docs/meeting-03-followup.md` ·
> `docs/tableau-dashboard.md` 一并列入，因为它们直接生成或污染上面这些文档的内容。

**分级**

| 级 | 含义 |
|---|---|
| **S1** | 已对外发布的研究断言与代码/产物矛盾，或发布了文档自己说「不应展示」的数字 |
| **S2** | 状态标记（locked / open / 未开始）与实际进度矛盾 |
| **S3** | 数字过期：文档里的数与当前流水线产出的数不同 |
| **S4** | 表述不一致，不影响结论 |

---

## A. 主对账表

| # | 级 | 位置 `file:line` | 原文（节录） | 与什么矛盾 | 哪边对 | 最小修改 |
|---|---|---|---|---|---|---|
| 1 | **S1** | `README.md:17` | `**Any-CVD prevalence, survey-weighted:** 8.1% of US adults in 1999-2000 → 9.61% in 2021-2022` | `reports/descriptive_results.json` 当前值 `std_first 0.0869 → std_last 0.0803`（年龄标准化后**下降**）；`scripts/build_site.py:785` 写的是 "Crude prevalence rose while the age-standardised series fell. The rise is the population ageing, not the disease spreading." | **JSON / 站点对。** README 这段由 `scripts/render_readme.py` 从 `reports/results.json` 生成，而该文件时间戳是 **2026-07-04**，属旧横断面流水线 | 换数据源：Key Findings 改读 `descriptive_results.json` + `model_results.json`；在换源之前不要重跑 `make site` |
| 2 | **S1** | `README.md:18-19` | `**Best model:** Xgboost predicts coronary heart disease at ROC-AUC 0.8585 … (5-fold cross-validated, survey design retained)` / `**Top risk drivers (SHAP, Any-CVD model):** age, hypertension_flag, poverty_income_ratio` | `docs/advisor-briefing.md:441-442`：**「现有 README 里的数字——ROC-AUC 0.8585、SHAP 排名、患病率趋势——全部建立在给 24.4% 样本编造的化验值之上，不应对外展示。」** 另与 `research-design.md:44-47`（按周期切分，随机 K-fold 会泄漏 PSU）、`:122`（**绝不用 SHAP 做因果解释**）矛盾 | **advisor-briefing 对。** `reports/tables/model_metrics.csv` 与 `results.json` 均为 2026-07-04 产物，早于 8 月的实验室数据修复 | 删掉这两条；若要留模型行，用 `model_results.json` 的 Harrell C（并先看第 6 条） |
| 3 | **S1** | `README.md:216-217` | `**Point estimates only.** Design-based confidence intervals via Taylor linearisation are not yet implemented.` | `src/descriptive.py:49-62`（VARIANCE 段）已实现 Taylor 线性化；`reports/tables/part1_prevalence_by_cycle.csv` 现在带 `design_dof / crit / lo_std / hi_std`；`src/models.py:122-124` 输出 cluster-robust `hr_lo95/hr_hi95` → `reports/tables/cox_systolic_bp.csv`、站点 `render_report.py:1053` 显示 `HR 1.121 · 1.077–1.166`；新增的 `docs/crosscheck-survey.md` 还拿 R `survey` 对了一遍 | **代码对，README 错。** 这是重构前遗留的 limitation | 删掉这条。若要保留一个诚实的残留限制，改写为「区间为设计基（Taylor + cluster-robust）；`svycoxph` 的分层 ultimate-cluster 估计量与 lifelines 的估计量仍有 1.2% 中位差异，见 `docs/crosscheck-survey.md`」 |
| 4 | **S1** ✅ | `scripts/render_report.py:664-668` | 原文曾是 `The interval excludes zero, so the decline is not noise.` | `descriptive_results.json` 现在给 `std_slope_ci = [-0.01218, +0.00035]`（**含零**）、`std_slope_excludes_zero: false`、`slope_dof: 8`、`slope_t_crit: 2.306` | **JSON 对。已在工作区修好**：该句现由 `p1['std_slope_excludes_zero']` 驱动条件文案 | **代码已修，但已发布的站点还没重跑**：`docs/burden.html` 与 `docs/cardiotrace-report.html` 仍含 `interval excludes zero, so the`，`docs/index.html` 仍印 `95% CI −1.16 to −0.06 pp`（旧的 1.96 版本）。→ 跑 `make descriptive site` |
| 5 | **S1** | `Makefile:30` + `:68` | `data:` → `$(PY) data/download.py` ；`all: up data load dbt analyze` | `README.md:118-122` 的复现步骤用 `data/download_from_catalog.py`；`research-design.md:625` 「`data/download_from_catalog.py` 取代 `data/download.py`（后者已标 deprecated）」；`research-design.md:689` 记该文件「**待重写**」 | **README / research-design 对。** `make all` 仍会跑弃用下载器 + `run_pipeline.py`（旧 XGBoost/SHAP 流水线，见其 `:6-7` docstring），覆写 `reports/results.json`，再由 `make site` 灌回 README | 这是第 1、2 条的**机制性成因**，不修好则两条会自动复发。`data:` 改指 catalog 下载器；`all:` 移除旧链或明确拆成两条 |
| 6 | **S1** ✅ | `src/models.py:182+` · `scripts/fit_survival_models.py:138` | 原文曾是 `def concordance(risk, time, event, weights=None)`，函数体从不读 `weights`；调用方也没传 | 与 `README.md:10` "Survey weights are applied to every population estimate."、`src/models.py:44-50` "SURVEY DESIGN … Fitted with the pooled MEC exam weight" 口径不一致 | **已在工作区全部修好**：加权 C（Fenwick 树）+ `horizon` 参数已实现，`fit_survival_models.py` 与 `discrimination.py` 都改为传 `weights=` / `horizon=`，产物也重跑了 | **对外数字已经变了**：`reports/model_results.json` 现在是 `harrell_c: 0.838` / `harrell_c_unweighted: 0.804`，10 年 `mean_predicted_pct` 由 2.82 → **1.96**。→ 见第 36 条：**五处文档仍写 0.804**，且已发布站点仍是旧值 |
| 36 | **S1** | `src/discrimination.py:1` `:4` `:138` · `src/screening.py:3` · `docs/pce-benchmark.md:122` | `"""Is C = 0.804 held down by the variable set, or by the model form?` / `reaches Harrell C = 0.804 at ten years on held-out later cycles` / `the 0.804 already published` / `The published model uses eleven variables and reaches C = 0.804.` / `不能拿主队列上得到的 C = 0.804 直接和 PCE 在这个子样本上的表现比。` | 第 6 条的修复把已发布值改成了 **0.838**（未加权 0.804 作为对照保留在 `harrell_c_unweighted`）。这五处 docstring / 文档把 **0.804 称作「已发布值」**，从这次重跑之后就不再成立 | **`model_results.json` 对** | 五处改为 0.838（并注明未加权对照 0.804）。`docs/pce-benchmark.md:122` 的**论证本身不变**（两个 C 在不同人群上不可比），只是数字要换。另需重跑 `make learning site`：`reports/part4_learning_results.json` 与 `docs/*.html` 仍基于未加权 C |
| 7 | **S1** | `docs/pce-benchmark.md:104-106` vs `:152-160` | §3.5 `🔒 对比协议 —— 2026-08-19 用户锁定` / `**在这四条落实之前不开工。**` ←→ §4 `## 4. 尚未决定 / 待办` 下三条（`**映射规则未定**`、完整病例子样本、服药血压）**正是 §3.5 已锁的 ①②③** | 同一文件自相矛盾；`research-design.md:692` 也把这四条记为 🔒 | **§3.5 对。** §4 是 8-19 锁定之前写的待办，锁定后没删 | 删掉 §4 前三条，或改写为「§3.5 已锁定，此处仅留实现待办」 |
| 8 | **S1** | `scripts/render_report.py:1473-1477` | `Three decisions remain open and are recorded as open: how to handle race categories …, whether to restrict the comparison to the subsample with all nine inputs observed, and whether treated blood pressure enters through the equations' own treated branch …` | 就是 §3.5 已锁的三条；同一 section 顶部 `:1426` 的 chip 却写着 `Protocol locked · analysis pending` | **§3.5 / `research-design.md:692` 对。** 公开报告把已锁的决定说成「仍然开放」——比文档内部矛盾更严重，它对外弱化了导师已拍板的约束 | 改写为「协议四条已锁定（列出四条），待做的是实现」；chip 文案保持不变 |
| 9 | **S1** | `README.md:52-55` | `**Survey weights, everywhere.** … Population estimates use the pooled MEC exam weight` | `src/descriptive.py:84-103` + `:199` 已把 Part 1 默认权重改为**访谈权重** `WEIGHT_INTERVIEW = "wtint2yr"`，理由在 `:86-95`（结局 MCQ160B-F 是**入户访谈**问的）；`descriptive_results.json` 现在带 `"weight": "wtint2yr"` | **代码对。** README 描述的是修正前口径 | 改为：人群估计用**访谈**权重（Part 1，结局来自访谈）/ **体检**权重（Part 3 与 ascertainment，暴露来自体检），并写出「取最严格组件的权重」这条规则 |
| 10 | **S2** | `docs/research-design.md:130` | `\| **解决了什么** \| … \| **反向因果、幸存者偏倚、"预测"名不副实——全解决** \|` | 同表下一行 `:131` 的「没解决什么」只写「只能预测死亡，不能预测发病」；`research-design.md:451`「`SEL` 是**对撞**且我们无法不条件于它 …… **无法修复**，只能写进 limitations」；`README.md:210-211`；`advisor-briefing.md:302 / 414 / 422` 三处「无法修复」 | **limitations 侧对。** 路线 C 换掉的是**反向因果**与「预测」名实不符；幸存者偏倚源于抽样框（只抽活着且住社区的人），接 LMF 不解决 | 从「全解决」里删掉「幸存者偏倚」，移到同表 `:131` 的「没解决什么」格，并注明与 §4.2 第 4 条一致 |
| 11 | **S2** | `docs/research-design.md:671` | `\| 2026-08-09 \| 1 · 路线 \| C：LMF 纵向队列 \| 稀缺性 > 严谨性（严谨是附赠）；一次性解决反向因果+幸存者偏倚 \| 全局 \|` | 两处问题：① 幸存者偏倚同上；②**「稀缺性 > 严谨性（严谨是附赠）」**——作为求职内部笔记成立，写在决策记录里就是把「严谨」记录为次要目标，而整份文档、README limitations、`advisor-briefing.md` 第 5 部分全部建立在相反立场上 | **相反立场对。** 这句的原始上下文在 `:144-146`，那里说的是「作品集的差异化价值在稀缺」，属**选题理由**，不是方法论立场 | 理由列改写为「作品集差异化：复杂抽样 + 死亡链接的生存分析少见；方法学门槛不因此降低」；删「严谨是附赠」；偏倚表述按第 10 条修 |
| 12 | **S2** | `docs/research-design.md:32` | `\| 7 \| 可重复性契约 \| ⬜ \| 别人怎么确认跑的是同一份数据？ \|` | `data/raw/MANIFEST.json` 与 `data/raw_mortality/MANIFEST.json` 均存在；`README.md:129-131` 记 SHA-256 + `--verify`；`research-design.md:630`「SHA-256 写入 `data/raw/MANIFEST.json`，`--verify` 可复核」 | **代码对** | 状态改 🔒（或 🔄，若认为 dbt/notebook 层尚未收口），并注明落地位置 |
| 13 | **S2** | `docs/research-design.md:47-50` | `\| 12 \| 抽样设计的正确处理 \| ⬜ \|` `\| 13 \| 描述性分析 \| ⬜ \|` `\| 14 \| 模型与验证策略 \| ⬜ \|` `\| 15 \| 校准、基准、敏感性 \| ⬜ \|` | 12 → `src/descriptive.py:49-62` Taylor + `src/models.py:95-106` cluster-robust + 新增 R 交叉核对；13 → `reports/tables/part1_*.csv` 七张表；14 → `src/models.py` + `scripts/fit_survival_models.py` 按周期外推验证；15 → `reports/tables/calibration_{5,10}y.csv` + 同文件决策表 `:691-693` 三条 15 号节点决定 | **代码与决策表对。** 5 个 ⬜ 里至少 4 个已实质完成 | 逐个更新；或按 §C 取消路线图的状态列，只留决策表一套状态 |
| 14 | **S2** | `docs/research-design.md:56` | `\| 16 \| 报告规范与可重复包 \| ⬜ \|` | `reports/tables/strobe_part3.csv` 已产出；`docs/*.html` 五页站点已发布；`reports/cardiotrace-report.html` 已生成 | **产物对** | 同上 |
| 15 | **S2** | `docs/research-design.md:60` / `:152` | `## 节点 1 · 研究问题与 estimand 🔄` / `## 节点 3 · 结局定义 🔄` | 路线图 `:21` 记节点 1 为 🔒；`:139` 是 `### 1.6 🔒 节点 1 决定`；节点 3 的 `:197` 是 `#### 3.2.2 🔒 决定`；`advisor-briefing.md:437`「**已锁定的决策节点**：1 研究问题 · 2 纳入排除 · 3 结局定义 · 4 DAG · 5 数据源 · 6 变量普查」 | **🔒 对。** 章节标题的 🔄 是写作残留 | 章节标题改 🔒；节点 2 在路线图 `:22` 也是 🔄 而 `:690` 已 🔒，一并改 |
| 16 | **S2** | `docs/research-design.md:621` | `## 节点 7 · 数据修复（步骤 0）✅ 已完成 2026-08-09` | 路线图 `:32` 的节点 7 是「**可重复性契约**」，不是「数据修复」。同一编号两个含义 | **路线图是原始定义**；`:621` 借用了编号 | 该节改称「步骤 0 · 数据修复」或另给编号。**这也是第 12 条被漏掉的直接原因**——看起来节点 7 已完成，实际完成的是另一件事 |
| 17 | **S2** | `docs/research-design.md:41` | `\| 11 \| 缺失机制与插补 \| ⬜ \| 缺失是随机的、还是设计造成的？ \|` | 代码**已经替你做了决定**：`src/models.py:103` `fit_df = d[cols].dropna()` = 完整病例。实测（§B.7）：丢弃 **2,207 / 20,736 = 10.64%**，被丢者 CVD 死亡率 **6.12%** vs 保留者 **4.26%** —— **缺失与结局相关** | **代码已定，文档未记。** 这不是「未开始」，是「已经默默决定了」 | 把完整病例写进节点 11 与 README limitations，附上这两个率；是否补 IPW / 多重插补由你定 |
| 18 | **S2** | `docs/advisor-briefing.md:101` `:127` `:321` + `docs/research-design.md:471` | `方法 \| … \| **cause-specific Cox + Fine-Gray**` / `④ 逼出模型：cause-specific Cox（病因）+ Fine-Gray（预测）` / 模型 P 的「模型」格 = `Fine-Gray` | `research-design.md:478-480`（2026-08-10 更新：「预测侧最终**没有拟合 Fine-Gray**」）+ 决策表 `:683`；`src/models.py:30-42` 标题就是 `COMPETING RISK, WITHOUT FINE-GRAY` | **8-10 决定 + 代码对** | 四处 `Fine-Gray` 改为「两个 cause-specific Cox 组合出 CIF」 |
| 19 | **S2** | `docs/research-design.md:497-498` | `\| 交叉验证 \| R \`survey::svycoxph\` 跑一次，把系数对照表放进 docs \|` / `\| 描述性 CI \| **R \`survey\` 包** \| Taylor linearization，**Python 侧无同等成熟实现** \|` | **两行都需要改，但方向相反**：`svycoxph` 交叉核对**现在已经做了**（`scripts/crosscheck_survey.R` + `docs/crosscheck-survey.md`，系数一致到 3.3e-12）；而描述性 CI **不是**由 R 产出的，是 `src/descriptive.py` 的 Python 实现产出，R 只做独立复核（两者一致到 4.2e-17）。所以「Python 侧无同等成熟实现」已被自己的交叉核对推翻 | **代码 + 交叉核对对** | 第一行改为「已完成，见 `docs/crosscheck-survey.md`」；第二行改为「Python 自实现 Taylor 线性化，R `survey` 作独立复核」。注意 `docs/crosscheck-survey.md:3-5` 自称 **proposed，尚未接进报告**，改文档时不要把它写成已发布 |
| 20 | **S2** | `docs/advisor-briefing.md:412` | `MEC 权重按周期合并（**注意 1999-2002 需 4 年权重 \`WTMEC4YR\`**）` | `src/cohort.py:164` 只读 `WTMEC2YR`；全仓库无 `WTMEC4YR`，也没有除以周期数的合并因子 | **代码是现状，文档描述的是没做的事** | 见 §D：**先实测影响再改文档**，否则会把「没做」写成「不需要做」 |
| 21 | **S3** | `docs/research-design.md:280-282` | S.0 表：Part 3 `N` = `**45,035**（有体检随访）`，`事件数` = `**2,513**` | 最终队列 `data/processed/cohort_part3.csv.gz` = **20,736 行 · 925 CVD 死亡 · 2,711 竞争死亡 · 235,553 人年**（§B.1）；`reports/tables/strobe_part3.csv` 有完整阶梯 | **队列文件对。** 45,035 / 2,513 是 STROBE 的中间步（`Completed the MEC examination`），不是分析样本 | S.0 改成最终值，并注明 45,035 属哪一步；或加一列「阶段」 |
| 22 | **S3** | `docs/advisor-briefing.md:25` / `:266` | `队列 1999–2014，8 个周期，51.7 万人年，2,513 例心血管死亡。` / `CVD 死亡 **2,513**，非 CVD 死亡 **5,472**，比例 **1 : 2.18**` | 同上：235,553 人年 · 925 例 · 2,711 例竞争死亡 · 比例 **1 : 2.93**（`README.md:11` 已写 2.9 : 1） | **队列文件对**（这份写于 2026-08-09，早于队列定稿） | 两处一并改。注意「竞争事件是主事件两倍以上」这个**论证仍然成立**（2.93 倍），只是数字要换 |
| 23 | **S3** | `docs/research-design.md:336-338` | S.3 `随访人年 **517,478**` / `CVD 死亡率 **4.86 / 1000 人年**` / `CVD 死亡 : 非 CVD 死亡 **1 : 2.18**` | 当前队列：235,553 人年 · 3.93/千人年 · 1 : 2.93 | **队列文件对。** 这是排除前（18+、含基线 CVD）的量级 | 标注「排除前量级」，或换成最终值 |
| 24 | **S3** | `docs/meeting-03-followup.md:48` | `\| 1999–2014，40–79，基线无 CVD \| 20,737 \| **925** \| 2,712 \| 235,558 \| 3.93/千人年 \|` | 队列文件：20,736 / 925 / **2,711** / **235,553**。差 1 人见 `reports/tables/strobe_part3.csv` 末行 `Cause of death coded for every decedent, 20736, 1` | **队列文件对**（该排除步是这份纪要之后才加的） | 对齐到 20,736 / 2,711 / 235,553，或注明口径 |
| 25 | **S3** | `src/survival.py:10-11` | `competing deaths outnumber CVD deaths 2.9 : 1 (2,712 vs 925)` | 队列文件：**2,711**（`README.md:147` 也是 2,711） | **队列文件 / README 对** | `2,712` → `2,711`（比值 2.9 : 1 不变） |
| 26 | **S3** | `docs/pce-benchmark.md:120` `:157-158` · `research-design.md:692` · `meeting-03-followup.md:49` | `PCE 九项输入齐全的完整病例（约 17,464 人 / 756 事件）` / `**必须在同一 17,464 人子样本上重新评估**` | 当前产物 `reports/tables/pce_cascade.csv` 末行 = **18,769**；我在缓存队列上直接复算九项齐全 = **18,744 人 / 824 事件**（§B.6） | **当前产物对。** 17,464 是 8-09 会议时的数，早于 1999–2004 实验室数据补齐（缺失变少 → 子样本变大） | 三处一并更新。**§3.5② 的约束本身仍然成立**（必须在同一子样本上重评自家模型），只是 n 变了。先解决第 27 条再定这个数 |
| 27 | **S3** | `scripts/pce_variable_cascade.py:58-60` → `reports/tables/pce_cascade.csv` | 阶梯起点 `all 1999-2014 respondents, 82091` → `free of self-reported CVD at baseline, **20771**` | `reports/tables/strobe_part3.csv` 同一步 = **20,737**，最终 **20,736**。级联脚本没走 `ELIGSTAT` 与 `Completed the MEC examination` 两步，且顺序不同 | **STROBE 表是分析样本的定义**；级联表的百分比因此不是在分析队列上算的 | 让级联复用 `build_cohort` 的排除阶梯；或在表头声明「起点为 `build_cycle` 全量，非 STROBE 分析样本」 |
| 28 | **S4** | `README.md:4` vs `:75` `:126` `:173` | 徽章 `tests-128%20passing`；正文三处 `The 85 tests are regressions…` / `pytest tests/ -q  # 85 tests` / `tests/  # 85 regressions for defects that shipped` | `reports/test_summary.json` = `{"collected": 128, "failed": 0}`；`scripts/render_readme.py:66-77` 只自动更新徽章，不碰正文 | **128 对** | 三处 85 → 128；更好的做法是把这三处也纳入 `render_readme.py` 的自动替换，否则下次仍会漂 |
| 29 | **S4** | `README.md:6` vs 全部 `.md` | `CardioTrace ingests **CDC NHANES 1999–2023**` | **这条不是简单的笔误**：工作区新加的 `src/descriptive.py` 注释指出 CDC 官方名称是 `NHANES August 2021-August 2023`，并因此把该周期的时间轴中点改为 **2022.6**、新增 `CYCLE_LABEL = {"2021-2022": "Aug 2021–Aug 2023"}`。所以 README 的 `1999–2023` **反而更接近官方口径**，而所有 `.md`（含 `README.md:17` 自己）仍写 `2021-2022` | **需要你定一个称谓**，两边现在各说各话 | 全项目统一：文件夹/后缀键继续用 `2021-2022`，**面向读者的文本统一用官方名**（或反之）。选定后 README `:6` 与 `:17` 至少要自洽 |
| 30 | **S4** | `README.md:2` | `A prospective cohort study of cardiovascular mortality, built from **11 NHANES cycles**` | 前瞻队列是 **8** 个周期（`README.md:142` `NHANES 1999–2014, 8 cycles`；队列文件实测 8 个 cycle 值）。11 是 Part 1/2 的横断面序列 | **8 对**（就 "prospective cohort" 这个主语而言） | 副标题改 8 cycles，或改写成不带数字的表述 |
| 31 | **S4** | `src/models.py:35` | `CIF_1(t\|X) = sum over u<=t of  S(u-\|X) * dH_1(u\|X)` | `src/models.py:176-178` 实际算的是同格点的 `S(u)`：`surv_prev = np.exp(-(h1 + h2))` 与 `dh1 = np.diff(h1, prepend=0.0)` 逐元素相乘，没有错开一格（变量名 `surv_prev` 也说明本意是 `S(u-)`） | **docstring 的公式对，代码差一格** | 量级极小（10 年平均预测风险 1.96% 上约 +0.004 pp，`n_grid=400`），但公式与实现不符要收口：**要么改代码对齐 `S(u-)`，要么改 docstring 承认用的是 `S(u)`** |
| 32 | **S4** | `src/ascertainment.py:231-232` | `"lo_std": max(0.0, p_std - 1.96 * se_std)` / `"hi_std": p_std + 1.96 * se_std` | **这是这轮修改新造成的不一致**：`src/descriptive.py:511-522` 已改用 `stats.t.ppf(0.975, dof)` 并同时导出 `lo_std_normal`，`part1_prevalence_by_cycle.csv` 也新增了 `design_dof / crit` 两列；而 `ascertainment.py` 仍是固定 1.96，`reports/tables/part1_ascertainment.csv` 未重跑 | **t 版本对**（同一份报告里两种区间口径并存，读者无法分辨） | `ascertainment.py` 跟着改用设计自由度，或在报告里标明该表用的是正态近似 |
| 33 | **S4** | `docs/tableau-dashboard.md:32` | `\| \`se_pct\`, \`ci_lo_pct\`, \`ci_hi_pct\` \| Design-based standard error and 95% interval \|` | 源表 `part1_prevalence_by_cycle.csv` 现在同时有 `lo_std/hi_std`（t）与 `lo_std_normal/hi_std_normal`（1.96），文档没说导出的是哪一套 | **需要指明** | 写明导出的是 t(design_dof) 版本还是正态版本；`scripts/build_tableau_extract.py` 也要跟着确认 |
| 34 | **S2** | `docs/methodology-review.md:4` `:673` | `审查对象：commit \`c523561\`（main，工作区干净）` / `_审查基于 commit \`c523561\`_` | 其中 `§5.2【严重】没有任何置信区间`、`§6.3【README 与实现不符】模型根本没用权重`、`§4.1 三层漏斗是死代码` 等均已修复；`README.md:177` 把它描述为 "the audit that started the rework" | **该文件本身没错**，它是历史快照；风险在于没有醒目的过期标记，读者会把 §5–§8 的「现状」读成今天的现状 | 顶部加一行状态横幅：「本文件是 `c523561` 的历史审查快照，不反映当前代码」。**正文不要改**——保留原始诊断的价值 |
| 35 | **S3** | `docs/advisor-briefing.md:435-445` | `## 第 6 部分 · 当前进度与欠账` / `**⚠️ 但原有分析代码一行未改。**` / `**下一步**：重写下载器为 catalog 驱动 → 补回 1999–2004 实验室数据 → 重跑 ETL 与 dbt → LMF join → STROBE 流程表 → 第一版 Kaplan-Meier` | 这五步全部完成（`data/download_from_catalog.py` · `data/raw/` 231 个 XPT · `src/cohort.py` · `strobe_part3.csv` · `src/survival.py`） | **代码对**——但「原有分析代码一行未改」这半句**仍然成立**：`run_pipeline.py` / `src/model.py` / `src/analysis.py` 确实没改，且仍挂在 `make all` 上 | 第 6 部分重写为当前进度；**保留「旧流水线仍在 Makefile 里」这条欠账**（与第 5 条同一件事） |

---

## B. 需要展开的证据

复算均用 `.venv/Scripts/python.exe`，工作目录为仓库根。

**B.1 队列口径（第 21/22/23/24/25 条）**

```
rows 20736 | cvd 925 | competing 2711 | person-years 235552.8
cycles 1999-2000 … 2013-2014（8 个）| age 40.0–79.0
```

`README.md:147` 的 `20,736 · 925 · 2,711 · 235,553` 与之一致——目前全项目唯一正确的一处。

**B.2 Part 1 趋势区间（第 3/4 条）** —— `reports/descriptive_results.json`（工作区版本）

```
std_slope_per_decade      -0.00591               → -0.59 pp/decade
std_slope_ci  (t, df=8)   [-0.01218, +0.00035]   → 含零
std_slope_ci_normal(1.96) [-0.01124, -0.00059]   → 不含零
std_slope_excludes_zero   false
slope_dof 8 · slope_t_crit 2.306
```

**已发布的三份 HTML 比 JSON 旧**（HTML 生成于 `2026-08-22 23:12`，JSON 写于工作区改动之后）：
`docs/index.html` 仍印 `95% CI −1.16 to −0.06 pp`，`docs/burden.html` 与
`docs/cardiotrace-report.html` 仍含 `interval excludes zero, so the`。

**B.3 硬编码 1.96 的现存位置（第 32 条）**

```
src/descriptive.py:515      crit = float(stats.t.ppf(0.975, dof))      ← 已改
src/descriptive.py:521-522  lo_std_normal / hi_std_normal = ±1.96·se   ← 保留作对照
src/ascertainment.py:231-232  lo_std / hi_std = ±1.96·se               ← 未改
scripts/build_descriptive_results.py:140-141  slope_ci(1.96) 与 t_crit 并存
```

新增的 `docs/crosscheck-survey.md` 用 R `degf()` 给出**每周期设计自由度 14–17**，
并算出 1999-2000 用 t(14) 的半宽比 1.96 宽 9%。

**B.4 C 统计量与权重（第 6 / 36 条）**

审查开始时 `concordance` 接受 `weights` 却从不使用；我按当时的调用路径复算得 **C = 0.8037**，
即已发布的 `0.804` 是**未加权**值。审查过程中这条被完整修好：加权实现 + `horizon` 截断 +
两个调用方都改了 + 产物重跑。当前 `reports/model_results.json`：

```
10 年： harrell_c 0.838 · harrell_c_unweighted 0.804 · n_evaluable 4669
        mean_predicted_pct 2.82 → 1.96 · mean_observed_pct 2.76 → 2.02（改为加权）
 5 年： harrell_c 0.802 · harrell_c_unweighted 0.797
```

**未跟上的是文档与已发布产物**：`src/discrimination.py:1` `:4` `:138` ·
`src/screening.py:3` · `docs/pce-benchmark.md:122` 共五处仍写 0.804；
`reports/part4_learning_results.json` 与 `docs/*.html` 仍基于未加权 C。

**B.5 R 的现状（第 19 条）**

审查开始时 `find . -name "*.R"` 无输出；写作过程中新增了
`scripts/crosscheck_survey.R` + `scripts/crosscheck_survey.py` + `docs/crosscheck-survey.md`。
该文档 `:3-5` 自称 **"Status: proposed … deliberately *not* wired into `render_report.py`"**。
结论：`svycoxph` 交叉核对**已做**（系数差 3.3e-12），描述性 CI 的产出方**是 Python 不是 R**。

**B.6 PCE 子样本（第 26 条）**

`reports/tables/pce_cascade.csv` 末行 `require HDL cholesterol non-null, 18769`。
在缓存队列上直接复算九项齐全：**18,744 人 / 824 CVD 死亡**（与 18,769 的差来自第 27 条的
两套阶梯）。文档三处的 `17,464 / 756` 与两者都对不上。

**B.7 完整病例（第 17 条）**

```
n 20736 | kept 18529 | dropped 2207 | 丢弃 10.64%
被丢弃者 CVD 死亡率 6.12%   vs   保留者 4.26%
```

即缺失与结局相关，不是 MCAR。目前没有任何文档记录这一步。

**B.8 规则阶梯核对（无矛盾，记录备查）**

`data/catalog/selection_ledger.csv` 1,821 行：KEEP = **225**（20 个概念）、
OFF-DAG = **1,008**、机械排除 = 265+122+17+128+56 = **588**。
与 `README.md:12`、`research-design.md:568-581`、`advisor-briefing.md:337-346`
**完全一致。这一块不用改。**

---

## C. 关于「单一 analysis protocol 文档」的选项

> **我不选，也不宣布任何文件为权威版本。** 下面只列现状、四个可行形态和各自代价。

### C.1 现状：权威关系其实已经写在文档里了

- `docs/advisor-briefing.md:4-5`：「**决策的权威记录在 `research-design.md`**；问题诊断在
  `methodology-review.md`。这一份是从那两份里提炼出的**叙事版**。」
- `docs/pce-benchmark.md:6`：「**决策记录以 `research-design.md` 的决策表为准**，这份只做本议题的展开。」
- `docs/advisor-briefing.md:449`：「本文由 `research-design.md` 的决策记录提炼而成。」

**所以「谁是主文件」在文字上已经有答案**（`research-design.md` 的决策表）。
问题不在缺一个权威文档，而在下面两件**性质不同**的事：

| 漂移类型 | 现在靠什么挡 | 实际发生了什么 |
|---|---|---|
| **状态漂移**（locked / open / 未开始） | 人工同步 | `research-design.md` 里**并存两套状态系统**：顶部 16 节点路线图（`:19-56`）和底部决策表（`:668-694`）。**只有决策表在维护**，路线图停在 8-09 → 第 12–16 条全部由此产生 |
| **数字漂移**（n、C、CI、事件数） | 部分自动（`render_readme.py` 的标记块、`build_site.py` 读 JSON）、部分**手抄进散文** | 第 1、2、21–27 条全部是手抄数字过期 |

**这两件事需要两种不同的机制。** 只新建一个 protocol 文档，只能解决第一件。

### C.2 四个形态与代价

| 方案 | 做什么 | 代价 | 解决哪些条目 | 主要风险 |
|---|---|---|---|---|
| **① 收敛到现有决策表**（不新建文件） | 删掉 `research-design.md:19-56` 路线图的状态列（或整表降级为「研究阶段说明，不带状态」），状态只由 `:668-694` 决策表承载；其余文档删掉自己的状态标记，改为链接到决策表的具体行 | **最小**：一个文件一处结构改动 + 四个文档删标记 | 12–16、18、19 | 决策表是**追加式**的（按锁定顺序），要看「某节点现在什么状态」得从头扫到尾；需在表头加一张「当前状态汇总」小表，否则可读性下降 |
| **② 新建 `docs/analysis-protocol.md`** | 一份薄文档：三个 Part 的 estimand · 决策台账（节点 / 状态 / 日期 / 落地位置） · 每个已发布数字的产出脚本与产物路径。其余五份文档改为引用它 | **中**：新文件约 150–250 行 + 五处加引用 + 删各自状态标记 | 12–16、18、19，并给 21–27 一个「数字该去哪查」的落点 | **它会变成第六份会过期的文档**。除非同时做 ④，否则只是把手工同步的地点换了一处；且它与 `research-design.md` 的决策表职责重叠，**必须有一份明确降级**——而这正是你说了算、我不能替你定的那一步 |
| **③ 把 `research-design.md` 重构成 protocol** | 不新建文件；路线图并进决策表，S.0–S.5 规格段更新到当前口径，文档定位从「活文档 / 决策日志」改为「协议」 | **大**：694 行文档的结构性重写；会丢掉「决策的时间顺序」这一现有价值（`:673`、`:682` 的删除线取代记录靠时间顺序才读得懂） | 同 ②，外加 21、23 | 重写期间文档不可用；且它同时承担「给导师讲的推导过程」与「协议」两个用途，压成一份可能两头不讨好 |
| **④ 机器生成状态与数字**（可与 ①②③ 任一叠加） | 状态存 `docs/decisions.yml`（节点 · 状态 · 日期 · 落地文件 · 理由锚点），数字继续存 `reports/*.json`；各文档用 `<!-- STATUS:node7 -->` 之类标记块由脚本注入。仓库里已有先例：`render_readme.py:59-64` 的 `KEY_FINDINGS` 标记、`build_site.py:770-778` 显式声明每张卡片的数据来源 | **中高**：一个渲染脚本（约 100 行）+ 五个文档插标记 + 一条测试断言（「标记块与源不一致即失败」） | 12–16、18、19 **且不会复发**；若把散文里的数字也纳入标记块，可覆盖 1、2、21–27 | 标记块让 Markdown 变难手写；**且只有加上「不一致即失败」的断言才真正有效**，否则与手工同步等价 |

### C.3 无论选哪个，有三条与选择无关

1. **第 5 条（Makefile 仍跑旧流水线）必须先修。** 只要 `make all` 还会覆写
   `reports/results.json`，任何协议文档都会被 `render_readme.py` 重新灌回旧数字。
   这是第 1、2 条的**机制性成因**，不是内容错误。
2. **`methodology-review.md` 不参与协议。** 它是 `c523561` 的历史快照，价值就在于冻结；
   加一行过期横幅即可（第 34 条），不要并进任何「当前状态」文档。
3. **数字的唯一来源已经是 `reports/*.json`**，这一点项目已经做对了
   （`build_site.py:770-778` 明确写了每张卡片读哪个键）。缺的只是「散文里的数字也走同一条路」。

---

## D. 我没有做的事 / 仍需你确认

- **没有改动任何其它文件。** 本文件是本次唯一新增。
- **没有宣布任何文件为权威版本**，也没有重排目录。§C 只列选项和代价。
- **审查过程中工作区被并发修改两轮**（见文首）。上表已按当前工作区逐条复核，但**如果那条主线
  还在动，第 4、6、9、19、32、36 条的状态需要在执行前再确认一次**。
- **第 20 条（`WTMEC4YR` / 多周期权重合并）我不确定影响面。** 对 Cox 的 HR 点估计无影响
  （权重整体缩放不改偏似然的极值点），但对 Part 1 的加权患病率及其 SE 可能有影响。
  **改文档之前先实测一遍**，否则会把「没做」写成「不需要做」。
- **第 26 条的 17,464 → 18,7xx**：两个候选值（级联表 18,769 / 缓存队列 18,744）来自两套排除
  阶梯（第 27 条）。**先统一阶梯，再定这个数**，不要直接把 17,464 换成其中任意一个。
- **第 6 / 36 条的对外数字已经在这轮被改掉了**：10 年 C 从 0.804（未加权）变成 0.838（加权），
  平均预测风险 2.82% → 1.96%。这不是重构，是**对外口径变更**——五处文档、
  `part4_learning_results.json` 和五页站点都还停在旧值。**改完要一次性重跑并核对全站**。
- **第 29 条（最后一个周期叫什么）需要你定一个称谓**，因为 CDC 官方名与项目内部键不一致，
  而工作区刚引入了官方名。这属于「命名的主从关系」，我不替你选。
- **第 31 条（`S(u-)` vs `S(u)`）**：改代码会让 `model_results.json` 的
  `mean_predicted_pct` 变动最后一位，进而动到站点与 README。改不改由你定；
  但公式与实现不一致这件事要收口。
