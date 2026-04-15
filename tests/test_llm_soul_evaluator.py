"""
test_llm_soul_evaluator.py · LLM 语义评估层（soul）单元测试

全部使用 mock LLM，不需要真实 API key。
覆盖：C2 精判、C4-a 内部冲突检测、C4-b IDENTITY 一致性检测、
      LLMSoulEvalResult 属性、run_llm_soul_evaluation 整体流程、错误处理。
"""
from unittest.mock import MagicMock

import pytest

from src.analyzers.llm_soul_evaluator import (
    C2ParagraphClassification,
    C4Conflict,
    C4IdentityMismatch,
    LLMSoulEvalResult,
    evaluate_c2_paragraphs,
    evaluate_c4a_conflicts,
    evaluate_c4b_identity,
    run_llm_soul_evaluation,
)


# ── 测试辅助 ───────────────────────────────────────────────────────────────────

def _mock_llm_c2(classification: str, reason: str = "test reason"):
    """构造返回固定 C2 分类结果的 mock LLM。"""
    mock = MagicMock()
    mock.complete.return_value = MagicMock(
        parsed={"classification": classification, "reason": reason}
    )
    return mock


def _mock_llm_c4a(conflicts: list):
    """构造返回固定 C4-a 冲突列表的 mock LLM。"""
    mock = MagicMock()
    mock.complete.return_value = MagicMock(parsed={"conflicts": conflicts})
    return mock


def _mock_llm_c4b(mismatches: list):
    """构造返回固定 C4-b 不一致列表的 mock LLM。"""
    mock = MagicMock()
    mock.complete.return_value = MagicMock(parsed={"mismatches": mismatches})
    return mock


SAMPLE_SOUL = """# SOUL.md

## Core Truths
Be genuinely helpful. Have opinions.

## Boundaries
Private things stay private.

## Vibe
Be concise and direct.

## Continuity
Each session, you wake up fresh.
"""

SAMPLE_IDENTITY = """# IDENTITY.md

Name: TestBot
Vibe: serious and methodical
"""


# ── evaluate_c2_paragraphs ─────────────────────────────────────────────────────

class TestEvaluateC2Paragraphs:
    def test_persona_content_classification(self):
        """LLM 返回 persona_content → 正确映射到结果。"""
        llm = _mock_llm_c2("persona_content", "这是身份描述")
        results = evaluate_c2_paragraphs(["Be helpful and honest."], llm)
        assert len(results) == 1
        assert results[0].classification == "persona_content"
        assert results[0].reason == "这是身份描述"

    def test_task_instruction_classification(self):
        """LLM 返回 task_instruction → 正确映射。"""
        llm = _mock_llm_c2("task_instruction", "这是任务指令")
        results = evaluate_c2_paragraphs(["When email arrives, reply immediately."], llm)
        assert len(results) == 1
        assert results[0].classification == "task_instruction"

    def test_mixed_classification(self):
        """LLM 返回 mixed → 正确映射。"""
        llm = _mock_llm_c2("mixed", "两者混合")
        results = evaluate_c2_paragraphs(["Be helpful. Also, run tests first."], llm)
        assert len(results) == 1
        assert results[0].classification == "mixed"

    def test_paragraph_hint_truncated_to_60(self):
        """paragraph_hint 超过 60 字时被截断并加省略号。"""
        llm = _mock_llm_c2("persona_content")
        long_para = "A" * 80
        results = evaluate_c2_paragraphs([long_para], llm)
        assert results[0].paragraph_hint == "A" * 60 + "…"

    def test_paragraph_hint_exact_60_no_ellipsis(self):
        """paragraph_hint 恰好 60 字时不加省略号。"""
        llm = _mock_llm_c2("persona_content")
        exact_para = "B" * 60
        results = evaluate_c2_paragraphs([exact_para], llm)
        assert results[0].paragraph_hint == "B" * 60
        assert "…" not in results[0].paragraph_hint

    def test_empty_list_returns_empty(self):
        """空段落列表 → 返回空结果，不调用 LLM。"""
        mock = MagicMock()
        results = evaluate_c2_paragraphs([], mock)
        assert results == []
        mock.complete.assert_not_called()

    def test_multiple_paragraphs_each_evaluated(self):
        """多段落时每段都调用一次 LLM。"""
        mock = MagicMock()
        mock.complete.side_effect = [
            MagicMock(parsed={"classification": "persona_content", "reason": "ok1"}),
            MagicMock(parsed={"classification": "task_instruction", "reason": "ok2"}),
            MagicMock(parsed={"classification": "mixed", "reason": "ok3"}),
        ]
        results = evaluate_c2_paragraphs(["p1", "p2", "p3"], mock)
        assert len(results) == 3
        assert mock.complete.call_count == 3

    def test_llm_parse_failure_skips_paragraph(self):
        """LLM 返回 None parsed → 跳过该段落，不崩溃。"""
        mock = MagicMock()
        mock.complete.return_value = MagicMock(parsed=None)
        results = evaluate_c2_paragraphs(["some paragraph"], mock)
        assert results == []

    def test_llm_missing_classification_skips(self):
        """LLM 返回缺少 classification 字段 → 跳过。"""
        mock = MagicMock()
        mock.complete.return_value = MagicMock(parsed={"reason": "ok"})
        results = evaluate_c2_paragraphs(["some paragraph"], mock)
        assert results == []

    def test_llm_exception_skips_paragraph(self):
        """LLM 抛异常 → 跳过该段落，不崩溃。"""
        mock = MagicMock()
        mock.complete.side_effect = Exception("network error")
        results = evaluate_c2_paragraphs(["some paragraph"], mock)
        assert results == []

    def test_partial_failure_continues(self):
        """部分段落 LLM 失败 → 其余段落正常处理。"""
        mock = MagicMock()
        mock.complete.side_effect = [
            Exception("fail"),
            MagicMock(parsed={"classification": "persona_content", "reason": "ok"}),
        ]
        results = evaluate_c2_paragraphs(["fail_para", "ok_para"], mock)
        assert len(results) == 1
        assert results[0].classification == "persona_content"

    def test_returns_c2paragraphclassification_type(self):
        """返回值是 C2ParagraphClassification 类型。"""
        llm = _mock_llm_c2("persona_content")
        results = evaluate_c2_paragraphs(["test"], llm)
        assert isinstance(results[0], C2ParagraphClassification)


# ── evaluate_c4a_conflicts ─────────────────────────────────────────────────────

class TestEvaluateC4aConflicts:
    def test_no_conflicts_returns_empty(self):
        """LLM 返回空冲突列表 → 返回空结果。"""
        llm = _mock_llm_c4a([])
        results = evaluate_c4a_conflicts(SAMPLE_SOUL, llm)
        assert results == []

    def test_single_conflict_parsed(self):
        """LLM 返回一对冲突 → 正确解析。"""
        conflicts = [{
            "statement_a": "谨慎行事，先确认",
            "statement_b": "快速执行，不要拖慢",
            "severity": "high",
            "reason": "核心行为矛盾",
        }]
        llm = _mock_llm_c4a(conflicts)
        results = evaluate_c4a_conflicts(SAMPLE_SOUL, llm)
        assert len(results) == 1
        assert results[0].statement_a == "谨慎行事，先确认"
        assert results[0].statement_b == "快速执行，不要拖慢"
        assert results[0].severity == "high"
        assert results[0].reason == "核心行为矛盾"

    def test_multiple_conflicts_parsed(self):
        """LLM 返回多对冲突 → 全部解析。"""
        conflicts = [
            {"statement_a": "A1", "statement_b": "B1", "severity": "high", "reason": "r1"},
            {"statement_a": "A2", "statement_b": "B2", "severity": "medium", "reason": "r2"},
        ]
        llm = _mock_llm_c4a(conflicts)
        results = evaluate_c4a_conflicts(SAMPLE_SOUL, llm)
        assert len(results) == 2

    def test_statement_truncated_to_60(self):
        """statement 超过 60 字时被截断。"""
        long_stmt = "X" * 80
        conflicts = [{
            "statement_a": long_stmt,
            "statement_b": "short",
            "severity": "medium",
            "reason": "test",
        }]
        llm = _mock_llm_c4a(conflicts)
        results = evaluate_c4a_conflicts(SAMPLE_SOUL, llm)
        assert results[0].statement_a == "X" * 60 + "…"

    def test_missing_statement_skips_item(self):
        """缺少 statement_a 或 statement_b 的条目被跳过。"""
        conflicts = [
            {"statement_a": "", "statement_b": "B", "severity": "high", "reason": "r"},
            {"statement_a": "A", "statement_b": "", "severity": "high", "reason": "r"},
        ]
        llm = _mock_llm_c4a(conflicts)
        results = evaluate_c4a_conflicts(SAMPLE_SOUL, llm)
        assert results == []

    def test_llm_parse_failure_returns_empty(self):
        """LLM 返回 None parsed → 返回空列表，不崩溃。"""
        mock = MagicMock()
        mock.complete.return_value = MagicMock(parsed=None)
        results = evaluate_c4a_conflicts(SAMPLE_SOUL, mock)
        assert results == []

    def test_llm_exception_returns_empty(self):
        """LLM 抛异常 → 返回空列表，不崩溃。"""
        mock = MagicMock()
        mock.complete.side_effect = Exception("timeout")
        results = evaluate_c4a_conflicts(SAMPLE_SOUL, mock)
        assert results == []

    def test_content_truncated_to_4000_chars(self):
        """超长 SOUL.md 只取前 4000 字传给 LLM。"""
        long_soul = "A" * 10000
        llm = _mock_llm_c4a([])
        evaluate_c4a_conflicts(long_soul, llm)
        call_args = llm.complete.call_args
        user_msg = call_args[1]["user"] if "user" in call_args[1] else call_args[0][1]
        # user_msg 包含截断后的内容，不超过 4000 字
        assert len(user_msg) < 10000

    def test_severity_defaults_to_medium(self):
        """severity 缺失时默认为 medium。"""
        conflicts = [{"statement_a": "A", "statement_b": "B", "reason": "r"}]
        llm = _mock_llm_c4a(conflicts)
        results = evaluate_c4a_conflicts(SAMPLE_SOUL, llm)
        assert results[0].severity == "medium"

    def test_returns_c4conflict_type(self):
        """返回值是 C4Conflict 类型。"""
        conflicts = [{"statement_a": "A", "statement_b": "B", "severity": "high", "reason": "r"}]
        llm = _mock_llm_c4a(conflicts)
        results = evaluate_c4a_conflicts(SAMPLE_SOUL, llm)
        assert isinstance(results[0], C4Conflict)


# ── evaluate_c4b_identity ──────────────────────────────────────────────────────

class TestEvaluateC4bIdentity:
    def test_empty_identity_skips_without_calling_llm(self):
        """identity_content 为空 → 直接返回空列表，不调用 LLM。"""
        mock = MagicMock()
        results = evaluate_c4b_identity(SAMPLE_SOUL, "", mock)
        assert results == []
        mock.complete.assert_not_called()

    def test_whitespace_only_identity_skips(self):
        """identity_content 只有空白字符 → 跳过。"""
        mock = MagicMock()
        results = evaluate_c4b_identity(SAMPLE_SOUL, "   \n  ", mock)
        assert results == []
        mock.complete.assert_not_called()

    def test_no_mismatches_returns_empty(self):
        """LLM 返回空不一致列表 → 返回空结果。"""
        llm = _mock_llm_c4b([])
        results = evaluate_c4b_identity(SAMPLE_SOUL, SAMPLE_IDENTITY, llm)
        assert results == []

    def test_single_mismatch_parsed(self):
        """LLM 返回一处不一致 → 正确解析。"""
        mismatches = [{
            "soul_description": "随性发挥，轻松应对",
            "identity_description": "严谨认真，有条不紊",
            "severity": "high",
            "reason": "风格冲突",
        }]
        llm = _mock_llm_c4b(mismatches)
        results = evaluate_c4b_identity(SAMPLE_SOUL, SAMPLE_IDENTITY, llm)
        assert len(results) == 1
        assert results[0].soul_description == "随性发挥，轻松应对"
        assert results[0].severity == "high"
        assert results[0].reason == "风格冲突"

    def test_descriptions_truncated_to_60(self):
        """soul_description 和 identity_description 超过 60 字时被截断。"""
        long_desc = "Y" * 80
        mismatches = [{
            "soul_description": long_desc,
            "identity_description": long_desc,
            "severity": "medium",
            "reason": "test",
        }]
        llm = _mock_llm_c4b(mismatches)
        results = evaluate_c4b_identity(SAMPLE_SOUL, SAMPLE_IDENTITY, llm)
        assert results[0].soul_description == "Y" * 60 + "…"
        assert results[0].identity_description == "Y" * 60 + "…"

    def test_missing_descriptions_skips_item(self):
        """soul_description 或 identity_description 为空 → 跳过。"""
        mismatches = [
            {"soul_description": "", "identity_description": "ok", "severity": "high", "reason": "r"},
            {"soul_description": "ok", "identity_description": "", "severity": "high", "reason": "r"},
        ]
        llm = _mock_llm_c4b(mismatches)
        results = evaluate_c4b_identity(SAMPLE_SOUL, SAMPLE_IDENTITY, llm)
        assert results == []

    def test_llm_parse_failure_returns_empty(self):
        """LLM 返回 None parsed → 返回空列表，不崩溃。"""
        mock = MagicMock()
        mock.complete.return_value = MagicMock(parsed=None)
        results = evaluate_c4b_identity(SAMPLE_SOUL, SAMPLE_IDENTITY, mock)
        assert results == []

    def test_llm_exception_returns_empty(self):
        """LLM 抛异常 → 返回空列表，不崩溃。"""
        mock = MagicMock()
        mock.complete.side_effect = Exception("api error")
        results = evaluate_c4b_identity(SAMPLE_SOUL, SAMPLE_IDENTITY, mock)
        assert results == []

    def test_soul_and_identity_content_in_prompt(self):
        """user message 中包含 SOUL.md 和 IDENTITY.md 内容。"""
        llm = _mock_llm_c4b([])
        evaluate_c4b_identity(SAMPLE_SOUL, SAMPLE_IDENTITY, llm)
        call_args = llm.complete.call_args
        user_msg = call_args[1]["user"] if "user" in call_args[1] else call_args[0][1]
        assert "SOUL.md" in user_msg
        assert "IDENTITY.md" in user_msg

    def test_returns_c4identitymismatch_type(self):
        """返回值是 C4IdentityMismatch 类型。"""
        mismatches = [{
            "soul_description": "casual",
            "identity_description": "formal",
            "severity": "medium",
            "reason": "style gap",
        }]
        llm = _mock_llm_c4b(mismatches)
        results = evaluate_c4b_identity(SAMPLE_SOUL, SAMPLE_IDENTITY, llm)
        assert isinstance(results[0], C4IdentityMismatch)


# ── LLMSoulEvalResult 属性 ────────────────────────────────────────────────────

class TestLLMSoulEvalResultProperties:
    def test_has_task_instructions_true_when_task_instruction(self):
        """c2_classifications 中有 task_instruction → has_task_instructions=True。"""
        result = LLMSoulEvalResult(
            c2_classifications=[
                C2ParagraphClassification("p1", "task_instruction", "reason"),
            ]
        )
        assert result.has_task_instructions is True

    def test_has_task_instructions_true_when_mixed(self):
        """c2_classifications 中有 mixed → has_task_instructions=True。"""
        result = LLMSoulEvalResult(
            c2_classifications=[
                C2ParagraphClassification("p1", "mixed", "reason"),
            ]
        )
        assert result.has_task_instructions is True

    def test_has_task_instructions_false_when_all_persona(self):
        """全部是 persona_content → has_task_instructions=False。"""
        result = LLMSoulEvalResult(
            c2_classifications=[
                C2ParagraphClassification("p1", "persona_content", "ok"),
                C2ParagraphClassification("p2", "persona_content", "ok"),
            ]
        )
        assert result.has_task_instructions is False

    def test_has_task_instructions_false_when_empty(self):
        """c2_classifications 为空 → has_task_instructions=False。"""
        result = LLMSoulEvalResult()
        assert result.has_task_instructions is False

    def test_high_severity_count_counts_conflicts(self):
        """高严重度冲突计入 high_severity_count。"""
        result = LLMSoulEvalResult(
            c4_conflicts=[
                C4Conflict("A", "B", "high", "r"),
                C4Conflict("C", "D", "medium", "r"),
                C4Conflict("E", "F", "high", "r"),
            ]
        )
        assert result.high_severity_count == 2

    def test_high_severity_count_counts_mismatches(self):
        """高严重度不一致计入 high_severity_count。"""
        result = LLMSoulEvalResult(
            c4_mismatches=[
                C4IdentityMismatch("s1", "i1", "high", "r"),
                C4IdentityMismatch("s2", "i2", "medium", "r"),
            ]
        )
        assert result.high_severity_count == 1

    def test_high_severity_count_combined(self):
        """冲突和不一致中的高严重度合计。"""
        result = LLMSoulEvalResult(
            c4_conflicts=[C4Conflict("A", "B", "high", "r")],
            c4_mismatches=[C4IdentityMismatch("s", "i", "high", "r")],
        )
        assert result.high_severity_count == 2

    def test_high_severity_count_zero_when_all_medium(self):
        """全部 medium → high_severity_count=0。"""
        result = LLMSoulEvalResult(
            c4_conflicts=[C4Conflict("A", "B", "medium", "r")],
            c4_mismatches=[C4IdentityMismatch("s", "i", "medium", "r")],
        )
        assert result.high_severity_count == 0

    def test_default_empty_result(self):
        """默认构造：所有列表为空，llm_error=None。"""
        result = LLMSoulEvalResult()
        assert result.c2_classifications == []
        assert result.c4_conflicts == []
        assert result.c4_mismatches == []
        assert result.llm_error is None


# ── run_llm_soul_evaluation（整体流程）────────────────────────────────────────

class TestRunLlmSoulEvaluation:
    def _make_ordered_llm(self, c2_result, c4a_result, c4b_result):
        """
        构造按顺序调用的 mock LLM：
        前 N 次调用（C2 精判）→ 返回 c2_result（列表，每次取一条）
        然后（C4-a）→ 返回 c4a_result
        然后（C4-b）→ 返回 c4b_result
        """
        call_count = [0]
        c2_list = c2_result  # list of classification strings

        def complete(system, user, json_schema=None, max_tokens=256):
            resp = MagicMock()
            idx = call_count[0]
            call_count[0] += 1

            if idx < len(c2_list):
                # C2 精判
                resp.parsed = {"classification": c2_list[idx], "reason": f"reason{idx}"}
            elif idx == len(c2_list):
                # C4-a
                resp.parsed = {"conflicts": c4a_result}
            else:
                # C4-b
                resp.parsed = {"mismatches": c4b_result}
            return resp

        mock = MagicMock()
        mock.complete.side_effect = complete
        mock._call_count = call_count
        return mock

    def test_no_suspicious_paragraphs_no_c2_calls(self):
        """无可疑段落 → C2 精判不调用 LLM。"""
        call_count = [0]

        def complete(system, user, json_schema=None, max_tokens=256):
            resp = MagicMock()
            call_count[0] += 1
            # 只有 C4-a 和 C4-b 两次调用
            if call_count[0] == 1:
                resp.parsed = {"conflicts": []}
            else:
                resp.parsed = {"mismatches": []}
            return resp

        mock = MagicMock()
        mock.complete.side_effect = complete

        result = run_llm_soul_evaluation(
            soul_content=SAMPLE_SOUL,
            suspicious_paragraphs=[],
            identity_content=SAMPLE_IDENTITY,
            llm_client=mock,
        )
        assert result.c2_classifications == []
        # C4-a 和 C4-b 各调用一次
        assert call_count[0] == 2

    def test_with_suspicious_paragraphs_runs_c2(self):
        """有可疑段落 → C2 精判被执行。"""
        llm = self._make_ordered_llm(["task_instruction"], [], [])
        result = run_llm_soul_evaluation(
            soul_content=SAMPLE_SOUL,
            suspicious_paragraphs=["When you receive tasks, execute immediately."],
            identity_content="",  # 空 identity，C4-b 跳过
            llm_client=llm,
        )
        assert len(result.c2_classifications) == 1
        assert result.c2_classifications[0].classification == "task_instruction"

    def test_c4a_conflicts_in_result(self):
        """C4-a 冲突被正确收录到结果。"""
        conflicts = [{"statement_a": "X", "statement_b": "Y", "severity": "high", "reason": "r"}]
        llm = self._make_ordered_llm([], conflicts, [])
        result = run_llm_soul_evaluation(
            soul_content=SAMPLE_SOUL,
            suspicious_paragraphs=[],
            identity_content="",
            llm_client=llm,
        )
        assert len(result.c4_conflicts) == 1
        assert result.c4_conflicts[0].severity == "high"

    def test_c4b_skipped_when_no_identity(self):
        """identity_content 为空 → C4-b 跳过，mismatches 为空。"""
        call_count = [0]

        def complete(system, user, json_schema=None, max_tokens=256):
            resp = MagicMock()
            call_count[0] += 1
            resp.parsed = {"conflicts": []}
            return resp

        mock = MagicMock()
        mock.complete.side_effect = complete

        result = run_llm_soul_evaluation(
            soul_content=SAMPLE_SOUL,
            suspicious_paragraphs=[],
            identity_content="",
            llm_client=mock,
        )
        assert result.c4_mismatches == []

    def test_c4b_runs_when_identity_present(self):
        """identity_content 非空 → C4-b 被执行。"""
        mismatches = [{
            "soul_description": "casual style",
            "identity_description": "serious style",
            "severity": "medium",
            "reason": "style gap",
        }]
        llm = self._make_ordered_llm([], [], mismatches)
        result = run_llm_soul_evaluation(
            soul_content=SAMPLE_SOUL,
            suspicious_paragraphs=[],
            identity_content=SAMPLE_IDENTITY,
            llm_client=llm,
        )
        assert len(result.c4_mismatches) == 1

    def test_returns_llm_soul_eval_result_type(self):
        """返回值是 LLMSoulEvalResult 类型。"""
        llm = self._make_ordered_llm([], [], [])
        result = run_llm_soul_evaluation(
            soul_content=SAMPLE_SOUL,
            suspicious_paragraphs=[],
            identity_content="",
            llm_client=llm,
        )
        assert isinstance(result, LLMSoulEvalResult)

    def test_has_task_instructions_property_works_end_to_end(self):
        """完整流程：has_task_instructions 属性正确。"""
        llm = self._make_ordered_llm(["task_instruction", "persona_content"], [], [])
        result = run_llm_soul_evaluation(
            soul_content=SAMPLE_SOUL,
            suspicious_paragraphs=["task para", "persona para"],
            identity_content="",
            llm_client=llm,
        )
        assert result.has_task_instructions is True

    def test_c4a_failure_does_not_break_c4b(self):
        """C4-a LLM 失败 → C4-b 仍然执行（如果 identity 非空）。"""
        call_count = [0]

        def complete(system, user, json_schema=None, max_tokens=256):
            resp = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("C4-a failed")  # C4-a 报错
            else:
                resp.parsed = {"mismatches": []}  # C4-b 正常
            return resp

        mock = MagicMock()
        mock.complete.side_effect = complete

        result = run_llm_soul_evaluation(
            soul_content=SAMPLE_SOUL,
            suspicious_paragraphs=[],
            identity_content=SAMPLE_IDENTITY,
            llm_client=mock,
        )
        # C4-a 失败 → 空列表，C4-b 正常 → 空列表
        assert result.c4_conflicts == []
        assert result.c4_mismatches == []
        assert result.llm_error is None  # 错误不冒泡到顶层
