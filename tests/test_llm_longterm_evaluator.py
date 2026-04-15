"""
test_llm_longterm_evaluator.py · LLM 语义评估层单元测试

全部使用 mock LLM，不需要真实 API key。
覆盖：任务A（有效性判断）、任务B（去重建议）、
      apply_llm_results 升级逻辑、错误处理。
"""
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from src.analyzers.llm_longterm_evaluator import (
    LLMEvalResult,
    MergeSuggestion,
    SemanticValidity,
    apply_llm_results,
    evaluate_duplicates_batch,
    evaluate_validity_single,
    run_llm_evaluation,
)
from src.analyzers.longterm_auditor import AuditedItem
from src.readers.longterm_reader import MemoryItem


# ── 测试辅助 ───────────────────────────────────────────────────────────────────

def _item(
    key: str = "memory:memory/f.md:1:5",
    path: str = "memory/f.md",
    start: int = 1,
    end: int = 5,
    snippet: str = "test snippet",
    score: float = 0.85,
    recalls: int = 3,
    avg: float = 0.70,
) -> MemoryItem:
    return MemoryItem(
        snippet=snippet,
        score=score,
        recalls=recalls,
        avg_score=avg,
        source_path=path,
        source_start=start,
        source_end=end,
        promotion_key=key,
    )


def _audited(item: MemoryItem, action: str = "review") -> AuditedItem:
    v1 = "possibly_moved" if action == "review" else "exists"
    v3 = "ok"
    return AuditedItem(item=item, v1_status=v1, v3_status=v3, action_hint=action)


def _mock_llm(verdicts: list[str], dedup_pairs: Optional[list] = None):
    """
    构造 mock LLM，按顺序返回任务 A 的判断结果。
    最后一次调用返回任务 B 的去重结果。
    """
    call_count = [0]

    def complete(system, user, json_schema=None, max_tokens=256):
        resp = MagicMock()
        idx = call_count[0]
        call_count[0] += 1

        # 任务 B（去重）：最后一次调用，或没有 verdict 可用时
        if idx >= len(verdicts):
            pairs = dedup_pairs or []
            resp.parsed = {"duplicates": pairs}
            return resp

        # 任务 A（有效性）
        resp.parsed = {"verdict": verdicts[idx], "reason": f"reason {idx}"}
        return resp

    mock = MagicMock()
    mock.complete.side_effect = complete
    mock._call_count = call_count
    return mock


# ── evaluate_validity_single ───────────────────────────────────────────────────

class TestEvaluateValiditySingle:
    def test_still_valid_upgrades_to_keep(self):
        """still_valid → upgraded_action=keep。"""
        llm = _mock_llm(["still_valid"])
        item = _item()
        result = evaluate_validity_single(item, Path("/tmp"), llm)
        assert result.verdict == "still_valid"
        assert result.upgraded_action == "keep"

    def test_outdated_upgrades_to_delete(self):
        """outdated → upgraded_action=delete。"""
        llm = _mock_llm(["outdated"])
        item = _item()
        result = evaluate_validity_single(item, Path("/tmp"), llm)
        assert result.verdict == "outdated"
        assert result.upgraded_action == "delete"

    def test_uncertain_stays_review(self):
        """uncertain → upgraded_action=review（不升级）。"""
        llm = _mock_llm(["uncertain"])
        item = _item()
        result = evaluate_validity_single(item, Path("/tmp"), llm)
        assert result.verdict == "uncertain"
        assert result.upgraded_action == "review"

    def test_llm_parse_failure_returns_uncertain(self):
        """LLM 返回无法解析的格式 → uncertain，不崩溃。"""
        mock = MagicMock()
        mock.complete.return_value = MagicMock(parsed=None)
        item = _item()
        result = evaluate_validity_single(item, Path("/tmp"), mock)
        assert result.verdict == "uncertain"
        assert result.upgraded_action == "review"

    def test_llm_exception_returns_uncertain(self):
        """LLM 调用抛异常 → uncertain，不崩溃。"""
        mock = MagicMock()
        mock.complete.side_effect = Exception("network error")
        item = _item()
        result = evaluate_validity_single(item, Path("/tmp"), mock)
        assert result.verdict == "uncertain"
        assert result.upgraded_action == "review"

    def test_source_file_context_included_when_exists(self):
        """来源文件存在时，context 内容会被传给 LLM。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            (ws / "memory").mkdir()
            src = ws / "memory" / "f.md"
            src.write_text("line1\nline2\nline3\nline4\nline5\n")

            llm = _mock_llm(["still_valid"])
            item = _item(path="memory/f.md", start=2, end=4)
            evaluate_validity_single(item, ws, llm)

            # 验证 user message 里包含文件内容
            call_args = llm.complete.call_args
            user_msg = call_args[1]["user"] if "user" in call_args[1] else call_args[0][1]
            assert "line2" in user_msg or "line" in user_msg

    def test_missing_source_file_noted_in_prompt(self):
        """来源文件不存在时，user message 里有相应说明。"""
        llm = _mock_llm(["outdated"])
        item = _item(path="memory/nonexistent.md")
        evaluate_validity_single(item, Path("/tmp"), llm)

        call_args = llm.complete.call_args
        user_msg = call_args[1]["user"] if "user" in call_args[1] else call_args[0][1]
        assert "不存在" in user_msg or "无法读取" in user_msg

    def test_returns_semantic_validity_type(self):
        """返回值是 SemanticValidity 类型。"""
        llm = _mock_llm(["still_valid"])
        result = evaluate_validity_single(_item(), Path("/tmp"), llm)
        assert isinstance(result, SemanticValidity)

    def test_reason_populated(self):
        """reason 字段被正确填充。"""
        llm = _mock_llm(["still_valid"])
        result = evaluate_validity_single(_item(), Path("/tmp"), llm)
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0


# ── evaluate_duplicates_batch ─────────────────────────────────────────────────

class TestEvaluateDuplicatesBatch:
    def test_empty_when_fewer_than_two_items(self):
        """少于 2 条时直接返回空列表，不调用 LLM。"""
        mock = MagicMock()
        result = evaluate_duplicates_batch([], [], mock)
        assert result == []
        mock.complete.assert_not_called()

    def test_returns_merge_suggestions(self):
        """LLM 返回重复对时，结果包含 MergeSuggestion。"""
        review = [_audited(_item(key=f"k{i}", path=f"memory/f{i}.md")) for i in range(3)]
        keep   = [_audited(_item(key="k3", path="memory/f3.md"), action="keep")]

        pairs = [{"index_a": 0, "index_b": 1, "merge_suggestion": "合并建议文本"}]
        llm = _mock_llm([], dedup_pairs=pairs)

        result = evaluate_duplicates_batch(review, keep, llm)
        assert len(result) == 1
        assert isinstance(result[0], MergeSuggestion)
        assert result[0].merge_suggestion == "合并建议文本"

    def test_no_duplicates_returns_empty(self):
        """LLM 返回无重复时，结果为空列表。"""
        review = [_audited(_item(key=f"k{i}", path=f"memory/f{i}.md")) for i in range(2)]
        llm = _mock_llm([], dedup_pairs=[])
        result = evaluate_duplicates_batch(review, [], llm)
        assert result == []

    def test_llm_exception_returns_empty(self):
        """LLM 抛异常时返回空列表，不崩溃。"""
        mock = MagicMock()
        mock.complete.side_effect = Exception("timeout")
        review = [_audited(_item(key=f"k{i}", path=f"memory/f{i}.md")) for i in range(2)]
        result = evaluate_duplicates_batch(review, [], mock)
        assert result == []

    def test_invalid_index_in_response_skipped(self):
        """LLM 返回越界 index 时跳过该对，不崩溃。"""
        review = [_audited(_item(key=f"k{i}", path=f"memory/f{i}.md")) for i in range(2)]
        pairs = [{"index_a": 0, "index_b": 99, "merge_suggestion": "bad"}]
        llm = _mock_llm([], dedup_pairs=pairs)
        result = evaluate_duplicates_batch(review, [], llm)
        assert result == []

    def test_max_items_limit_respected(self):
        """超过 max_items 时，只取前 N 条传给 LLM。"""
        review = [_audited(_item(key=f"k{i}", path=f"memory/f{i}.md")) for i in range(50)]
        llm = _mock_llm([], dedup_pairs=[])

        evaluate_duplicates_batch(review, [], llm, max_items=10)

        call_args = llm.complete.call_args
        user_msg = call_args[1]["user"] if "user" in call_args[1] else call_args[0][1]
        # user message 里的条目不应超过 10 条
        assert user_msg.count("[") <= 11  # 10 条 + 可能的其他 [


# ── apply_llm_results ─────────────────────────────────────────────────────────

class TestApplyLlmResults:
    def test_still_valid_upgraded_to_keep(self):
        """still_valid 的 review 条目 → action_hint 改为 keep。"""
        item = _item(key="k1")
        audited = _audited(item, action="review")

        eval_result = LLMEvalResult(
            validity_results={"k1": SemanticValidity("still_valid", "ok", "keep")}
        )
        updated = apply_llm_results([audited], eval_result)
        assert updated[0].action_hint == "keep"

    def test_outdated_upgraded_to_delete(self):
        """outdated 的 review 条目 → action_hint 改为 delete。"""
        item = _item(key="k1")
        audited = _audited(item, action="review")

        eval_result = LLMEvalResult(
            validity_results={"k1": SemanticValidity("outdated", "old", "delete")}
        )
        updated = apply_llm_results([audited], eval_result)
        assert updated[0].action_hint == "delete"

    def test_uncertain_stays_review(self):
        """uncertain → action_hint 不变，维持 review。"""
        item = _item(key="k1")
        audited = _audited(item, action="review")

        eval_result = LLMEvalResult(
            validity_results={"k1": SemanticValidity("uncertain", "dunno", "review")}
        )
        updated = apply_llm_results([audited], eval_result)
        assert updated[0].action_hint == "review"

    def test_keep_items_not_modified(self):
        """原本 keep 的条目不受 LLM 结果影响。"""
        item = _item(key="k1")
        audited = _audited(item, action="keep")

        eval_result = LLMEvalResult(
            validity_results={"k1": SemanticValidity("outdated", "old", "delete")}
        )
        updated = apply_llm_results([audited], eval_result)
        assert updated[0].action_hint == "keep"  # 不被改变

    def test_delete_items_not_modified(self):
        """原本 delete 的条目不受影响。"""
        item = _item(key="k1")
        audited = _audited(item, action="delete")

        eval_result = LLMEvalResult(
            validity_results={"k1": SemanticValidity("still_valid", "ok", "keep")}
        )
        updated = apply_llm_results([audited], eval_result)
        assert updated[0].action_hint == "delete"

    def test_no_llm_result_for_item_stays_unchanged(self):
        """LLM 没有给出判断的 review 条目 → action_hint 不变。"""
        item = _item(key="k_no_result")
        audited = _audited(item, action="review")

        eval_result = LLMEvalResult(validity_results={})
        updated = apply_llm_results([audited], eval_result)
        assert updated[0].action_hint == "review"

    def test_original_list_not_mutated(self):
        """原始 audit_items 列表不被修改（返回新列表）。"""
        item = _item(key="k1")
        audited = _audited(item, action="review")
        original = [audited]

        eval_result = LLMEvalResult(
            validity_results={"k1": SemanticValidity("still_valid", "ok", "keep")}
        )
        updated = apply_llm_results(original, eval_result)

        # 原列表未变
        assert original[0].action_hint == "review"
        # 新列表已更新
        assert updated[0].action_hint == "keep"

    def test_fallback_key_without_promotion_key(self):
        """没有 promotion_key 的条目，用 source:start-end 作为 key。"""
        item = _item(path="memory/f.md", start=1, end=5)
        item.promotion_key = None  # 无 promotion_key
        audited = _audited(item, action="review")

        fallback_key = "memory/f.md:1-5"
        eval_result = LLMEvalResult(
            validity_results={fallback_key: SemanticValidity("outdated", "old", "delete")}
        )
        updated = apply_llm_results([audited], eval_result)
        assert updated[0].action_hint == "delete"


# ── run_llm_evaluation（整体流程）─────────────────────────────────────────────

class TestRunLlmEvaluation:
    def test_empty_review_no_llm_calls(self):
        """无 review 条目时不调用 LLM，直接返回空结果。"""
        mock = MagicMock()
        items = [_audited(_item(), action="keep")]
        result = run_llm_evaluation(items, Path("/tmp"), mock)

        assert result.validity_results == {}
        assert result.merge_suggestions == []
        mock.complete.assert_not_called()

    def test_review_items_all_evaluated(self):
        """所有 review 条目都有评估结果。"""
        review = [_audited(_item(key=f"k{i}", path=f"memory/f{i}.md")) for i in range(3)]
        llm = _mock_llm(["still_valid", "outdated", "uncertain"])

        result = run_llm_evaluation(review, Path("/tmp"), llm)

        assert len(result.validity_results) == 3

    def test_keep_items_not_evaluated_individually(self):
        """keep 条目不单独调用任务 A。"""
        review = [_audited(_item(key="r1", path="memory/r.md"))]
        keep   = [_audited(_item(key=f"k{i}", path=f"memory/k{i}.md"), action="keep") for i in range(5)]

        call_count = [0]
        def mock_complete(system, user, json_schema=None, max_tokens=256):
            resp = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                resp.parsed = {"verdict": "still_valid", "reason": "ok"}
            else:
                resp.parsed = {"duplicates": []}
            return resp

        mock = MagicMock()
        mock.complete.side_effect = mock_complete

        run_llm_evaluation(review + keep, Path("/tmp"), mock)

        # 任务 A 只调用 1 次（1 条 review），任务 B 调用 1 次，共 2 次
        assert call_count[0] == 2

    def test_returns_llm_eval_result_type(self):
        """返回值是 LLMEvalResult 类型。"""
        mock = MagicMock()
        result = run_llm_evaluation([], Path("/tmp"), mock)
        assert isinstance(result, LLMEvalResult)
