# CardioTrace 方法学审查与重设计

> 目的：把当前流水线里**每一个未经论证的选择**摊开，给出权衡、依据、和可执行的替代方案。
> 审查对象：commit `632e92e`（main，工作区干净）。所有断言带 `file:line` 出处。
> 立场：这份文档不是"挑毛病"，是把项目从 *engineering demo* 升级成 *defensible research* 的施工图。

---

## 0. 元问题：项目现在缺的不是解释，是研究设计

### 0.1 诊断

当前项目同时在做**四件互不相干的研究**：

| # | 研究 | 需要的设计 | 现状 |
|---|------|-----------|------|
| 1 | 25 年 CVD 患病率趋势 | 年龄标准化 + 设计基 CI + 趋势检验 | 只有原始加权点估计 |
| 2 | 种族健康公平性 | 分解（诊断可及性 vs 真实患病）+ 混杂调整 | 只有分组均值 |
| 3 | 疫情前后对比 | 准实验识别策略（ITS / DiD） | pre = 10 个周期混合，post = 1 个周期 |
| 4 | 5 个 CVD 结局的 ML "预测" | 纵向结局 + 时序验证 + 校准 | 横断面 prevalent 结局 |

每一件都没做完，而且第 3、4 件的**识别策略是错的**（见 §5.4、§6.1）。

### 0.2 为什么"每个点解释不通"

因为决策顺序反了。正确顺序是：

```
研究问题 → estimand（要估计什么量）→ 识别假设（DAG）→ 数据需求 → 变量选择 → 模型 → 指标
```

当前顺序是：

```
数据能拿到什么 → 建个仓库 → 塞进 XGBoost → 事后找理由
```

README `Why this project is built the way it is`（README.md:22-31）列的五条理由**全部是工程理由**（权重、SMOTE、PR-AUC、去重、仪器统一），没有一条是研究设计理由。这就是导师的感受来源。

### 0.3 第一件要做的事：写下 estimand

在动任何代码之前，先把下面这句话填满并锁定：

> 我们要估计的是，在 **[目标人群：美国非住院成人 20+]** 中，**[暴露/时间]** 与 **[结局：自报医生诊断的 CVD 现患]** 的 **[关联/因果对比/预测性能]**，在 **[调整/条件于 ...]** 之下。

不同的填法会导出**完全不同的**变量集、模型、指标。三条可选路线见 §9。

---

## 1. 数据获取层

### 1.1 【用户核心疑问】"先全引再筛" vs "先筛再引"

**现状**：两层筛选都已发生，且都在下载/读取阶段。

- `data/download.py:80-83` 硬编码 17 个 module（`TARGET_MODULES`）。NHANES 单个周期公开的数据文件在 **150–250 个**之间。
- `src/etl.py:98-104` `_wanted_original_cols()` 在读 XPT 时就只读目标表已有的列——**列级筛选发生在入库之前**。
- 结果：`raw` schema 里根本没有"全部数据"，连审计"我们排除了什么"的证据都不存在。

**导师质疑成立**。但他给的两个选项（全引 / 先筛）是**假两难**。要拆成三种性质完全不同的筛选：

| 类型 | 判据来源 | 看不看结局？ | 会不会引入偏倚 | 应该放在哪 |
|---|---|---|---|---|
| **A 设计性筛选** | 研究问题的定义 | 否 | 不会（它就是研究问题的一部分） | 最前面，下载前 |
| **B 可行性筛选** | 缺失率、覆盖周期、样本量/EPV | 只看边缘分布 | 不会引入选择性偏倚，但改变可推广人群，**必须报告** | 入库后、建模前 |
| **C 结局驱动筛选** | 卡方 / 相关 / p 值 / LASSO | **是** | **会**（乐观偏倚） | 要么不做，要么锁进 CV 内层 |

导师担心的"漏掉隐藏因果"针对的是 **A 类**。而 A 类的正解**不是"全部下载"**，是：

> **全量枚举 metadata，选择性下载数据，并把枚举结果作为审计证据留档。**

#### 具体方案：Stage 0 全量变量普查

CDC 对每个周期发布 variable list（变量名、标签、所属文件、component、可用周期），是**独立于数据本体的小文件**。

```
建表 raw.nhanes_variable_catalog
  variable_name · label · file · component · cycles_available · n_cycles · unit · age_range
```

- 成本：数 MB，一次几分钟。
- 产出：一句可以对导师说的话——"我们**考虑过全部 N 个变量**，排除了 M 个，每一个排除都有规则和记录，这是清单。"
- 这一步**同时**解决了"不预设"和"内存"，因为它不需要下载任何数据。

#### Stage 1 规则（全部可预先声明，全部不看结局）

| 规则 | 内容 | 理由 |
|---|---|---|
| R1 覆盖度 | 变量须在 ≥ 9/11 个周期存在 | 25 年连续序列是研究问题的定义，不是主观取舍 |
| R2 人群 | 须对成人 20+ 采集 | 同上 |
| R3 分析单位 | 须是 person-level | 排除膳食 food-level（DR1IFF）、加速度计原始数据（PAXRAW）——这两类的排除理由是**分析单位不匹配 + 需要专用子样本权重**，不是内存 |
| R4 时序 | 排除发生在结局之后的变量 | 如"因心脏病住院次数"是 collider/mediator，纳入会造成 Table 2 fallacy |
| R5 冗余 | 派生变量与其分量三选一 | 如 BMXBMI vs BMXWT+BMXHT |
| R6 缺失 | pooled missing ≤ 30% | **需要敏感性分析**：20% / 30% / 40% 三档，见 §4.5 |

预计从 ~1500 个变量降到 **150–250 个**。

#### 关于"内存撑不住"——这个理由在技术上站不住，必须诚实承认

量化一下，导师如果懂技术会立刻算这笔账：

| 环节 | 规模 | 是否是瓶颈 |
|---|---|---|
| 最终宽表 62,890 行 × 250 列 float32 | **≈ 63 MB** | 否 |
| 62,890 × 1000 列 | ≈ 250 MB | 否 |
| XPT → Postgres 逐文件流式导入 | 单文件峰值 < 500 MB | 否（`src/etl.py:203-205` 已按周期分批 + `gc.collect()`） |
| 全量下载所有 module 的磁盘占用 | 20–30 GB | 磁盘/IO 问题，**不是内存问题** |
| 膳食 food-level / 加速度计原始数据 | 亿级行 / TB 级 | **是**——但排除理由应写 R3，不是内存 |

历史上真正踩过的内存坑是 **XPT 解析器**，不是列数：进度文档记录 pandas 的 XPORT reader 在 2013-2014 血压文件上 MemoryError，改用 pyreadstat 解决（`src/etl.py:72-79` 的 docstring 也记了）。这个坑和"要不要多引变量"无关。

**结论**：内存不能作为变量筛选的理由。真正的硬约束是下面这个——

#### 真正的硬约束：事件数，不是内存

| 结局 | N | 患病率 | 阳性事件数 |
|---|---|---|---|
| has_angina | 62,654 | 2.88% | **≈ 1,805** |
| has_heart_failure | 62,689 | 3.59% | ≈ 2,251 |
| has_stroke | 62,785 | 4.08% | ≈ 2,562 |
| has_any_cvd | 62,886 | 11.64% | ≈ 7,320 |

（来源：`reports/results.json`）

按经典 EPV ≥ 10，angina 模型最多容纳 **180 个参数**；按 Riley 等的现代最小样本量公式（考虑目标 shrinkage 与 optimism）会更紧。也就是说：

> **就算把 1500 个变量全引进来，也没有统计功效去筛。变量数的天花板由事件数决定，不由内存决定。**

这句话可以直接回答导师——它承认了他的关切（不该主观预设），同时给出了一个**客观的、可计算的**约束边界。

---

### 1.2 周期选择

**现状**：11 个非重叠周期，明确排除 2017-2020 pre-pandemic 合并文件（`data/download.py:16-26`）。

**这一条是全项目论证最扎实的地方，保留。** 理由（避免参与者重复计数）正确、有文档、可复述。

**但要补一个说明**：2019–2020 现场作业被 COVID 中断，NCHS 从未单独发布该波次；这意味着 2018→2021 之间有 3 年空窗。这个空窗对 §5.4 的 COVID 识别既是优势（干净断点）也是劣势（无法排除 2019-2020 期间的其他冲击）。要写进 limitations。

### 1.3 可重复性：缺文件版本与校验

**现状**：`data/download.py:104-127` 的 `download()` 只判断 HTTP 200，不校验 size 或 hash；没有记录下载日期。

**风险**：CDC 会**静默更新** NHANES 文件（发布 revised 版本，文件名不变）。没有 checksum 就无法证明"我跑出来的数字和你跑出来的是同一份数据"。

**修法**（低成本、高信誉回报）：

```
data/raw/MANIFEST.json
  { file, url, sha256, bytes, http_last_modified, downloaded_at_utc }
```

在 `download()` 成功后写入；`load_all_cycles()` 启动时校验。README 里贴上 manifest 的 hash。

---

## 2. 原始层：`raw` 其实不是 raw

**现状矛盾**：

- `dbt/models/staging/sources.yml:7-9` 声明 raw 是 "loaded **verbatim** from the CDC XPT files"。
- 实际上 `src/etl.py:107-124` 的 `harmonize()` 在**入库之前**就改了列名、乘了单位系数。

**后果**：`raw.blood_pressure_exam` 里的 `bpxsy1` 可能来自 BPX（听诊法），也可能来自 BPXO（示波法），**无法区分**。审计链断了，也无法回溯重算。

**修法**：raw 层严格 verbatim（BPXO 列保留原名，进独立表 `raw.blood_pressure_exam_oscillometric`），所有 harmonization 下沉到 staging，并**保留 `bp_method` 列**标记来源仪器。这也是下一节的前提。

---

## 3. 仪器换代：最严重的一处混杂

### 3.1 血压：仪器变更与 COVID 对比**完全共线**

事实（从 `data/raw/` 目录直接可查）：

| 周期 | 有 BPX（听诊） | 有 BPXO（示波） |
|---|---|---|
| 1999-2000 … 2015-2016 | ✅ | ❌ |
| **2017-2018** | **✅** | **✅** |
| 2021-2022 | ❌ | **✅ 仅有** |

也就是说：**你的 pre-COVID 血压几乎全是听诊法，post-COVID 血压 100% 是示波法。**

`reports/results.json` 报告的 `mean_sbp` 从 122.59（pre）降到 121.15（post）。**这 1.44 mmHg 的"下降"完全可能是仪器造成的**，示波法收缩压系统性低于听诊法是有文献的已知现象。当前代码（`src/etl.py:109-115`）只是把 `bpxosy1` 改名成 `bpxsy1`，等于**假定两种方法可互换**——这个假定没有任何论证。

导师问一句"你怎么知道血压下降不是因为换了机器"，现在无法回答。

### 3.2 好消息：桥接校准的数据就在手里

2017-2018 **同时**采集了 BPX_J 和 BPXO_J（同一批人、同一次访视、两种方法）。这是 CDC 专门设计的桥接样本。

**可执行方案**：

1. 在 2017-2018 内配对提取 `(bpxsy_manual, bpxosy_oscillometric)`。
2. 拟合桥接方程（NCHS 自己发过类似的转换式；也可自己拟合，建议 Deming regression 或分位数映射，而不是普通 OLS——因为两个变量都有测量误差）。
3. 把 2021-2022 的示波值映射回听诊尺度（或反过来把全序列映射到示波尺度）。
4. 报告校准前后的 mean_sbp 对比作为敏感性分析。

**当前代码还在破坏这份桥接数据**：`src/etl.py:145` 按文件名排序 glob，`BPXO_J.XPT` 排在 `BPX_J.XPT` 之前，`combine_first`（`src/etl.py:171`）让先读的 BPXO 优先，BPX 只用来补空。结果 2017-2018 的血压值是**两种仪器的静默混合**，桥接样本被销毁了。这行代码必须改。

### 3.3 CRP：更麻烦，建议降级处理

**现状**：`src/etl.py:120-123` 老 assay ×10 做 mg/dL→mg/L 换算，`HSCRP` 直接改名。

**问题**：
- 换算方向正确，但**两种 assay 的检测下限差了一个量级**。老 CRP 大量值堆在检测限（0.2 mg/dL）附近被截断，hs-CRP 能测到 0.01 mg/L。合并后的分布会在拼接点断裂。
- 更致命的是**覆盖**：从 `data/raw/` 看，1999-2004 三个周期**完全没有 CRP 文件**。
- 而 `crp` 却在 `run_pipeline.py:60` 的 `NUM_FEATURES` 里，被 `SimpleImputer(strategy="median")`（`src/model.py:44-46`）填成了全局中位数。

> **这等于给 1999-2004 的约 1.5 万人凭空编造了炎症指标，而且这个编造值还进了 SHAP 图。**

**建议**：CRP 从主分析特征集中移除，改为在有覆盖的周期子集上做**敏感性分析**。要保留就必须交代 assay 桥接 + 缺失机制，代价远超收益。

---

## 4. 变量与特征层

### 4.1 【严重】三层漏斗是死代码

**现状**：

- README.md:102 宣称 `src/features.py # 3-layer feature selection funnel`。
- 实际 `run_pipeline.py:58-62` 硬编码 `NUM_FEATURES` + `CAT_FEATURES` 共 19 个特征，`run_pipeline.py:132` 直接用它们。
- 全仓库搜索：`select_features()` 只在 `scripts/build_notebooks.py:60` 生成的 notebook 里出现，**主流水线从未调用**。而进度文档记录 notebook「目前只生成了框架、没执行」。

> **你声称有筛选方法学，实际跑的是一份手写常量列表。这是导师最容易一击命中的地方。**

必须二选一：要么把漏斗真的接进流水线，要么删掉 features.py 并在 README 里诚实写"特征集由领域知识预先指定"。**我建议后者 + §4.3 的 DAG**，理由见下。

### 4.2 为什么单变量 p 值筛选是错的（即使接进流水线也不该用）

`src/features.py:73-113` 用卡方 / 点二列相关 + `p < 0.05` 筛变量。四个独立的问题：

1. **N = 62,890 时 p 值失去筛选能力**。样本量这么大，几乎所有变量都会显著。这层筛选实际上不做任何事——可以实测证明给导师看。
2. **`r_thresh=0.03`（features.py:99）是纯任意值**，没有任何依据。
3. **漏掉抑制变量（suppressor）**。有些变量单变量与结局无关，但在调整其他变量后显现出强效应。单变量筛选必然漏掉。这正是导师说的"隐藏因果"。
4. **用同一份数据先筛后建模 → 乐观偏倚**。报告的 AUC 和 p 值都失真。`features.py` 是在全量 `df` 上筛的，之后 `model.py:141` 才做 CV——**已经泄漏**。

### 4.3 替代方案：用 DAG 决定角色，而不是用 p 值决定去留

这是回答导师"不应该一开始就假定什么影响心血管"的**正解**，而且是可以当场说服人的一句话：

> **我们不是假定什么影响心血管。我们是先把因果结构假设显式画出来（DAG），让 DAG 决定每个变量在模型里扮演什么角色。这个假设是写下来的、可被反驳的、可做敏感性分析的——这比"不做假设"更科学，因为"不做假设"的模型其实隐含了一个更强、更没根据的假设：所有变量地位相同。**

具体做法：用 `dagitty` 画一张 DAG，把每个候选变量归入四类之一：

| 角色 | 处理方式 | 例子 |
|---|---|---|
| **混杂 confounder** | 必须调整 | 年龄、性别 |
| **中介 mediator** | **不能**与暴露同时放进一个模型再逐个解释系数（Table 2 fallacy）；要分层报告 total effect vs direct effect | 收入 → BMI → CVD 中的 BMI |
| **对撞 collider** | **绝不能**调整 | 某些结构下的"是否服药" |
| **纯预测因子** | 预测模型可放，因果模型不放 | — |

**关键提醒**：当前所有模型都把 19 个变量平铺进去然后用 SHAP 解释每一个——这就是标准的 **Table 2 fallacy**。SHAP 里 `hypertension_flag` 排第二（mean_abs_shap 0.4513），但高血压既可能是 CVD 的原因，也可能是同一批人被更密集监测的结果；`systolic_bp_avg` 又同时在特征集里，两者互为中介/混杂。这些系数**不能各自作因果解释**。

### 4.4 缺失的关键变量清单（对导师质疑的直接回应）

从 `data/download.py:80-83` 的 17 个 module 看，以下重要变量**从未进入候选池**：

| 模块 | 内容 | 为什么重要 |
|---|---|---|
| **RXQ_RX** | 处方药 | **最关键**。他汀/降压药是解决 §6.1 治疗效应偏倚的必需品 |
| **MCQ300A/B/C** | 一级亲属早发心脏病史 | Framingham 核心变量之一，当前完全缺失 |
| **ALQ** | 饮酒 | J 型关联，经典混杂 |
| **HIQ** | 医保 | **equity 分析的关键混杂**——直接影响"是否被诊断"（见 §7.2） |
| **SLQ** | 睡眠时长 / 呼吸暂停 | 与 CVD 强关联 |
| **DR1TOT** | 膳食总量（person-level，非 food-level） | 钠、饱和脂肪、能量 |
| **ALB_CR / KIQ** | 尿白蛋白肌酐比 / 肾病 | CKD 是 CVD 风险倍增因子 |
| **CDQ** | Rose Angina Questionnaire | **可构造比自报诊断更客观的心绞痛定义**（见 §7.3） |
| **PBCD / UHM** | 血铅镉 / 尿金属 | 环境暴露与 CVD——**这一类才是"不预设就可能发现"的东西** |
| **OHXDEN** | 牙周 | 有文献关联，属"隐藏因果"的典型例子 |
| DEMO 未用列 | DMDBORN/DMDCITZN/DMDMARTL | 已下载但没进 staging |

最后两行正是导师担心的场景：**如果你一开始就按"已知 CVD 危险因素"筛，你永远发现不了牙周或重金属。** 这也是 §1.1 的 Stage 0 全量普查必须做的原因。

### 4.5 缺失值：当前是最弱的一环

**现状**：`src/model.py:44-50` 数值用 median、类别用 most_frequent 单一插补。插补器封在 `Pipeline` 里所以**每折内重做**——这一点是对的，保留。

但有三个层级的问题：

1. **单一插补低估方差** → 置信区间过窄，p 值过乐观。
2. **MCAR 假设站不住，而且有些缺失是设计性的**：
   - `fasting_glucose`（`stg_risk_factors.sql:77`，来自 LBXGLU）只在**空腹晨检子样本**采集，有专门的子样本权重 `WTSAF2YR`。用全样本中位数填它是**结构性错误**——不是"填得不准"，是"填了一个不存在的量"。
   - `ldl_cholesterol`（`stg_risk_factors.sql:67`，LBDLDL）同样只在空腹子样本。
   - `crp` 见 §3.3。
3. **插补模型必须包含结局变量和设计变量**，否则会系统性削弱变量与结局的关联（把估计推向零）。

**修法**：
- 空腹相关变量（GLU、LDL、TRIGLY）：从主分析移出，或改用空腹子样本 + `WTSAF2YR` 单独建一个次要分析。
- 其余：MICE 多重插补，m = 10~20，Rubin's rules 合并。Python 用 `sklearn.IterativeImputer` 可行但 diagnostics 弱，`statsmodels.imputation.mice` 或直接调 R 的 `mice` 更稳。
- 报告 missing pattern 图 + complete-case vs imputed 的敏感性对比。

---

## 5. 统计推断层

### 5.1 权重合并规则不完全正确

**现状**：`dbt/models/mart/mart_cv_master.sql:35` 用 `survey_weight_2yr / n_cycles`，`n_cycles = COUNT(DISTINCT cycle) = 11`。

从数据算 n_cycles 而不硬编码——这个工程判断好，保留。但统计上有两个漏洞：

1. **1999-2002 需要 4 年权重**。NHANES 官方指导明确：1999-2000 与 2001-2002 合并分析时应使用 `WTMEC4YR`，不能简单除以周期数，因为这两轮抽样设计与之后不同。当前代码一视同仁。
2. **2021-2022 不是标准 2 年周期**。它实际是 August 2021–August 2023，响应率显著低于历史水平，NCHS 对它附了单独的分析说明并**警告与之前周期合并需谨慎**。当前代码把它当成第 11 个普通周期。

**修法**：查 NHANES Analytic Guidelines 对每一段周期的官方权重指引，写成一张显式的 `cycle → weight_var → pooling_divisor` 映射表放进 dbt，而不是一条除法。这张表本身就是给导师看的论证材料。

### 5.2 【严重】没有任何置信区间

`reports/results.json` 里 **全部是点估计**，一个 CI 都没有。

而 `src/analysis.py:11-13` 的 docstring 自己承认了：

> "Design-based standard errors would additionally use the strata/PSU columns via a Taylor-series or replicate-weight estimator; we retain those columns in the mart so that refinement is a drop-in."

**承认了该做但没做。** 后果：8.67% vs 9.61%（post 组 n = 7,809）这个差异**无法判断是否显著**，所有 equity 的组间比较也一样。

**修法**（按可信度排序）：
1. **R 的 `survey` 包（`svydesign` + `svyby` + `svyciprop`）** ——领域金标准，导师和审稿人都认。Python 侧用 `rpy2` 或直接把 mart 导成 CSV 在 R 里跑。
2. Python 的 `samplics` 包，支持 Taylor linearization。
3. 自己实现 linearized variance——不建议，容易错且没人信。

设计变量已经在 mart 里（`mart_cv_master.sql:30-32` 的 `psu` / `strata`），接上去就行。

### 5.3 【严重】没有年龄标准化

25 年间美国成人年龄结构显著老化。CVD 患病率随年龄陡升——SHAP 里 `age` 的 mean_abs_shap 是 **1.2505**，第二名 `hypertension_flag` 才 0.4513，差 2.8 倍。

> **不做年龄标准化的患病率趋势，主要反映的是人口老化，不是心血管健康的变化。**

NCHS 自己发布趋势时一律用 age-adjusted rate（direct standardization to 2000 US standard population）。

这条如果导师是流行病学背景，会是他问的第一个问题。修法成本很低：加一个直接标准化函数，同时报 crude 和 age-adjusted 两条线。

### 5.4 COVID 对比：识别策略不成立

**现状**：`mart_cv_master.sql:89-92` 把 2021-2022 标为 `post_pandemic`，其余 10 个周期全标 `pre_pandemic`；`src/analysis.py:81-97` 按这两组算加权均值。

**三个问题**：

1. **"pre" 组是 1999–2018 的 10 个周期混合**，代表的是"过去 20 年的平均人口"。拿它和 2021-2022 比，差异里混着 **20 年的长期趋势**。从 results.json 可以直接算：1999-2000 是 8.10%，2021-2022 是 9.61%，25 年涨 1.51 个百分点——而"COVID 效应"报的是 8.67%→9.61%，即 0.94 个百分点。**这 0.94 里有多少是趋势、多少是 COVID，当前设计无法区分。**
2. **血压那一项被仪器换代完全混杂**（§3.1）。
3. **没有年龄标准化**（§5.3），人口老化也算进了"COVID 效应"。

**修法**（按强度递增）：

| 方案 | 做法 | 强度 |
|---|---|---|
| 最低 | 只比相邻周期 2017-2018 vs 2021-2022，并明确说这是描述性对比 | 弱但诚实 |
| 推荐 | **中断时间序列（ITS / segmented regression）**：用 1999–2018 的 10 个点拟合趋势，外推出 2021-2022 的反事实，比较实测与反事实 | 中 |
| 强 | ITS + 年龄标准化 + 仪器校准 + 设计基 CI + 安慰剂检验（对不该受 COVID 影响的结局做同样分析，如身高） | 强 |

**注意一个技术细节**：`covid_period` 分组用 `survey_weight_pooled`（除以 11）。做**组内比例**时分子分母同除常数会约掉，所以数值本身不错；但一旦要报加权人口数或跨组合并方差，这个权重就是错的。改用官方指引的周期特定权重（§5.1）后这个隐患自动消失。

### 5.5 多重比较与预先声明

6 个结局 × 2 个模型 × 6 个种族组 × 11 个周期，**没有任何多重比较处理**。

不必然要 Bonferroni，但**必须区分 primary 和 exploratory**。建议写一份简短的 pre-analysis plan（哪怕是事后写、注明是事后写的），声明：
- Primary outcome：`has_any_cvd`
- Primary analysis：年龄标准化加权患病率趋势 + 设计基 CI
- 其余全部标记 exploratory，不做强推断声明

这一份文件本身就能大幅改善导师对"每个点都没论证"的印象。

---

## 6. 建模层

### 6.1 【最致命】横断面 prevalent 结局，因果方向是反的

结局 MCQ160B/C/D/E/F 问的是"医生**曾经**是否告诉过你你有 X"——是 **prevalent（现患/既往）** 病例。而特征（血压、BMI、血脂、HbA1c、CRP）是**同一次访视**测的。

三个后果，每个都足以推翻"预测"这个定位：

1. **反向因果 / 治疗指征偏倚**
   得过心梗的人在吃他汀 → 总胆固醇更低。所以模型学到的"胆固醇 ↔ CVD"关系被治疗效应污染，方向甚至可能翻转。SHAP 里 `total_cholesterol` 排第 6（0.1477），**这个方向现在根本无法解释**。没有 RXQ_RX（§4.4）就无法诊断这件事。

2. **幸存者偏倚**
   NHANES 只抽非住院人群。心梗当场死亡的、住在医院/养老院的人不在样本里。所以这是"**活下来且住在社区里的** CVD 患者"的画像，不是"谁会得 CVD"。

3. **ROC-AUC 0.86 是虚高**
   `age` 一个变量在横断面 prevalent CVD 上就能拿到 ~0.80。模型主要在学"老年人报告过 CVD 病史"。这不是预测，是**识别已诊断者**。

**必须改口径或改设计，三选一**：

| 路线 | 做法 | 代价 | 论证强度 |
|---|---|---|---|
| **(a) 降级为关联研究** | 不再叫 prediction。指标从 AUC 换成设计基加权 OR + 95%CI。模型换成 survey-weighted logistic regression | 低。改文案 + 换指标 | 中，但**完全站得住** |
| **(b) 改成筛查模型** | 只用**不受治疗影响的先行变量**（age, gender, race, education, PIR, 吸烟史, 家族史），明确定位为 "detection of undiagnosed CVD" 而非 "prognosis" | 中。需下载 MCQ300 家族史 | 中高 |
| **(c) 换成真纵向结局** | 接 **NHANES Linked Mortality File（NDI）**——公开、免费、按 SEQN 对齐、文件很小。可得 CVD 死亡的**时间到事件**结局，做 Cox / 竞争风险模型 | 中高。要学 survival + 复杂抽样 | **高，这是最能救项目的一条** |

**我的建议：(c) 为主线，(a) 为描述性配菜。** Linked Mortality File 几乎不增加内存和工程负担，却把项目从"横断面关联"提升到"纵向预后"，同时自动解决幸存者偏倚里最尖锐的一部分，也让 §6.2 的时序验证变得有意义。

### 6.2 交叉验证与抽样设计不匹配

**现状**：`src/model.py:133` 用 `StratifiedKFold(shuffle=True)`。

NHANES 是**分层多阶段整群抽样**——同一个 PSU 内的个体不独立（同社区、同医疗可及性、同环境）。随机打散会把同一 PSU 的人分到训练和测试两边，造成**乐观偏倚**。

**修法**：
- 最低：`StratifiedGroupKFold`，`group = strata × psu`。设计变量已在 mart（`mart_cv_master.sql:31-32`）。
- 更好：**按周期做时序外推验证**（train 1999–2016，test 2017-2018 + 2021-2022）。这才回答"模型能不能推广到未来人群"，而且直接呼应你的 25 年时间跨度卖点。

### 6.3 【README 与实现不符】模型根本没用权重

- README.md:6 写 "trains **survey-weighted** machine-learning models"。
- 实际：`run_pipeline.py:138` 调 `M.train_target(df, oc, feats, cat, cv_folds=5)`，没有传权重；`src/model.py` 全文**没有任何 `sample_weight`**。
- 评估指标（`model.py:96-106`）也全部是未加权的。

**这意味着模型是对"NHANES 样本"训练和评估的，metrics 不能外推到美国人群。README 这句话是不实陈述，导师一查代码就穿帮。**

**修法，二选一并写清楚理由**：
- **加权**：`pipe.fit(X, y, model__sample_weight=w)`；`roc_auc_score` / `average_precision_score` 都支持 `sample_weight`。注意加权会增大方差。
- **不加权**：明确写"模型层不加权（加权 ML 的方差代价 > 收益），仅描述统计加权；因此模型性能是样本层结论，不作人群外推"。

哪个都行，**但必须选一个并在 README 里说实话**。

### 6.4 阈值选择泄漏

`src/model.py:141-143`：在**全部 CV 预测**上选最大化 F1 的阈值，然后用**同一份预测**报告 F1。

阈值是一个从数据里学来的参数，在测试集上选它再在测试集上报告 → **F1 系统性乐观**。

**修法**：阈值选择放进内层 CV（嵌套 CV），或者干脆只报阈值无关的指标（PR-AUC、ROC-AUC）+ 一个**预先声明**的阈值（如按人群患病率定）。

### 6.5 【内在矛盾】class_weight 与"风险分"不能共存

- `src/model.py:57-81` 用 `class_weight='balanced'` / `scale_pos_weight` 处理不平衡。
- `src/model.py:198-200` `compute_risk_score()` 把预测概率 ×100 当作 0–100 风险分。

**这两件事互斥。** `scale_pos_weight` 会系统性破坏概率校准——输出的不再是校准过的概率，而是被人为抬高的分数。所以这个"风险分"**没有临床意义**。

而且**整个项目没有任何校准评估**：没有 calibration plot，没有 Brier score。风险模型的第一评价维度是校准，不是判别（AUC 高但校准差的模型临床上有害）。

**修法**：
- 若目标是排序/筛查 → 保留 `scale_pos_weight`，**删掉 `compute_risk_score`**，只谈排序性能。
- 若目标是风险估计 → 去掉重加权，用 `CalibratedClassifierCV`（isotonic 或 Platt），报 calibration curve + Brier score + calibration slope/intercept。

README.md:27 的"No SMOTE"论证是对的（SMOTE 会伪造少数类、扭曲流行病学患病率），**保留这条**，它是全 README 里第二扎实的论证。

### 6.6 类别编码：`race_ethnicity` 被当成有序数值

`src/model.py:49` 对所有类别变量用 `OrdinalEncoder`。

`race_ethnicity` 是**无序**类别。对树模型影响有限（能靠多次分裂近似），但对 **Logistic Regression 是错的**——强加了一个不存在的线性顺序（Mexican American=0 < Other Hispanic=1 < ... 这种序在数学上被当真了）。

而 SHAP 里 `race_ethnicity` 排第 7（0.1469），这个数值在当前编码下**不可解释**。

**修法**：LR 用 one-hot；XGBoost 用原生 `enable_categorical=True` + pandas category dtype。`education_level` 是有序的（DMDEDUC2），可以保留 ordinal，但要在文档里说明这个区别是有意的。

### 6.7 超参数完全硬编码且未调优

`src/model.py:57-81`：`n_estimators=400, learning_rate=0.05, max_depth=4, subsample=0.8, ...`，`LogisticRegression(C=0.1)`。

没有任何调优，也没有说明这些值从哪来。导师问"为什么 max_depth=4 不是 6"，现在没有答案。

**修法，二选一**：
- 嵌套 CV 调优（外层评估、内层选参），报告调优空间。
- 或者诚实写"采用文献常用默认值，未做调优；调优对本任务的边际收益有限（可用一次小规模实验佐证）"。

### 6.8 没有与已有临床评分对比

导师/审稿人必问："你比 Framingham Risk Score / ASCVD Pooled Cohort Equations 好在哪？"

这两个评分的输入变量 NHANES 基本都有。加一个 baseline 对比列，是**性价比最高的一项加分**——它把项目从"我训了个 XGBoost"变成"我评估了现有工具在当代美国人群中的表现"。

---

## 7. 结局效度：可能推翻 equity 结论

### 7.1 自报诊断的误分类，而且是差异性的

MCQ160B/C/D/E/F 全部是**自报的医生诊断**。已知性质：
- 与病历核对，自报 CHD 的敏感性约 60–80%，特异性 > 95%。
- **未被诊断者被归为"无病"** → 结局误分类。
- 关键在于：**这个误分类与暴露相关**。低收入、无医保、就医频率低的人更不容易被诊断 → **差异性误分类** → 会**系统性低估**社会经济和种族梯度。

### 7.2 因此 equity 结论现在的写法是危险的

`reports/results.json` 报告 2021-2022 各族裔 any-CVD：

```
Other/Multiracial 10.87 · Non-Hispanic White 10.85 · Non-Hispanic Black 9.21
Other Hispanic 7.75 · Mexican American 5.37 · Non-Hispanic Asian 4.74
```

按已知流行病学，Non-Hispanic Black 的 CVD 负担通常**高于** Non-Hispanic White。这里反过来了。最可能的解释是**诊断可及性差异**，不是真实患病率差异。

> 把"Non-Hispanic Asian 4.74%，最低"作为 Key Finding 写进 README（README.md:14）而不加限定，**是一个可能被直接判为错误结论的陈述**。

**必须做的补救**：
1. 下载 **HIQ（医保）** 并作为混杂调整/分层变量。
2. 加入**客观测量的**结局做交叉验证：血压测量值、糖化血红蛋白等——比较"自报高血压"与"测量高血压"的差距在各族裔间是否不同。这个差距本身就是**诊断可及性的直接度量**，是一个很漂亮的分析。
3. Key Finding 的措辞改为"自报医生诊断的 CVD 患病率"，并明确写出误分类方向。

### 7.3 替代结局（也是"漏掉的变量"的最佳例证）

| 来源 | 内容 | 价值 |
|---|---|---|
| **CDQ 模块**（1999–2012） | Rose Angina Questionnaire | 可构造**症状学定义的**心绞痛，不依赖是否看过医生。直接检验 §7.1 |
| **Linked Mortality File**（NDI） | CVD 死亡 + 随访时间 | 硬结局，见 §6.1(c) |
| 部分周期的 ECG | 客观心电异常 | 覆盖有限，可作敏感性分析 |

CDQ **当前完全没下载**（不在 `data/download.py:80-83` 的清单里）——这就是导师说的"先筛就会漏掉"的一个**真实、具体、可举证**的例子。

### 7.4 五个结局的内部重叠

MCQ160C（coronary heart disease）、MCQ160D（angina）、MCQ160E（heart attack）在受访者理解中高度重叠，一致性差。把它们当作 5 个独立结局分别建模、分别报 AUC，暗示了一种它们不具备的独立性。

**建议**：primary 只报 `has_any_cvd`，其余四个降为 exploratory 并报告两两 kappa。

---

## 8. 数据处理层的具体缺陷

### 8.1 【bug】复合结局把"不知道"当成了"没有"

`dbt/models/staging/stg_cardiovascular.sql:16-26`：

```sql
CASE
    WHEN GREATEST(recode(mcq160b), ..., recode(mcq160f)) = 1 THEN 1
    WHEN COALESCE(mcq160b, mcq160e, mcq160c, mcq160d, mcq160f) IS NULL THEN NULL
    ELSE 0
END AS has_any_cvd
```

第二个 `WHEN` 用的是**原始列**，不是 recode 后的值。而 `recode_cvd`（`dbt/macros/recode_cvd.sql:4`）把 7/9 → NULL。

于是：某人 `mcq160b = 9`（Don't know）、其余全 NULL → `COALESCE` 返回 9（非 NULL）→ 落到 `ELSE 0` → **`has_any_cvd = 0`**。

> **"拒答"和"不知道"被静默编码成了"没有心血管病"。**

影响量级不大（MCQ 的 7/9 通常 < 1%），但这是一个**可当场演示的逻辑错误**，修起来只要几行：把 `COALESCE` 里的原始列换成 recode 后的表达式（或先建一个 CTE 存 recode 结果，避免宏被展开五次）。

顺带：`mart_prevalence.sql:39` 的 `WHERE has_any_cvd IS NOT NULL` 依赖这个字段，错误会传导下去。

### 8.2 【bug 级设计缺陷】主表用 INNER JOIN，样本静默流失

`dbt/models/mart/mart_cv_master.sql:94-96`：

```sql
FROM stg_demographics d
JOIN stg_cardiovascular cv USING (seqn, cycle)   -- INNER
JOIN stg_risk_factors   rf USING (seqn, cycle)   -- INNER
```

没做 MCQ 问卷的人**直接从主表消失**，而且**没有任何记录**。这是**非随机流失**——未完成问卷的人往往更病重、更少受教育、或语言障碍。

**必须做**：
1. 改成 LEFT JOIN（或至少先用 LEFT JOIN 统计流失量）。
2. 产出一张 **STROBE participant flow diagram**：
   ```
   总受访者 → 年龄 ≥20 → 有 MEC 权重 > 0 → 有 MCQ 记录 → 有 ≥1 个结局非缺失 → 最终分析样本
   ```
   每一步标出 n 和排除原因。
3. 比较被排除者与保留者在年龄/性别/种族/PIR 上的分布差异。

**这是导师会直接开口要的东西**，而且是所有观察性研究报告规范（STROBE）的强制项。当前 62,890 这个数字**没有任何审计链**。

### 8.3 吸烟编码丢掉了既往吸烟史

`dbt/models/staging/stg_risk_factors.sql:55-61`：

```sql
WHEN sm.smq040 IN (1, 2) THEN 1   -- current smoker
WHEN sm.smq020 = 1       THEN 0   -- former smoker  ← 和 never 同为 0
WHEN sm.smq020 = 2       THEN 0   -- never smoker
```

**既往吸烟者和从不吸烟者被合并成同一类。** 既往吸烟是 CVD 的独立危险因素，风险在戒烟后需要十年以上才接近从不吸烟者。这样编码丢掉了实质信息，而且会**稀释**吸烟的效应估计。

**修法**：三分类（never / former / current）。进一步可以用 SMD030（开始年龄）+ SMQ050Q（戒烟时长）+ SMD650（日吸量）构造 **pack-years**，这是文献标准做法，也是一个很好的"我做了细致处理"的展示点。

### 8.4 borderline diabetes 直接当成"无"

`stg_risk_factors.sql:47`：`WHEN diq.diq010 = 3 THEN 0  -- borderline → treat as no`

有注释，比无注释好，但**缺少论证和敏感性分析**。DIQ010=3（borderline/prediabetes）人群的 CVD 风险介于两者之间。

**修法**：至少做一次敏感性分析（borderline 归 1 / 归 0 / 单列一类），报告结论是否稳健。三行代码的事，换来一句"我们检验过这个编码决策"。

### 8.5 血压均值：把首次读数也算进去了

`stg_risk_factors.sql:11-25` 对 BPXSY1/2/3 取可得值的平均。

NHANES 与 AHA 的常规做法是**丢弃第一次读数**（白大衣效应，第一次系统性偏高），用第 2、3 次的均值。当前实现把三次全平均，会系统性高估血压。

**修法**：主分析用 mean(BPXSY2, BPXSY3)，把 mean(1,2,3) 作为敏感性分析。同样是几行代码，但这正是"每个点都能解释得通"的那种点。

### 8.6 `hypertension_flag` / `diabetes_flag` 的缺失逻辑不对称

`mart_cv_master.sql:71-84`：

```sql
-- hypertension_flag 的 NULL 分支只检查 systolic_bp_avg 和 hypertension_diagnosed
WHEN rf.systolic_bp_avg IS NULL AND rf.hypertension_diagnosed IS NULL THEN NULL
```

但阳性分支用了**三个**条件：`systolic_bp_avg >= 130 OR diastolic_bp_avg >= 80 OR hypertension_diagnosed = 1`。

于是：某人只有舒张压（收缩压缺失）、且 dbp < 80、且未诊断 → 落到 `ELSE 0`，**被判为无高血压**，尽管收缩压未知。逻辑不对称。

`diabetes_flag` 的三条件 NULL 检查是对称的（`:81-83`），说明这是 hypertension 那一支写漏了。

---

## 9. 三条可选路线（按投入排序）

### 路线 A：最小可辩护版（约 1–2 周）

目标：**不改变研究范围，把每个决策补上论证，删掉不实陈述。**

1. 写 estimand 声明 + pre-analysis plan（primary/exploratory 划分）
2. STROBE flow diagram（§8.2）
3. 设计基 CI（R survey 包）（§5.2）
4. 年龄标准化（§5.3）
5. 修 `has_any_cvd` bug（§8.1）、吸烟三分类（§8.3）、血压去首读（§8.5）、hypertension_flag 对称（§8.6）
6. 移除 CRP（§3.3）与空腹变量（§4.5）出主分析
7. 模型定位改为"识别已诊断 CVD 的关联模型"，指标改 OR + CI（§6.1a）
8. 删 `src/features.py` 或接进流水线，README 改口（§4.1）
9. README 删掉 "survey-weighted ML" 的不实表述（§6.3）
10. 数据 manifest + hash（§1.3）

### 路线 B：标准研究版（约 4–6 周，推荐）

路线 A 全部 + ：

11. **Stage 0 全量变量普查**（§1.1）——这是对导师质疑的正面回答
12. **DAG**（dagitty），变量按角色分类（§4.3）
13. 补关键模块：**RXQ_RX、MCQ300、HIQ、ALQ、CDQ**（§4.4）
14. **血压桥接校准**（用 2017-2018 双测数据）（§3.2）+ 修 ETL 的 combine_first 顺序
15. **ITS 分析**替代 pre/post 二分（§5.4）
16. MICE 多重插补（§4.5）
17. `StratifiedGroupKFold` by PSU + 按周期时序外推验证（§6.2）
18. 校准评估（calibration curve + Brier）（§6.5）
19. equity 分析加入医保调整 + "自报 vs 测量"差距分析（§7.2）
20. dbt tests（当前 `sources.yml` 无任何断言，`dbt build` 绿只代表编译通过）

### 路线 C：强论证版（约 2–3 个月）

路线 B 全部 + ：

21. **接 Linked Mortality File**，做 CVD 死亡的 Cox / 竞争风险模型（§6.1c）——**单项收益最大**
22. 与 Framingham / ASCVD PCE 基准对比（§6.8）
23. Rose Angina（CDQ）作为替代结局的完整敏感性分析（§7.3）
24. 未测量混杂的 E-value 敏感性分析
25. 环境暴露（PBCD/UHM）等假设生成型探索，明确标 exploratory

---

## 10. 如果导师只有 10 分钟，先准备这五个答案

| 他会问 | 现在的问题 | 你要能说的 |
|---|---|---|
| "你怎么选的变量？" | 三层漏斗是死代码（§4.1），实际是手写常量表 | Stage 0 全量普查 + 规则化 A/B/C 三类筛选 + DAG 定角色（§1.1、§4.3） |
| "你的模型预测什么？" | 横断面 prevalent 结局，因果方向反了（§6.1） | 要么降级为关联，要么接 Linked Mortality File 做真纵向 |
| "COVID 那个差异是 COVID 造成的吗？" | pre 组混了 20 年趋势 + 血压被仪器换代完全混杂（§5.4、§3.1） | ITS + 年龄标准化 + 仪器桥接校准 |
| "亚裔患病率最低，你信吗？" | 差异性误分类，很可能是诊断可及性（§7.2） | 加医保调整 + "自报 vs 测量"差距分析 |
| "你的 8.1%→9.61% 显著吗？" | 没有任何 CI（§5.2） | 设计基 Taylor linearization（R survey） |

---

## 11. 一句话总结

> 这条流水线的**工程质量**明显高于它的**研究质量**。工程侧（Docker + dbt + 可复现 Makefile + 确定性下载器）是加分项，保留。研究侧目前缺三样东西：**estimand、识别假设、不确定性量化**。补齐这三样，同一份数据可以支撑一篇站得住的论文；不补，再多的 AUC 也只是把 age 这一个变量包装了六遍。

---

_审查基于 commit `632e92e`。所有 file:line 引用对应该 commit 的工作区状态。_
