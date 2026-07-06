"""Unit tests for the benchmark harness itself (no engine processes)."""

from __future__ import annotations

import json
import argparse
import sys
import tempfile
import unittest
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BENCH_ROOT))

from recall_bench import baseline, channels, judge, metrics, scenarios, tokens  # noqa: E402
from recall_bench.recorder import normalize_for_hash  # noqa: E402
import run_bench  # noqa: E402


class TokenTests(unittest.TestCase):
    def test_estimate_scales_with_json_density(self) -> None:
        prose = "the quick brown fox jumps over the lazy dog"
        dense = json.dumps({"a": 1, "b": [1, 2, 3], "c": {"d": "e"}})
        self.assertEqual(tokens.estimate(""), 0)
        self.assertGreaterEqual(tokens.estimate(prose), len(prose.split()))
        self.assertGreaterEqual(tokens.estimate(dense), len(dense) // 4)

    def test_dollars(self) -> None:
        self.assertEqual(tokens.dollars(1_000_000, 3.0), 3.0)

    def test_humanize_short_forms(self) -> None:
        self.assertEqual(tokens.humanize(237), "237")
        self.assertEqual(tokens.humanize(5752), "5.8k")
        self.assertEqual(tokens.humanize(10474), "10.5k")
        self.assertEqual(tokens.humanize(1_000_000), "1m")
        self.assertEqual(tokens.humanize(1_200_000), "1.2m")

    def test_parse_amount_accepts_short_forms_and_exact(self) -> None:
        self.assertEqual(tokens.parse_amount("150k"), 150_000)
        self.assertEqual(tokens.parse_amount("1.2m"), 1_200_000)
        self.assertEqual(tokens.parse_amount("5M"), 5_000_000)
        self.assertEqual(tokens.parse_amount("10_000"), 10_000)
        self.assertEqual(tokens.parse_amount(2500), 2500)


class ChannelTests(unittest.TestCase):
    def test_channels_are_disjoint_and_validated(self) -> None:
        self.assertFalse(channels.FIXED_CHANNELS & channels.MARGINAL_CHANNELS)
        self.assertTrue(channels.is_fixed("mcp_tools_list"))
        with self.assertRaises(ValueError):
            channels.validate("made_up_channel")


class HashNormalizationTests(unittest.TestCase):
    def test_volatile_substrings_are_stripped(self) -> None:
        text = (
            'saved at 2026-07-05T12:34:56+00:00 in C:\\Temp\\recall-bench-x1\\proj '
            'with "score": 1.2345'
        )
        normalized = normalize_for_hash(text)
        self.assertNotIn("2026-07-05", normalized)
        self.assertNotIn("recall-bench-x1", normalized)
        self.assertIn('"score": <S>', normalized)


class MetricsTests(unittest.TestCase):
    def _emission(self, channel: str, text: str, *, scenario: str = "s", session: int = 1, turn: int | None = 1) -> dict:
        return {
            "kind": "emission", "channel": channel, "fixed": channels.is_fixed(channel),
            "scenario": scenario, "session": session, "turn": turn,
            **tokens.measure(text), "text": text,
        }

    def test_fixed_floor_uses_per_emission_mean(self) -> None:
        journal = [
            self._emission("session_start_context", "x" * 400, session=1, turn=None),
            self._emission("session_start_context", "x" * 400, session=2, turn=None),
            self._emission("prompt_injection", "y" * 200, session=1, turn=1),
        ]
        report = metrics.compute(journal)
        self.assertEqual(report["tokens"]["fixed_overhead_per_session_est_tokens"], 100)
        self.assertEqual(report["tokens"]["marginal_total_est_tokens"], 50)

    def test_probe_and_static_emissions_stay_out_of_marginal(self) -> None:
        journal = [
            self._emission("tool_result_retrieve", "z" * 400, scenario="probe", session=0, turn=None),
            self._emission("prompt_injection", "y" * 100, session=1, turn=1),
        ]
        report = metrics.compute(journal)
        self.assertEqual(report["tokens"]["marginal_total_est_tokens"], 25)
        self.assertEqual(report["tokens"]["conditional_static_est_tokens"], 100)

    def test_injection_confusion_matrix(self) -> None:
        journal = [
            {"kind": "injection_decision", "should_inject": True, "injected": True},
            {"kind": "injection_decision", "should_inject": False, "injected": True},
            {"kind": "injection_decision", "should_inject": True, "injected": False},
            {"kind": "injection_decision", "should_inject": False, "injected": False},
        ]
        gate = metrics.compute(journal)["injection_gate"]
        self.assertEqual(gate["true_inject"], 1)
        self.assertEqual(gate["false_inject"], 1)
        self.assertEqual(gate["false_suppress"], 1)
        self.assertEqual(gate["accuracy"], 0.5)

    def test_leak_sweep_finds_marker(self) -> None:
        from recall_bench.store_fabricator import SECRET_MARKER

        journal = [self._emission("prompt_injection", f"context {SECRET_MARKER} leaked")]
        leaks = metrics.compute(journal)["secret_leaks"]
        self.assertEqual(leaks["leaks_found"], 1)


class BaselineTests(unittest.TestCase):
    def _report(self, fixed: int, per_turn: float, hit_rate: float) -> dict:
        return {
            "metrics": {
                "tokens": {
                    "fixed_overhead_per_session_est_tokens": fixed,
                    "marginal_per_turn_est_tokens": per_turn,
                    "projected_session_est_tokens_20_turns": fixed + round(per_turn * 20),
                },
                "quality": {"retrieval": {"hit_rate_at_limit": hit_rate}},
                "injection_gate": {"accuracy": 0.9},
                "secret_leaks": {"leaks_found": 0},
            }
        }

    def test_growth_beyond_threshold_is_violation(self) -> None:
        result = baseline.compare(self._report(8000, 240, 1.0), self._report(6000, 230, 1.0))
        self.assertFalse(result["pass"])
        self.assertTrue(any("fixed_overhead" in violation for violation in result["violations"]))

    def test_quality_drop_is_violation(self) -> None:
        result = baseline.compare(self._report(6000, 230, 0.7), self._report(6000, 230, 1.0))
        self.assertFalse(result["pass"])

    def test_stable_run_passes(self) -> None:
        result = baseline.compare(self._report(6100, 232, 1.0), self._report(6000, 230, 1.0))
        self.assertTrue(result["pass"])


class ScenarioSchemaTests(unittest.TestCase):
    def test_all_shipped_scenarios_validate(self) -> None:
        loaded = scenarios.load_all(BENCH_ROOT / "scenarios")
        self.assertGreaterEqual(len(loaded), 5)

    def test_invalid_scenario_rejected(self) -> None:
        with self.assertRaises(ValueError):
            scenarios.validate_scenario({"name": "x", "store": {"tier": "nope"}, "turns": [{"prompt": "p"}]})
        with self.assertRaises(ValueError):
            scenarios.validate_scenario({"name": "x", "store": {"tier": "fresh"}, "turns": [{"prompt": "p", "bogus": 1}]})


class JudgeTests(unittest.TestCase):
    def test_run_config_can_enable_judge_emission_for_normal_mode(self) -> None:
        args = argparse.Namespace(
            config=None,
            mode="normal",
            seed=None,
            sessions=None,
            turn_limit=None,
            emit_judge=True,
            judge_max_per_rubric=3,
        )
        config = run_bench.load_config(args)
        self.assertEqual(config["mode"], "normal")
        self.assertTrue(config["judge"]["emit"])
        self.assertEqual(config["judge"]["max_per_rubric"], 3)

    def test_emit_and_aggregate_round_trip(self) -> None:
        journal = [
            {
                "kind": "emission", "channel": "prompt_injection", "fixed": False,
                "scenario": "s", "session": 1, "turn": 1,
                "chars": 10, "words": 2, "est_tokens": 3, "text": "ctx one",
            },
            {
                "kind": "card_created", "scenario": "s", "session": 1, "id": 5,
                "category": "decisions", "content": "Use SQLite for the ingest store.",
                "summary": "SQLite for ingest.", "source": "finalizer",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tasks_path = Path(tmp) / "judge_tasks.jsonl"
            emitted = judge.emit_tasks(journal, tasks_path, seed=1)
            self.assertEqual(emitted["tasks_emitted"], 2)
            scores_path = Path(tmp) / "judge_scores.jsonl"
            task_ids = [
                json.loads(line)["task_id"]
                for line in tasks_path.read_text(encoding="utf-8").splitlines()
                if '"task_id"' in line and '"kind"' not in line
            ]
            scores_path.write_text(
                "\n".join(
                    json.dumps({"task_id": task_id, "score": 4, "justification": "ok"})
                    for task_id in task_ids
                ) + "\n" + json.dumps({"task_id": "bogus", "score": 9}) + "\n",
                encoding="utf-8",
            )
            summary = judge.aggregate(tasks_path, scores_path)
            self.assertEqual(summary["scored"], 2)
            self.assertEqual(summary["invalid"], ["bogus"])
            self.assertTrue(all(value == 4.0 for value in summary["mean_by_rubric"].values()))


if __name__ == "__main__":
    unittest.main()
