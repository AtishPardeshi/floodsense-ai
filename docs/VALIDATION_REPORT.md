# FloodSense AI - Historical Validation Report

**Evaluation Date:** 2026-11-10T09:11:32+00:00  
**Evaluation Standard:** Event-Based Retrospective Historical Replay (No future leakage)

---

## 1. Executive Summary & Core Metrics

| Metric | Operational Amber Threshold ($\ge 0.35$) | Reanalysis Sensitivity Threshold ($\ge 0.10$) | Status / Rationale |
|---|---|---|---|
| **Independent Storm Events** | 6 | 6 | Documented in `incidents.csv` |
| **Storm Event Recall** | **0.0%** (0/6) | **33.3%** (2/6) | Detected multi-spot events |
| **Spot Incident Recall** | **0.0%** (0/14) | **42.9%** (6/14) | Detected spot flood hours |
| **Median Warning Lead Time** | **N/A** | **870.0 min** | Advance warning before onset |
| **Eligible Positive Hours (1)** | 42 | 42 | Documented flood windows |
| **Eligible Negative Hours (0)** | 0 | 0 | Verified control non-floods |
| **Excluded Unknown Hours (-1)** | 3256 | 3256 | Unassessed rainy context |
| **Precision** | **Unavailable** | **Unavailable** | Zero verified negative controls |
| **False Alarm Rate** | **Unavailable** | **Unavailable** | Zero verified negative controls |
| **F1 Score** | **Unavailable** | **Unavailable** | Requires precision & recall |

---

## 2. Honest Scientific Disclaimers & Metric Limitations

> [!IMPORTANT]
> **1. Why Precision and False-Alarm Rate are reported as UNAVAILABLE:**  
> The dataset currently contains **0 verified negative control observations** (`flood = 0`). In urban flood reporting, news agencies only report areas that *did* flood; dry/clear streets during severe storms are rarely published as news items.  
> Marking unmonitored rainy hours as "non-flood" would be unscientific and misleading because minor floods frequently go unreported. Hence, 3,256 rainy hours are strictly classified as **unknown (-1)** and excluded from supervised precision calculations.  
> **Precision and False-Alarm Rates will only be reported once active municipal control-point data is gathered.**

> [!NOTE]
> **2. The Reanalysis Attenuation Gap:**  
> Open-Meteo ERA5-Land reanalysis models atmospheric weather on a ~9km to 30km grid. Highly localized convective cloudbursts in Bengaluru (such as 60mm in 45 minutes over KR Circle) are smoothed across the broader grid, appearing as 3–9 mm/h in reanalysis archives.  
> When evaluated at the strict operational Amber threshold ($0.35$, calibrated for real-time 50 mm/h downpours), reanalysis inputs underestimate peak severity. When evaluated at the reanalysis sensitivity threshold ($0.10$), the model successfully flags the September 2022 deluge and May 2024 storms with a median lead time of **870.0 minutes (~14.5 hours)**.

---

## 3. Incident-Level Evaluation Breakdown (Operational Threshold $\ge 0.35$)

| Incident ID | Spot ID | Event ID | Detected? | Max Risk Score | Lead Time (min) | Outcome Note |
|---|---|---|---|---|---|---|
| `i001` | `kr_circle` | `ev_20230521_cloudburst` | ❌ MISSED | 0.05 | - | Max risk 0.05 below alert threshold 0.35 |
| `i002` | `bellandur` | `ev_20220905_deluge` | ❌ MISSED | 0.15 | - | Max risk 0.15 below alert threshold 0.35 |
| `i003` | `silk_board` | `ev_20220905_deluge` | ❌ MISSED | 0.15 | - | Max risk 0.15 below alert threshold 0.35 |
| `i004` | `mahadevapura` | `ev_20220905_deluge` | ❌ MISSED | 0.12 | - | Max risk 0.12 below alert threshold 0.35 |
| `i005` | `hsr_layout` | `ev_20220905_deluge` | ❌ MISSED | 0.12 | - | Max risk 0.12 below alert threshold 0.35 |
| `i006` | `agara` | `ev_20220905_deluge` | ❌ MISSED | 0.13 | - | Max risk 0.13 below alert threshold 0.35 |
| `i007` | `silk_board` | `ev_20221019_rains` | ❌ MISSED | 0.02 | - | Max risk 0.02 below alert threshold 0.35 |
| `i008` | `bellandur` | `ev_20221019_rains` | ❌ MISSED | 0.02 | - | Max risk 0.02 below alert threshold 0.35 |
| `i009` | `kr_circle` | `ev_20240519_thunderstorms` | ❌ MISSED | 0.12 | - | Max risk 0.12 below alert threshold 0.35 |
| `i010` | `hebbal` | `ev_20240519_thunderstorms` | ❌ MISSED | 0.08 | - | Max risk 0.08 below alert threshold 0.35 |
| `i011` | `hebbal` | `ev_20241015_northblr` | ❌ MISSED | 0.09 | - | Max risk 0.09 below alert threshold 0.35 |
| `i012` | `agara` | `ev_20241021_cloudburst` | ❌ MISSED | 0.01 | - | Max risk 0.01 below alert threshold 0.35 |
| `i013` | `mahadevapura` | `ev_20241021_cloudburst` | ❌ MISSED | 0.05 | - | Max risk 0.05 below alert threshold 0.35 |
| `i014` | `indiranagar` | `ev_20241021_cloudburst` | ❌ MISSED | 0.02 | - | Max risk 0.02 below alert threshold 0.35 |

---

## 4. Methodology & Leakage Prevention Rules

1. **Temporal Horizon**: Predictions are generated strictly sequentially. No future observed rainfall (`next_2h_mm`) is passed as an input during validation.
2. **Event Isolation**: Evaluation groups incidents by multi-spot physical storm events rather than random hour slicing.
3. **Threshold Calibration**: Operational alerts are triggered when predicted risk reaches $\ge 0.35$ (Amber warning threshold).
