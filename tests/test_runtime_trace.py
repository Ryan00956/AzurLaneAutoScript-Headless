import json
import tempfile
import unittest
from pathlib import Path

from alas_headless.runtime_trace import (
    RuntimeTraceError,
    RuntimeTraceRecorder,
    RuntimeProcessSample,
    summarize_runtime_trace,
)


class RuntimeTraceTests(unittest.TestCase):
    def test_disabled_trace_has_no_file_or_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            trace = RuntimeTraceRecorder(path)
            self.assertFalse(trace.emit("observer.request"))
            summary = trace.close()
            self.assertFalse(path.exists())
            self.assertEqual(summary["recorded"], 0)

    def test_trace_writes_safe_events_and_summarizes_latency(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            trace = RuntimeTraceRecorder(path, enabled=True, run_id="run-test")
            trace.emit(
                "observer.request",
                duration_ns=100,
                fields={"endpoint": "/v1/state", "snapshot_age_ms": 20},
            )
            trace.emit(
                "observer.request",
                outcome="timeout",
                duration_ns=300,
                fields={"endpoint": "/v1/state"},
            )
            trace.close()
            records = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([record["sequence"] for record in records], [1, 2])
            summary = summarize_runtime_trace(path)
            event = summary["events"]["observer.request"]
            self.assertEqual(event["mean_ns"], 200)
            self.assertEqual(event["p95_ns"], 300)
            self.assertEqual(event["error_rate"], 0.5)

    def test_sensitive_fields_and_exception_messages_are_not_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = RuntimeTraceRecorder(
                Path(directory) / "trace.jsonl", enabled=True
            )
            with self.assertRaises(RuntimeTraceError):
                trace.emit("bad", fields={"account_token": "secret"})
            summary = trace.close()
            self.assertEqual(summary["invalid"], 1)

    def test_close_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = RuntimeTraceRecorder(
                Path(directory) / "trace.jsonl", enabled=True
            )
            trace.close()
            self.assertEqual(trace.close()["writer_error"], None)

    def test_span_records_only_exception_type(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            trace = RuntimeTraceRecorder(path, enabled=True)
            with self.assertRaisesRegex(ValueError, "must-not-be-persisted"):
                with trace.span("runtime.phase", {"phase": "start"}):
                    raise ValueError("must-not-be-persisted")
            trace.close()
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("must-not-be-persisted", raw)
            self.assertEqual(json.loads(raw)["fields"]["exception_type"], "ValueError")

    def test_lifecycle_action_and_process_samples_use_stable_events(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            trace = RuntimeTraceRecorder(path, enabled=True)
            with trace.lifecycle_span("kvm", "kvm-default-v1", "start"):
                pass
            with trace.alas_action_span("campaign.run", "map-wait"):
                pass
            trace.process_sample(
                RuntimeProcessSample(
                    "game", cpu_time_ns=10, rss_bytes=20, read_bytes=30
                )
            )
            trace.close()
            events = [json.loads(line)["event"] for line in path.read_text().splitlines()]
            self.assertEqual(
                events,
                ["runtime.lifecycle", "alas.action", "runtime.process.sample"],
            )
            with self.assertRaises(RuntimeTraceError):
                RuntimeProcessSample("game", rss_bytes=-1).fields()


if __name__ == "__main__":
    unittest.main()
