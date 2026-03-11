"""
主工作流编排（基于 Agno Workflow）
===================================
使用 Agno Workflow 框架编排 6 阶段合规审核流水线：
  Stage 0: 预处理与资产固化（纯代码）
  Stage 1: 混合检索 + LLM 粗筛（Agno Agent 并发）
  Stage 1.5: 事实抽取（纯代码）
  Stage 1.8: 双轨路由分发（纯代码）
  Stage 2: 双轨深度精判（Agno Agent 并发）
  Stage 3: 确定性定位 + API 组装（纯代码）

Agno Workflow 提供：
  - session_state  : 跨 Step 共享的工作流状态
  - Step 级别     : 指标收集、错误处理、后续扩展（条件路由、循环等）
"""

import json
import time
import asyncio
from contextvars import ContextVar
from pathlib import Path

from agno.workflow import Workflow, Step, StepInput, StepOutput

from . import config
from .log import get_logger
from .schemas import RuleCard, WorkflowState, AuditResponse
from .ocr_preprocessor import normalize_text_for_audit
from .stages.stage0_preprocess import preprocess
from .stages.stage1_recall_filter import run_stage1
from .stages.stage1_5_fact_extract import run_stage1_5
from .stages.stage1_8_route_dispatch import run_stage1_8
from .stages.stage2_deep_judge import run_stage2
from .stages.stage2_5_refute import run_stage2_5_refute
from .stages.stage3_assemble import run_stage3

logger = get_logger(__name__)

# ============================================================
# 规则卡片缓存（避免重复加载和解析 JSON）
# ============================================================

_cached_rule_cards: dict[str, RuleCard] | None = None
_cached_rule_cards_path: str | None = None


def load_rule_cards(path: str | None = None, force_reload: bool = False) -> dict[str, RuleCard]:
    """从 JSON 文件加载规则卡片（自动缓存，避免重复 IO）"""
    global _cached_rule_cards, _cached_rule_cards_path

    if path is None:
        path = config.RULE_CARDS_PATH

    # 命中缓存
    if not force_reload and _cached_rule_cards is not None and _cached_rule_cards_path == path:
        logger.debug(f"使用缓存的规则卡片 ({len(_cached_rule_cards)} 条)")
        return _cached_rule_cards

    rule_path = Path(path)
    if not rule_path.is_absolute():
        rule_path = config.BASE_DIR / rule_path

    with open(rule_path, "r", encoding="utf-8") as f:
        raw_list = json.load(f)

    cards = {}
    for item in raw_list:
        card = RuleCard(**item)
        cards[card.rule_id] = card

    # 写入缓存
    _cached_rule_cards = cards
    _cached_rule_cards_path = path

    logger.info(f"已加载 {len(cards)} 条规则卡片")
    return cards


# ============================================================
# 跨 Step 共享状态（基于 ContextVar，支持并发隔离）
# ============================================================

_current_state: ContextVar[WorkflowState | None] = ContextVar("_current_state", default=None)
_current_meta: ContextVar[dict[str, object]] = ContextVar("_current_meta", default={})


def _get_state() -> WorkflowState:
    """获取当前 Workflow 的共享状态（每个请求独立）"""
    state = _current_state.get()
    if state is None:
        raise RuntimeError("WorkflowState 未初始化，请通过 run_audit() 调用工作流")
    return state


def _get_meta() -> dict[str, object]:
    """获取当前请求上下文元信息（例如 start_time/doc_id）"""
    return _current_meta.get()


# ============================================================
# Step Executor（每个 Step 对应一个 Pipeline 阶段）
# ============================================================

async def _stage0_executor(step_input: StepInput) -> StepOutput:
    """Stage 0: 预处理与资产固化"""
    logger.info("=" * 50)
    logger.info("=== Stage 0: 预处理与资产固化 ===")

    state = _get_state()
    input_text = step_input.input or ""
    meta = _get_meta()
    doc_id = meta.get("doc_id")

    # OCR 文本预处理（自动检测并修复 OCR 文本问题）
    working_text = normalize_text_for_audit(input_text)
    if working_text != input_text:
        logger.info("检测到 OCR 文本，已应用智能修复")

    state.document = preprocess(
        original_text=input_text,  # 保存用户真正的输入
        working_text=working_text,  # 用于审核处理的文本
        doc_id=doc_id if isinstance(doc_id, str) else None,
        chunk_size=config.CHUNK_SIZE,
        chunk_min_size=config.CHUNK_MIN_SIZE,
    )

    logger.info(
        f"Stage 0 完成: doc_id={state.document.doc_id}, "
        f"{len(state.document.chunks)} chunks, "
        f"{len(state.document.span_pool)} spans"
    )

    return StepOutput(
        content=f"doc_id={state.document.doc_id}, "
                f"chunks={len(state.document.chunks)}, "
                f"spans={len(state.document.span_pool)}",
        success=True,
    )


async def _stage1_executor(step_input: StepInput) -> StepOutput:
    """Stage 1: 路由召回与大模型粗筛"""
    logger.info("=" * 50)
    logger.info("=== Stage 1: 路由召回与大模型粗筛 ===")

    state = _get_state()

    state.stage1_candidates = await run_stage1(
        document=state.document,
        rule_cards=state.rule_cards,
        top_k_recall=config.TOP_K_RULES,
        top_k_filter=config.TOP_K_FILTER,
        max_concurrent=config.MAX_CONCURRENT_CALLS,
    )

    total_pairs = sum(len(c.candidate_rule_ids) for c in state.stage1_candidates)
    logger.info(
        f"Stage 1 完成: {len(state.stage1_candidates)} 个 Chunk 有候选, "
        f"共 {total_pairs} 个待精判组合"
    )

    return StepOutput(
        content=f"candidates={len(state.stage1_candidates)}, pairs={total_pairs}",
        success=True,
    )


async def _stage2_executor(step_input: StepInput) -> StepOutput:
    """Stage 2: 深度精判与对齐"""
    logger.info("=" * 50)
    logger.info("=== Stage 2: 深度精判与对齐 ===")

    state = _get_state()

    state.stage2_judgments = await run_stage2(
        document=state.document,
        rule_cards=state.rule_cards,
        candidates=state.stage1_candidates,
        routed_pairs=state.stage18_routes,
        chunk_facts=state.stage15_facts,
        max_concurrent=config.MAX_CONCURRENT_CALLS,
    )

    violation_count = sum(1 for j in state.stage2_judgments if j.verdict == "violation")
    logger.info(
        f"Stage 2 完成: {len(state.stage2_judgments)} 个判定结果, "
        f"其中 {violation_count} 个违规"
    )

    return StepOutput(
        content=f"judgments={len(state.stage2_judgments)}, violations={violation_count}",
        success=True,
    )


async def _stage15_executor(step_input: StepInput) -> StepOutput:
    """Stage 1.5: 事实抽取与结构化固化"""
    logger.info("=" * 50)
    logger.info("=== Stage 1.5: 事实抽取与结构化固化 ===")

    state = _get_state()

    state.stage15_facts = run_stage1_5(
        document=state.document,
        candidates=state.stage1_candidates,
    )

    signal_count = sum(len(p.signals) for p in state.stage15_facts.values())
    logger.info(
        f"Stage 1.5 完成: {len(state.stage15_facts)} 个 chunk 事实画像, "
        f"共 {signal_count} 条事实信号"
    )

    return StepOutput(
        content=f"fact_profiles={len(state.stage15_facts)}, signals={signal_count}",
        success=True,
    )


async def _stage18_executor(step_input: StepInput) -> StepOutput:
    """Stage 1.8: 双轨路由分发"""
    logger.info("=" * 50)
    logger.info("=== Stage 1.8: 双轨路由分发 ===")

    state = _get_state()
    state.stage18_routes = run_stage1_8(
        candidates=state.stage1_candidates,
        rule_cards=state.rule_cards,
        chunk_facts=state.stage15_facts,
    )

    base_count = sum(1 for r in state.stage18_routes if r.strategy == "base")
    skill_count = len(state.stage18_routes) - base_count
    return StepOutput(
        content=f"routes={len(state.stage18_routes)}, base={base_count}, skill={skill_count}",
        success=True,
    )


async def _stage3_executor(step_input: StepInput) -> StepOutput:
    """Stage 3: 确定性定位与 API 组装"""
    logger.info("=" * 50)
    logger.info("=== Stage 3: 确定性定位与 API 组装 ===")

    state = _get_state()
    meta = _get_meta()

    # processing_time 从 session_state 中获取
    start_time = float(meta.get("start_time", time.time()))
    processing_time = time.time() - start_time

    state.final_response = run_stage3(
        judgments=state.stage2_judgments,
        document=state.document,
        rule_cards=state.rule_cards,
        processing_time=processing_time,
    )

    logger.info(
        f"Stage 3 完成: {state.final_response.total_violations} 个违规, "
        f"耗时 {state.final_response.processing_time_seconds}s"
    )

    return StepOutput(
        content=state.final_response.model_dump_json(ensure_ascii=False),
        success=True,
    )


async def _stage25_executor(step_input: StepInput) -> StepOutput:
    """Stage 2.5: 反证校验与误报纠偏"""
    logger.info("=" * 50)
    logger.info("=== Stage 2.5: 反证校验与误报纠偏 ===")

    state = _get_state()
    before_violation = sum(1 for j in state.stage2_judgments if j.verdict == "violation")

    state.stage2_judgments = run_stage2_5_refute(
        judgments=state.stage2_judgments,
        document=state.document,
        rule_cards=state.rule_cards,
        chunk_facts=state.stage15_facts,
    )

    after_violation = sum(1 for j in state.stage2_judgments if j.verdict == "violation")
    logger.info(
        f"Stage 2.5 完成: violation {before_violation} -> {after_violation}"
    )

    return StepOutput(
        content=f"violation_before={before_violation}, violation_after={after_violation}",
        success=True,
    )


# ============================================================
# Agno Workflow 创建
# ============================================================

def create_workflow() -> Workflow:
    """
    创建 Agno Workflow 实例（6 阶段合规审核流水线）。

    Workflow 配置：
      - 顺序 Step，每个 Step 对应一个 Pipeline 阶段
      - session_state 用于跨 Step 共享工作流状态
      - debug_mode 关闭以减少日志噪音
    """
    return Workflow(
        name="ComplianceAudit",
        description="保险文本合规审核 5 阶段流水线 (Agno Workflow)",
        steps=[
            Step(name="preprocess", executor=_stage0_executor),
            Step(name="recall_filter", executor=_stage1_executor),
            Step(name="fact_extract", executor=_stage15_executor),
            Step(name="route_dispatch", executor=_stage18_executor),
            Step(name="deep_judge", executor=_stage2_executor),
            Step(name="refute_validate", executor=_stage25_executor),
            Step(name="assemble", executor=_stage3_executor),
        ],
        session_state={},
        debug_mode=False,
    )


# ============================================================
# 公开接口（供 API 和 CLI 使用）
# ============================================================

async def run_audit(input_text: str, doc_id: str | None = None) -> AuditResponse:
    """
    异步执行完整的合规审核流水线（基于 Agno Workflow）。

    流水线:
      Stage 0: 预处理与资产固化（纯代码）
      Stage 1: 路由召回与大模型粗筛（Agno Agent 并发）
      Stage 2: 双轨深度精判（base/skill 分发 + Agno Agent 并发 + unsure 二次审查）
      Stage 3: 确定性定位与 API 组装（纯代码，坐标重叠去重）
    """
    start_time = time.time()

    # 初始化当前请求的隔离状态
    state = WorkflowState()
    state.rule_cards = load_rule_cards()
    state_token = _current_state.set(state)
    meta_token = _current_meta.set({
        "start_time": start_time,
        "doc_id": doc_id,
    })

    try:
        # 创建并运行 Agno Workflow
        wf = create_workflow()
        await wf.arun(input=input_text)

        # 从隔离状态中提取最终结果
        response = state.final_response
        return response
    finally:
        _current_state.reset(state_token)
        _current_meta.reset(meta_token)


def run_audit_sync(input_text: str, doc_id: str | None = None) -> AuditResponse:
    """同步版本的审核入口（CLI 使用）"""
    return asyncio.run(run_audit(input_text, doc_id))
