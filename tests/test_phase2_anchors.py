"""
测试 Phase 2 新增的 5 类锚点抽取功能
"""

import unittest
from src.moderation.stages.stage0_preprocess import preprocess
from src.moderation.stages.stage1_5_fact_extract import run_stage1_5
from src.moderation.schemas import ChunkCandidates


class TestPhase2Anchors(unittest.TestCase):
    """测试 Phase 2 新增的锚点抽取"""

    def test_actor_extraction(self):
        """测试主体识别（actor）"""
        text = "我们的代理人月收入可观，客户满意度高，公司实力雄厚。"
        doc = preprocess(original_text=text, working_text=text, doc_id="TEST_ACTOR")

        # 模拟 Stage 1 输出
        candidates = [ChunkCandidates(chunk_id=doc.chunks[0].chunk_id, candidate_rule_ids=["R001"])]

        # 运行 Stage 1.5
        profiles = run_stage1_5(document=doc, candidates=candidates)

        # 验证主体识别
        profile = profiles[doc.chunks[0].chunk_id]
        signal_labels = {s.label for s in profile.signals}

        self.assertIn("actor_agent", signal_labels, "应该识别出代理人主体")
        self.assertIn("actor_customer", signal_labels, "应该识别出客户主体")
        self.assertIn("actor_company", signal_labels, "应该识别出公司主体")

    def test_claim_type_extraction(self):
        """测试主张类型（claim）"""
        text = "产品收益稳定，排名第一，历史业绩优秀，建议退保旧保单。"
        doc = preprocess(original_text=text, working_text=text, doc_id="TEST_CLAIM")

        candidates = [ChunkCandidates(chunk_id=doc.chunks[0].chunk_id, candidate_rule_ids=["R001"])]
        profiles = run_stage1_5(document=doc, candidates=candidates)

        profile = profiles[doc.chunks[0].chunk_id]
        signal_labels = {s.label for s in profile.signals}

        self.assertIn("claim_income_promise", signal_labels, "应该识别出收益承诺")
        self.assertIn("claim_ranking", signal_labels, "应该识别出排名声称")
        self.assertIn("claim_historical", signal_labels, "应该识别出历史业绩")
        self.assertIn("claim_surrender", signal_labels, "应该识别出退保引导")

    def test_time_scope_extraction(self):
        """测试时间范围（time_scope）"""
        text = "之前在银行工作，现在担任经理，未来发展前景好，限时优惠。"
        doc = preprocess(original_text=text, working_text=text, doc_id="TEST_TIME")

        candidates = [ChunkCandidates(chunk_id=doc.chunks[0].chunk_id, candidate_rule_ids=["R001"])]
        profiles = run_stage1_5(document=doc, candidates=candidates)

        profile = profiles[doc.chunks[0].chunk_id]
        signal_labels = {s.label for s in profile.signals}

        self.assertIn("time_past", signal_labels, "应该识别出过去时态")
        self.assertIn("time_present", signal_labels, "应该识别出现在时态")
        self.assertIn("time_future", signal_labels, "应该识别出未来时态")
        self.assertIn("time_limited", signal_labels, "应该识别出限时标记")

    def test_evidence_need_extraction(self):
        """测试证据需求（evidence_need）"""
        text = "年化收益率8%，排名行业第一，历史业绩优秀，获奖无数。"
        doc = preprocess(original_text=text, working_text=text, doc_id="TEST_EVIDENCE")

        candidates = [ChunkCandidates(chunk_id=doc.chunks[0].chunk_id, candidate_rule_ids=["R001"])]
        profiles = run_stage1_5(document=doc, candidates=candidates)

        profile = profiles[doc.chunks[0].chunk_id]
        signal_labels = {s.label for s in profile.signals}

        self.assertIn("evidence_need", signal_labels, "应该识别出需要证据的陈述")

        # 验证具体的证据需求词
        evidence_signals = [s for s in profile.signals if s.label == "evidence_need"]
        evidence_values = {s.value for s in evidence_signals}

        self.assertTrue(
            any(v in evidence_values for v in ["收益率", "排名", "历史", "业绩", "获奖"]),
            "应该识别出具体的证据需求词"
        )

    def test_tone_strength_extraction(self):
        """测试语气强度（tone_strength）"""
        text = "保证收益，可能亏损，预期回报，建议购买。"
        doc = preprocess(original_text=text, working_text=text, doc_id="TEST_TONE")

        candidates = [ChunkCandidates(chunk_id=doc.chunks[0].chunk_id, candidate_rule_ids=["R001"])]
        profiles = run_stage1_5(document=doc, candidates=candidates)

        profile = profiles[doc.chunks[0].chunk_id]
        signal_labels = {s.label for s in profile.signals}

        self.assertIn("tone_guarantee", signal_labels, "应该识别出保证语气")
        self.assertIn("tone_possible", signal_labels, "应该识别出可能语气")
        self.assertIn("tone_expected", signal_labels, "应该识别出预期语气")
        self.assertIn("tone_suggest", signal_labels, "应该识别出建议语气")

    def test_complex_scenario(self):
        """测试复杂场景：多种锚点同时出现"""
        text = "李经理之前在外企工作，月薪3万。现在加入我们，预期收益更高，保证稳定。"
        doc = preprocess(original_text=text, working_text=text, doc_id="TEST_COMPLEX")

        candidates = [ChunkCandidates(chunk_id=doc.chunks[0].chunk_id, candidate_rule_ids=["R001"])]
        profiles = run_stage1_5(document=doc, candidates=candidates)

        profile = profiles[doc.chunks[0].chunk_id]
        signal_labels = {s.label for s in profile.signals}

        # 验证多种锚点
        self.assertIn("actor_agent", signal_labels, "应该识别出代理人主体")
        self.assertIn("actor_third_party", signal_labels, "应该识别出第三方主体")
        self.assertIn("time_past", signal_labels, "应该识别出过去时态")
        self.assertIn("time_present", signal_labels, "应该识别出现在时态")
        self.assertIn("claim_income_promise", signal_labels, "应该识别出收益承诺")
        self.assertIn("tone_expected", signal_labels, "应该识别出预期语气")
        self.assertIn("tone_guarantee", signal_labels, "应该识别出保证语气")

    def test_summary_includes_new_anchors(self):
        """测试摘要包含新增的锚点"""
        text = "代理人收益高，客户满意，过去业绩好，保证稳定。"
        doc = preprocess(original_text=text, working_text=text, doc_id="TEST_SUMMARY")

        candidates = [ChunkCandidates(chunk_id=doc.chunks[0].chunk_id, candidate_rule_ids=["R001"])]
        profiles = run_stage1_5(document=doc, candidates=candidates)

        profile = profiles[doc.chunks[0].chunk_id]
        summary = profile.summary

        # 验证摘要包含新增的锚点类型
        self.assertIn("actor_", summary, "摘要应该包含主体识别信息")
        self.assertIn("claim_", summary, "摘要应该包含主张类型信息")
        self.assertIn("time_", summary, "摘要应该包含时间范围信息")
        self.assertIn("tone_", summary, "摘要应该包含语气强度信息")


if __name__ == "__main__":
    unittest.main()
