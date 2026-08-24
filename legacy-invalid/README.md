# `legacy-invalid/` — 被取代的流水线，保留但不运行

> **这里的东西不参与任何默认构建。** `make all` 不碰它，`pytest` 不导入它，
> 没有一个还在维护的脚本 import 它。
> 保留的原因是它产出过对外发布的数字——删掉就没法回答「那些数是怎么来的」。

## 为什么是 invalid，不是「旧版本」

区别是重要的：这不是一条能跑出稍差结果的老路，是一条**跑出的结果不该被相信**的路。

| 缺陷 | 后果 |
|---|---|
| `data/download.py` 硬编码 17 个模块名，404 静默跳过 | 1999–2004 三个周期**零实验室数据**，15,332 人（24.4%）的化验值被中位数填补，然后当作实测值进模型 |
| `src/model.py` 用 XGBoost + SHAP 做横断面「预测」 | 结局是**自报现患 CVD**，暴露和结局同时测量。这不是预测，是把当前状态回归到当前状态；反向因果无法排除 |
| `src/analysis.py` 的加权均值不带设计方差 | 全部是点估计，一个设计基区间都没有 |
| 「COVID 效应」= 2021-2022 对 1999–2018 十周期混合 | 差异里混着 20 年长期趋势。实测：25 年涨 1.51 个百分点，报出的「COVID 效应」是 0.94 个百分点——分不开 |

诊断全文见 [`docs/methodology-review.md`](../docs/methodology-review.md)（`632e92e` 的历史快照）。

## 里面是什么，被谁取代

| 这里 | 取代它的 |
|---|---|
| `run_pipeline.py` | `scripts/build_cohort_results.py` · `build_descriptive_results.py` · `build_learning_results.py` · `fit_survival_models.py` · `render_report.py`（各自单独可跑，各自有测试） |
| `data/download.py` | `data/download_from_catalog.py`（catalog 驱动，404 报错退出，写 SHA-256 manifest） |
| `src/model.py` | `src/models.py`（病因特异 Cox × 2 → CIF，按周期前向验证） |
| `src/analysis.py` | `src/descriptive.py`（Taylor 线性化 + 设计自由度 t 分位） |
| `src/features.py` | `src/screening.py`（设计基 Wald 前向选择） |
| `scripts/build_notebooks.py` | 无。它生成的四份 notebook 是上面三个模块的叙事层，模块作废则 notebook 作废 |
| `artefacts/results.json` | `reports/descriptive_results.json` · `reports/model_results.json` · `reports/tables/` |
| `dashboard/data/*.csv` | `data/tableau/cardiotrace_prevalence.csv`（见 [`docs/tableau-dashboard.md`](../docs/tableau-dashboard.md)） |

## 曾经的复发路径

`reports/results.json` 之所以危险，不在于它存在，而在于**有一条链会自动把它灌回首页**：

```
make all → analyze → run_pipeline.py → reports/results.json → render_readme.py → README.md
```

`render_readme.py` 已改为读当前产物，`Makefile` 的 `all:` 已不再调 `analyze`。
现在再加一层：这些文件都不在原位了，`make all` 里也没有任何目标指向它们。
**要跑它，得自己 `cd legacy-invalid` 并显式调用**——那是一个刻意的动作，
和「跑一次构建就意外发生」不是一回事。

## 如果真要跑

不建议。真要跑，先把 `reports/` 备份出去，因为这些脚本会覆写产物路径；
且它们 import 的是仓库根的 `src/`，路径已变，需要自己处理。
**跑出来的数字不得进入任何对外页面。**
