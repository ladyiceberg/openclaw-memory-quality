"""
test_llm_promotion_evaluator.py · 关卡 5 LLM 长期价值 advisory 单元测试

全部使用 mock LLM，不需要真实 API key。
覆盖：evaluate_long_term_value、run_llm_promotion_evaluation、
      LLMPromotionEvalResult 属性、错误处理。
"""
from unittest.mock import MagicMock
from typing import Optional

import pytest

from src.analyzers.llm_promotion_evaluator import (
    LLMPromotionEvalResult,
    LongTermValueAdvisory,
    evaluate_long_term_value,
    run_llm_promotion_evaluation,
)
from src.analyzers.promotion_auditor import (
    PromotionCandidate,
    PromotionScore,
)
from src.readers.shortterm_reader import ShortTermEntry


# ── 测试辅助 ───────────────────────────────────────────────────────────────────

def _entry(key: str = "k1", path: str = "memory/f.md") -> ShortTermEntry:
    return ShortTermEntry(
        key=key, path=path, start_line=1, end_line=5,
        source="memory",
        snippet="Gateway binds loopback and port 18789",
        recall_count=5, total_score=4.0, max_score=0.92,
        first_recalled_at="2026-04-05T00:00:00Z",
        last_recalled_at="2026-04-14T00:00:00Z",
        query_hashes=["h1", "h2", "h3"],
        recall_days=["2026-04-14"],
        concept_tags=["gateway", "port"],
    )


def _score(composite: float = 0.75, avg: float = 0.80) -> PromotionScore:
    return PromotionScore(
        composite=composite, frequency=0.5, relevance=avg,
        diversity=0.6, recency=0.9, conceptual=0.3, avg_score=avg,
    )


def _candidate(
    key: str = "k1",
    verdict: str = "pass",
    skip_reason: Optional[str] = None,
    flag_reason: Optional[str] = None,
) -> PromotionCandidate:
    return PromotionCandidate(
        entry=_entry(key=key),
        score=_score(),
        verdict=verdict,
        skip_reason=skip_reason,
        flag_reason=flag_reason,
    )


def _mock_llm(verdict: str, reason: str = "test reason"):
    mock = MagicMock()
    mock.complete.return_value = MagicMock(
        parsed={"verdict": verdict, "reason": reason}
    )
    return mock


# ── evaluate_long_term_value ───────────────────────────────────────────────────

class TestEvaluateLongTermValue:
    def test_long_term_knowledge_verdict(self):
        """LLM 返回 long_term_knowledge → 正确映射。"""
        llm = _mock_llm("long_term_knowledge", "稳定设计事实")
        cand = _candidate()
        result = evaluate_long_term_value(cand, llm)
        assert result.verdict == "long_term_knowledge"
        assert result.reason == "稳定设计事实"

    def test_one_time_context_verdict(self):
        """LLM 返回 one_time_context → 正确映射。"""
        llm = _mock_llm("one_time_context", "一次性上下文")
        cand = _candidate()
        result = evaluate_long_term_value(cand, llm)
        assert result.verdict == "one_time_context"

    def test_uncertain_verdict(self):
        """LLM 返回 uncertain → 正确映射。"""
        llm = _mock_llm("uncertain", "上下文不足")
        cand = _candidate()
        result = evaluate_long_term_value(cand, llm)
        assert result.verdict == "uncertain"

    def test_entry_key_in_result(self):
        """结果中 entry_key 与 candidate.entry.key 一致。"""
        llm = _mock_llm("uncertain")
        cand = _candidate(key="my_key_123")
        result = evaluate_long_term_value(cand, llm)
        assert result.entry_key == "my_key_123"

    def test_llm_parse_failure_returns_uncertain(self):
        """LLM 返回 None parsed → uncertain，不崩溃。"""
        mock = MagicMock()
        mock.complete.return_value = MagicMock(parsed=None)
        cand = _candidate()
        result = evaluate_long_term_value(cand, mock)
        assert result.verdict == "uncertain"

    def test_llm_missing_verdict_returns_uncertain(self):
        """LLM 返回缺少 verdict 字段 → uncertain。"""
        mock = MagicMock()
        mock.complete.return_value = MagicMock(parsed={"reason": "ok"})
        cand = _candidate()
        result = evaluate_long_term_value(cand, mock)
        assert result.verdict == "uncertain"

    def test_llm_exception_returns_uncertain(self):
        """LLM 抛异常 → uncertain，不崩溃。"""
        mock = MagicMock()
        mock.complete.side_effect = Exception("network error")
        cand = _candidate()
        result = evaluate_long_term_value(cand, mock)
        assert result.verdict == "uncertain"

    def test_returns_long_term_value_advisory_type(self):
        """返回值是 LongTermValueAdvisory 类型。"""
        llm = _mock_llm("uncertain")
        result = evaluate_long_term_value(_candidate(), llm)
        assert isinstance(result, LongTermValueAdvisory)

    def test_snippet_and_path_in_prompt(self):
        """user message 包含 snippet 和 path 信息。"""
        llm = _mock_llm("uncertain")
        cand = _candidate()
        evaluate_long_term_value(cand, llm)
        call_args = llm.complete.call_args
        user_msg = call_args[1]["user"] if "user" in call_args[1] else call_args[0][1]
        assert "Gateway binds loopback" in user_msg
        assert "memory/f.md" in user_msg


# ── run_llm_promotion_evaluation ──────────────────────────────────────────────

class TestRunLlmPromotionEvaluation:
    def test_skip_candidates_not_evaluated(self):
        """skip 条目不调用 LLM。"""
        mock = MagicMock()
        candidates = [_candidate(verdict="skip", skip_reason="source_deleted")]
        result = run_llm_promotion_evaluation(candidates, mock)
        mock.complete.assert_not_called()
        assert result.advisories == {}

    def test_pass_candidates_evaluated(self):
        """pass 条目调用 LLM。"""
        llm = _mock_llm("long_term_knowledge")
        candidates = [_candidate(key="k1", verdict="pass")]
        result = run_llm_promotion_evaluation(candidates, llm)
        assert "k1" in result.advisories
        assert result.advisories["k1"].verdict == "long_term_knowledge"

    def test_flag_candidates_evaluated(self):
        """flag 条目也调用 LLM。"""
        llm = _mock_llm("one_time_context")
        candidates = [_candidate(key="k1", verdict="flag",
                                 flag_reason="potential_false_positive")]
        result = run_llm_promotion_evaluation(candidates, llm)
        assert "k1" in result.advisories

    def test_mixed_candidates_only_non_skip_evaluated(self):
        """混合列表：只有 pass/flag 被评估，skip 跳过。"""
        call_count = [0]
        def complete(system, user, json_schema=None, max_tokens=256):
            resp = MagicMock()
            call_count[0] += 1
            resp.parsed = {"verdict": "uncertain", "reason": "ok"}
            return resp
        mock = MagicMock()
        mock.complete.side_effect = complete

        candidates = [
            _candidate(key="skip1", verdict="skip"),
            _candidate(key="pass1", verdict="pass"),
            _candidate(key="flag1", verdict="flag"),
            _candidate(key="skip2", verdict="skip"),
        ]
        result = run_llm_promotion_evaluation(candidates, mock)
        assert call_count[0] == 2  # 只有 pass1 和 flag1
        assert "pass1" in result.advisories
        assert "flag1" in result.advisories
        assert "skip1" not in result.advisories
        assert "skip2" not in result.advisories

    def test_empty_candidates_no_calls(self):
        """空候选列表 → 不调用 LLM。"""
        mock = MagicMock()
        result = run_llm_promotion_evaluation([], mock)
        mock.complete.assert_not_called()
        assert result.advisories == {}

    def test_returns_llm_promotion_eval_result_type(self):
        """返回值是 LLMPromotionEvalResult 类型。"""
        result = run_llm_promotion_evaluation([], MagicMock())
        assert isinstance(result, LLMPromotionEvalResult)

    def test_all_skip_no_calls(self):
        """全部是 skip → 不调用 LLM，advisories 为空。"""
        mock = MagicMock()
        candidates = [
            _candidate(key=f"k{i}", verdict="skip") for i in range(5)
        ]
        result = run_llm_promotion_evaluation(candidates, mock)
        mock.complete.assert_not_called()
        assert result.advisories == {}


# ── LLMPromotionEvalResult 属性 ────────────────────────────────────────────────

class TestLLMPromotionEvalResultProperties:
    def test_long_term_count(self):
        """long_term_count 正确统计。"""
        result = LLMPromotionEvalResult(advisories={
            "k1": LongTermValueAdvisory("k1", "long_term_knowledge", "r"),
            "k2": LongTermValueAdvisory("k2", "long_term_knowledge", "r"),
            "k3": LongTermValueAdvisory("k3", "one_time_context", "r"),
        })
        assert result.long_term_count == 2

    def test_one_time_count(self):
        """one_time_count 正确统计。"""
        result = LLMPromotionEvalResult(advisories={
            "k1": LongTermValueAdvisory("k1", "one_time_context", "r"),
            "k2": LongTermValueAdvisory("k2", "uncertain", "r"),
        })
        assert result.one_time_count == 1

    def test_uncertain_count(self):
        """uncertain_count 正确统计。"""
        result = LLMPromotionEvalResult(advisories={
            "k1": LongTermValueAdvisory("k1", "uncertain", "r"),
            "k2": LongTermValueAdvisory("k2", "uncertain", "r"),
            "k3": LongTermValueAdvisory("k3", "long_term_knowledge", "r"),
        })
        assert result.uncertain_count == 2

    def test_empty_advisories_all_zero(self):
        """空 advisories → 三个计数都是 0。"""
        result = LLMPromotionEvalResult()
        assert result.long_term_count == 0
        assert result.one_time_count == 0
        assert result.uncertain_count == 0
