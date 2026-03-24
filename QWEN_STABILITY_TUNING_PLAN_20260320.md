# Qwen 稳定性调优方案（不换模型版）

## 1. 当前结论

当前项目使用的是 `SiliconFlow / Qwen/Qwen3.5-27B`，渠道本身是通的，轻量请求下：

- 单次请求：`HTTP 200`
- `8` 并发：`8/8` 成功
- `24` 并发：`24/24` 成功

因此，当前问题**不是模型渠道不可用**，而是：

1. 审核链路属于长链路、多阶段、多次 LLM 调用
2. `think` 打开后，单次请求 token 消耗明显上升
3. `100+` 条 smoke 批量评测时，系统累计 token 压力过大
4. 触发 `TPM` 限流、非结构化输出、Stage 降级，最终表现为**误判偏保守、召回明显下降**

---

## 2. 目标

在**不更换模型**的前提下，优先提升以下能力：

- 保持渠道可用和长链路稳定
- 减少 `429 TPM limit` 和非结构化输出
- 保持主判定效果，不因为全局降级导致召回塌陷
- 让 `smoke` 批量评测可稳定跑完，而不是只适合小样本探针

---

## 3. 核心判断

当前最关键的问题不是“模型能力不够”，而是“**同一个模型被用在不同职责阶段时，资源策略没有彻底分层**”。

也就是说：

- `Stage 1 filter` 只做粗筛，不值得消耗高推理预算
- `Stage 2 judge` 才是最值得保留 `think` 的阶段
- `Stage 2.7 suggestion` 对实时性和结构稳定性要求更高，不应抢占主判定预算
- `benchmark` 跑批时应视为“压测模式”，其策略不应与线上单文档审核完全一致

因此，稳定性优化要遵循：

> **按阶段分层控制，而不是全局同配。**

---

## 4. P0 级稳定性方案

### P0-1. 保留 `think`，但只集中在 `judge` 主判定层

建议：

- `filter model`：默认关闭 `think`
- `judge model`：保留 `think`
- `suggestion model`：默认关闭 `think`

原因：

- `filter` 只是召回粗筛，过度推理没有收益
- `judge` 才是真正需要语义判定和边界推理的位置
- `suggestion` 面向业务展示，更重表达稳定，而不是深推理

建议默认配置：

- `FILTER_MODEL_ENABLE_THINKING=false`
- `JUDGE_MODEL_ENABLE_THINKING=true`
- `SUGGESTION_MODEL_ENABLE_THINKING=false`

---

### P0-2. 并发分层，不再让批量评测直接吃满 `24`

当前 `24` 并发对轻量探针可用，但不代表适合多阶段审核链路。

建议拆成两层：

- **接口级并发**：用于控制同时审核多少篇文档
- **Stage 级并发**：用于控制单篇文档内部的 LLM 并发

建议值：

- 日常单文档审核：
  - `MAX_CONCURRENT_CALLS=8`
  - `STAGE2_MAX_CONCURRENT_CALLS=3~4`
- `smoke` 批量评测：
  - 外层批跑并发控制在 `1~2` 个 runner
  - runner 内部 `MAX_CONCURRENT_CALLS=4`
  - `STAGE2_MAX_CONCURRENT_CALLS=2~3`

关键原则：

> **线上单请求并发** 和 **离线批量评测并发** 必须分开控制。

不能因为轻量探针下 `24` 并发成功，就直接在长链路 `smoke` 跑批里沿用 `24`。

---

### P0-3. 对 `filter` 和 `judge` 采用不同超时策略

建议：

- `filter`：短超时，快速失败，直接 fallback
- `judge`：中等超时，允许有限退避重试
- `suggestion`：更短超时，失败就退回模板建议

建议值：

- `filter timeout`: `12~15s`
- `judge timeout`: `60~90s`
- `suggestion timeout`: `20~30s`

原因：

- `filter` 不值得等待太久
- `judge` 是主判定，值得保留窗口
- `suggestion` 不是核心判定，不应拖慢主链路

---

### P0-4. 把重试从“立即重试”改成“分层退避重试”

当前已有重试，但建议进一步明确策略：

- `429`：指数退避 + 抖动
- 非结构化输出：最多 `1` 次重试
- 超时：最多 `1` 次重试
- 同一阶段同一 agent 连续失败后，应直接进入 fallback，不继续硬撞

建议：

- `filter`: `max_retries=1`
- `judge`: `max_retries=1~2`
- `suggestion`: `max_retries=0~1`

重点不是多试几次，而是：

> **避免把同一类慢请求反复打到同一限流窗口上。**

---

### P0-5. 给 `benchmark` 增加“稳定性运行模式”

建议在评测模块里增加一组独立运行参数（不影响主流程逻辑）：

- `BENCHMARK_MAX_CONCURRENT_RUNNERS`
- `BENCHMARK_STAGE_MAX_CONCURRENT_CALLS`
- `BENCHMARK_DISABLE_SUGGESTION_RENDER`
- `BENCHMARK_FILTER_THINKING=false`
- `BENCHMARK_JUDGE_THINKING=true`

目标是让 benchmark 进入一种更稳的模式：

- 保证主判定优先
- 关闭非必要渲染消耗
- 控制批量请求速率

这类配置只影响评测运行，不影响线上主审核链路。

---

## 5. P1 级进一步优化

### P1-1. 为不同阶段设置不同 `max_tokens`

建议：

- `filter`: `64~128`
- `judge`: `512~768`
- `suggestion`: `192~384`

原因：

- `filter` 不需要长输出
- `judge` 才需要更大预算
- `suggestion` 只需要稳定改写，不需要长 reasoning

---

### P1-2. 为 `judge` 单独设置 `thinking_budget`

建议：

- `judge thinking_budget`: `96~192`
- `filter thinking_budget`: `0`
- `suggestion thinking_budget`: `0~64`

原因：

- Qwen 的 `reasoning_content` 会消耗大量预算
- 如果不限制 budget，批量评测时很容易压满 TPM

---

### P1-3. 把 `非结构化输出` 视为稳定性问题，而不只是解析问题

当前这类错误容易表现为：

- API 请求成功
- 但输出不符合 schema
- 最终变成 `unsure` / `compliant` / fallback

建议在后续监控里单独统计：

- `structured_parse_failure_rate`
- `filter_fallback_rate`
- `judge_retry_rate`
- `429_rate`

这样才能把“模型通了但效果掉了”定位清楚。

---

## 6. 推荐默认配置（下一版建议值）

### 线上审核默认值

- `MAX_CONCURRENT_CALLS=8`
- `STAGE2_MAX_CONCURRENT_CALLS=4`
- `FILTER_MODEL_ENABLE_THINKING=false`
- `JUDGE_MODEL_ENABLE_THINKING=true`
- `SUGGESTION_MODEL_ENABLE_THINKING=false`
- `FILTER timeout=15s`
- `JUDGE timeout=75s`
- `SUGGESTION timeout=25s`

### benchmark 跑批默认值

- 外层 runner 并发：`1`
- `MAX_CONCURRENT_CALLS=4`
- `STAGE2_MAX_CONCURRENT_CALLS=2`
- `FILTER_MODEL_ENABLE_THINKING=false`
- `JUDGE_MODEL_ENABLE_THINKING=true`
- `SUGGESTION_USE_LLM_RENDERER=false`

---

## 7. 最后判断

如果不换模型，当前最优策略不是继续盲目提高并发，而是：

1. **保留 `judge think`**
2. **压缩 `filter` 消耗**
3. **关闭建议层不必要的模型渲染**
4. **把批量评测和线上审核拆成两套并发策略**

一句话总结：

> 当前 Qwen 通道是通的，问题不是“能不能调”，而是“怎么在长链路下稳地调”。

