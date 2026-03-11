"""
FastAPI 服务入口
=================
提供 RESTful API 接口供外部调用。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import config
from .log import get_logger, setup_logging
from .schemas import AuditResponse
from .workflow import run_audit, load_rule_cards

# 使用统一日志模块
setup_logging()
logger = get_logger(__name__)


# ============================================================
# 请求 / 响应 模型
# ============================================================

class AuditRequest(BaseModel):
    """审核请求体"""
    text: str = Field(..., description="待审核的保险文本内容", min_length=10)
    doc_id: str | None = Field(None, description="可选的文档ID")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    model: str
    rules_loaded: int


# ============================================================
# 应用生命周期
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的初始化和清理"""
    logger.info("=" * 60)
    logger.info("保险文本合规审核系统启动")
    logger.info(f"LLM Model: {config.LLM_MODEL}")
    logger.info(f"LLM API Base: {config.LLM_API_BASE}")
    logger.info(f"Chunk Size: {config.CHUNK_SIZE}, Min Size: {config.CHUNK_MIN_SIZE}")
    logger.info(f"Top-K Recall: {config.TOP_K_RULES}, Top-K Filter: {config.TOP_K_FILTER}")

    # 预加载规则卡片验证
    try:
        cards = load_rule_cards()
        app.state.rules_count = len(cards)
        logger.info(f"规则卡片加载成功: {len(cards)} 条")
    except Exception as e:
        logger.error(f"规则卡片加载失败: {e}")
        app.state.rules_count = 0

    logger.info("=" * 60)
    yield
    logger.info("保险文本合规审核系统关闭")


# ============================================================
# FastAPI 应用
# ============================================================

app = FastAPI(
    title="保险文本合规审核系统",
    description="基于 Agno Workflow + Agent 的保险文本合规审核 API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    """健康检查接口"""
    return HealthResponse(
        status="ok",
        model=config.LLM_MODEL,
        rules_loaded=getattr(app.state, "rules_count", 0),
    )


@app.post("/api/v1/audit", response_model=AuditResponse)
async def audit_text(request: AuditRequest):
    """
    文本合规审核接口

    对输入的保险文本进行全流程合规审核，返回违规详情。
    单次处理耗时 ≤ 3 分钟。
    """
    logger.info(f"收到审核请求: 文本长度={len(request.text)}, doc_id={request.doc_id}")

    try:
        response = await run_audit(
            input_text=request.text,
            doc_id=request.doc_id,
        )
        logger.info(
            f"审核完成: doc_id={response.doc_id}, "
            f"violations={response.total_violations}, "
            f"time={response.processing_time_seconds}s"
        )
        return response

    except Exception as e:
        logger.error(f"审核失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"审核处理失败: {str(e)}")


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "moderation.api:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=False,
        log_level="info",
    )
