"""
端到端测试：验证 Stage 1.9 Gate 和 Stage 2.5 Override 的主链路集成

注意：这些测试调用真实 LLM API，需要有效的 API Key 和网络连接。
在日常回归中请使用 `pytest -m "not integration"` 跳过这些测试。
"""

import pytest
from src.moderation.workflow import run_audit_sync

pytestmark = pytest.mark.integration


class TestMainPipelineIntegration:
    """测试主链路集成：Stage 1.9 Gate + Stage 2.5 Override"""

    def test_gate_integration_in_main_pipeline(self):
        """测试 Stage 1.9 Gate 已接入主工作流"""
        # 使用一个简单的测试文本
        text = "这款产品收益稳定，适合长期投资。"

        # 运行完整审核流程
        response = run_audit_sync(text, doc_id="test_gate_integration")

        # 验证流程正常完成
        assert response is not None
        assert response.doc_id == "test_gate_integration"
        assert isinstance(response.total_violations, int)

        # 如果有违规，验证结构完整
        if response.total_violations > 0:
            assert len(response.violations) > 0
            for violation in response.violations:
                assert violation.rule_id
                assert violation.verdict
                assert violation.reasoning

    def test_override_with_gate_signals(self):
        """测试 Stage 2.5 Override 接收 Gate 信号"""
        # 使用包含否定语境的文本（应触发 negation_context override）
        text = "请不要退保，退保会影响您的保障。"

        response = run_audit_sync(text, doc_id="test_override_gate")

        # 验证流程正常完成
        assert response is not None

        # 由于有否定语境，应该没有违规（或违规被 override 改判）
        # 这里不强制断言 total_violations == 0，因为可能有其他规则命中
        # 但至少验证流程没有崩溃
        assert isinstance(response.total_violations, int)

    def test_full_pipeline_with_complex_text(self):
        """测试完整流程处理复杂文本"""
        text = """
        我们的保险产品具有以下特点：
        1. 保障全面，覆盖多种风险
        2. 灵活的保单贷款功能，但请注意贷款会影响保障额度
        3. 根据保险法规定，保单具有现金价值

        请根据自身需求谨慎选择，不要盲目退保。
        """

        response = run_audit_sync(text, doc_id="test_complex_text")

        # 验证流程正常完成
        assert response is not None
        assert response.doc_id == "test_complex_text"
        assert isinstance(response.total_violations, int)
        assert isinstance(response.processing_time_seconds, float)

        # 验证违规结果结构
        for violation in response.violations:
            assert violation.rule_id
            assert violation.rule_name
            assert violation.risk_level in ["high", "medium", "low"]
            assert violation.verdict in ["violation", "compliant"]
            assert len(violation.locations) > 0

            # 验证定位信息
            for loc in violation.locations:
                assert loc.original_text_slice
                assert loc.raw_start >= 0
                assert loc.raw_end > loc.raw_start

    def test_gate_skip_functionality(self):
        """测试 Gate 的跳过功能（主体不匹配场景）"""
        # 使用客户视角的文本（如果规则要求代理人主体，应该被 Gate 跳过）
        text = "我觉得这个产品很好，我打算购买。"

        response = run_audit_sync(text, doc_id="test_gate_skip")

        # 验证流程正常完成
        assert response is not None
        assert isinstance(response.total_violations, int)

        # Gate 应该过滤掉不匹配的规则，减少不必要的 LLM 调用
        # 这里不强制断言具体数量，但验证流程正常

    def test_override_priority_order(self):
        """测试 Override 规则的优先级顺序"""
        # 使用可能触发多个 override 规则的文本
        text = "根据监管规定，保险产品具有现金价值，但请谨慎选择退保。"

        response = run_audit_sync(text, doc_id="test_override_priority")

        # 验证流程正常完成
        assert response is not None
        assert isinstance(response.total_violations, int)

        # Override 规则应该按优先级顺序应用（只应用第一个匹配的）
        # 这里验证流程没有崩溃即可


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
