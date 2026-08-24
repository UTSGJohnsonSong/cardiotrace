# ASCVD PCE 基准对比 —— 系数来源与设计修正

> 状态：系数已取得并核验；**三层拆解的设计需要修正**（见 §2）。
> ⚠️ **PCE 已不是当前临床标准**（2026-08-22 核实，见 §0）——本项目仍按预先设定的历史基准保留 PCE，
> PREVENT-ASCVD 记为当前标准与未来比较对象。
> 决策记录以 `research-design.md` 的决策表为准，这份只做本议题的展开。

---

## 0. ⚠️ PCE 已不是当前临床标准（2026-08-22 核实）

| | 现状 |
|---|---|
| **当前推荐** | AHA **PREVENT-ASCVD** 方程。2026 ACC/AHA/Multisociety 血脂管理指南以 10 年 PREVENT-ASCVD 风险为起点；2025 ACC/AHA 高血压指南亦推荐用 PREVENT 取代 PCE |
| **PCE 的地位** | ACC 自家的 CVD Risk Estimator Plus 明示：用 pooled cohort equation 算出的 10 年 ASCVD 风险 "is no longer supported by ACC clinical policy or guidelines"，并指向 2026 血脂指南的 PREVENT 模型 |

**本项目的处理 —— 保留 PCE，但改称谓：**

1. PCE 由「the risk tool in clinical use」降为**预先设定的历史基准**（prespecified historical benchmark）。§3.5 锁定的四条协议、系数转抄与核验都在指南更新之前完成；事后换比较对象，等于看着答案改设计。
2. **PREVENT-ASCVD 写为当前标准与未来比较对象**，不是本轮工作。它不是 PCE 的即插即用替代：需要 eGFR、去掉种族输入、年龄下探到 30 岁、结局口径也不同（PREVENT 另有 total CVD 与 HF 模型）。换过去是新工作量，不是改个名字。
3. §2 与 §3.5 的结局口径论证**不受影响**：PCE 结局仍是 hard ASCVD，本项目 Part 3 仍只有 CVD 死亡。这一条与指南更新无关。

**出处**（2026-08-22 取得）：

- ACC CVD Risk Estimator Plus <https://tools.acc.org/cvd-risk-estimator-plus/> —— 上表引文直接取自该页
- 2026 ACC/AHA/Multisociety Guideline on the Management of Dyslipidemia, *Circulation* —— <https://www.ahajournals.org/doi/10.1161/CIR.0000000000001423>（**DOI 由检索结果 URL 取得，原文 403 未能直取；正式引用前需核对**）
- Implementing the PREVENT Risk Equation in the 2025 Guideline for the Prevention, Detection, Evaluation, and Management of High Blood Pressure in Adults, *Hypertension* —— <https://www.ahajournals.org/doi/10.1161/HYPERTENSIONAHA.125.25465>（同上，未直取）

---

## 1. 系数来源与核验

**来源**：2013 ACC/AHA Guideline on the Assessment of Cardiovascular Risk,
**Full Work Group Report, Table 4, pp.32–33**
（"Equation Parameters of the Pooled Cohort Equations for Estimation of 10-Year Risk for Hard ASCVD"）
取自 ACC 自托管 PDF：`jaccjacc.cardiosource.com/acc_documents/2013_FPR_S5_Risk_Assesment.pdf`，2026-08-18 取得。

> 注：`ahajournals.org` 与 `heart.org` 的同一文档均返回 403，无法直取。上述 ACC 域名是官方托管，非第三方镜像。

**落地**：`data/reference/pce_coefficients.csv` —— 4 组 × （13 系数 + 2 参数）= 60 行。

**核验方式**：Table 4 为四个组各印了**同一个人的算例**（55 岁、TC 213、HDL-C 50、未服药 SBP 120、不吸烟、无糖尿病）及其应得的 Individual Sum 与 10 年风险。`tests/test_pce_reference.py` 用这四个已发表答案反查我们的转抄，10 个测试全过：

| 组 | Individual Sum（原文 / 复算） | 10 年风险（原文 / 复算） |
|---|---|---|
| White women | −29.67 / −29.68 | 2.1% / 2.07% |
| AA women | 86.16 / 86.17 | 3.0% / 3.00% |
| White men | 60.69 / 60.70 | 5.3% / 5.33% |
| AA men | 18.97 / 18.97 | 6.1% / 6.06% |

---

## 2. 🔴 结局口径不匹配 —— 这会污染三层拆解的归因

Table 4 脚注对结局的定义是逐字的：

> *Defined as first occurrence of nonfatal MI or CHD death, or fatal or nonfatal stroke.

| | 结局 |
|---|---|
| **PCE** | hard ASCVD = **非致死性心梗** + 冠心病死亡 + **致死及非致死性中风** |
| **CardioTrace Part 3** | CVD 死亡（UCOD ∈ {1,5}），**只有死亡** |

原三层拆解（原系数直接套 / 同变量集重拟合 / 全变量集）的目的，是把性能差异归因到
**人群漂移 · 变量集 · 模型形式**三者。结局口径是**第四个来源，且与这三个全部混杂**。

后果是具体的：第一层必然出现大幅系统性高估，因为 PCE 预测的是一个严格更宽的复合结局。
若照原设计出图，读者（和我们自己）会把这个高估读成"PCE 在这个人群失效"或"人群漂移大"，
**而它其实只是定义差异**。

### 修正后的分层

| 层 | 做什么 | 隔离出什么 |
|---|---|---|
| **1a** | 原系数 + 原基线生存，直接套 | 定义性差异。**预期高估，这是应报告的已知结果，不是 PCE 失败** |
| **1b** | 原系数，基线生存**重校准到本队列** | 线性预测子的排序与形状是否迁移（去掉结局尺度差异） |
| **2** | 同变量集，在本队列重拟合 | 人群漂移 + 结局定义的合并效应 |
| **3** | 全变量集（本项目的模型） | 变量集与模型形式的增量 |

**主指标用区分度**（C-index / 时依 AUC）：它对预测风险的任何单调变换不变，
因此**跨结局口径可比**。校准则不可直接比，只在 1b 之后比。

> **这条是我替你定的，可驳回**（沿用 `research-design.md` §S.4 的约定）。
> 替代方案是只做 1b–3、完全不报 1a；我不建议，因为 1a 的高估本身就是一个诚实且说得清的结果。

---

## 3. 转抄陷阱（都已踩过，记录备查）

1. **`Ln` 与 `Log` 在 Table 4 里是同一个东西。** 女性行印作 `Ln Age`，男性行印作 `Log Age`，
   但脚注 † 统一定义为 "the natural log of the value"。按字面区分会错。
2. **`pdftotext` 默认输出把减号、乘号、连字符压成同一个 `�`**，
   `Ln Age�Ln` 是乘号而 `�29.799` 是减号。必须 `-enc UTF-8` 重抽。
   本文件的数字全部来自 UTF-8 抽取结果。
3. **风险值对线性预测子的舍入极敏感。** 原文把 Individual Sum 印到两位小数，
   `exp()` 会放大：white men 用 60.69 得 5.34%，用 60.70 得 5.39%。
   测试因此分成两条断言，见 `tests/test_pce_reference.py` 的模块 docstring。

**原文自身的笔误（不影响数字）**：Table 4 缩写表把 CHD 写作 "congestive heart disease"，
应为 coronary heart disease。

---

## 3.5 🔒 对比协议 —— 2026-08-19 用户锁定

导师审阅后给出四条约束。**在这四条落实之前不开工。**

### ① 族裔：主分析只做两组

**主分析限定 non-Hispanic White 与 non-Hispanic Black。** 其他族裔套用 White 方程
**只能作为明确标注的敏感性分析**，不进主结果。

理由：PCE 本来就是为 White / Black、40–79 岁人群建立的，指南对其他族裔的建议是
Grade E / COR IIb —— 证据等级最低的一档。把它当主分析等于替指南做了它自己不敢做的外推。

📍 [2013 ACC/AHA 指南](https://www.ahajournals.org/doi/10.1161/01.cir.0000437741.48606.98)

### ② 缺失：完整病例，但**本项目模型必须在同一子样本上重新评估**

用 PCE 九项输入齐全的完整病例（约 17,464 人 / 756 事件）。

**关键约束**：不能拿主队列上得到的 C（加权 0.838，未加权 0.804）直接和 PCE 在这个子样本上的表现比。
**必须在同一个 17,464 人子样本上重新拟合并评估本项目的模型**，否则比的是两个不同人群，
差异里混进了「谁被排除了」这个来源。

> 这一条容易被忽略，因为两个数字都叫「C-index」，摆在一起看不出问题。

### ③ 血压：喂 PCE 原始观测值，不喂 Tobin 校正值

PCE 的正式变量定义是**实测 SBP + 治疗状态**，方程自带 treated / untreated 两条分支。
本项目的 Tobin 校正（给服药者 +10 mmHg）是为**病因估计**设计的，目的是还原未治疗暴露；
把它喂给 PCE 等于同一件事做了两遍，且与该方程的定义不符。

📍 [ACC ASCVD Risk Estimator Plus](https://tools.acc.org/cvd-risk-estimator-plus/)

### ④ 🔴 终点不一致 —— 最根本的一条

PCE 预测**首次 ASCVD**：非致死性心梗 + 冠心病死亡 + 致死或非致死性卒中。
本项目 Part 3 只有 **CVD 死亡**链接。

**因此不能做严格的校准头对头。** 定位必须降级为：

- 称作 **prognostic benchmark**，不称 head-to-head validation
- **主要比较 discrimination**（对预测风险的单调变换不变，可跨口径）
- **不得宣称比较了同一个风险终点**

§2 提出的 1a / 1b 分层仍然有用，但它解决的是「基线生存该不该重校准」，
**解决不了终点定义本身不同**。这一条只能靠措辞诚实，不能靠方法修补。

---

## 4. 尚未决定 / 待办

- 种族映射：指南只给 White 与 African American 两套方程，并建议其他族裔用 White 方程
  （Recommendation 2，Grade E / COR IIb）。本队列含相当比例的 Mexican American 与 Other，
  **映射规则未定**，且这个选择会直接影响对比结论 —— 需要单独决定并写进决策表。
- PCE 九项输入齐全的子样本为 17,464 人 / 756 事件（见 `meeting-03-followup.md`），
  与主队列 20,736 / 925 不同。**对比必须在同一子样本内做**，否则样本差异又混进来一个来源。
- 服药血压：本项目病因模型用 Tobin 校正（+10/+5），**但 PCE 有自己的 treated/untreated 分支**。
  套用 PCE 时必须走 PCE 的分支，不能喂 Tobin 校正后的值。
