"""Verify controller handoff preserves live workers, requests, and deadlines."""
import json
import pathlib
import sys
import tempfile
import time
import unittest

from supervisor import AdoptedProcess, restore_lanes, spawn, stop


class AdoptionTests(unittest.TestCase):
    def test_adopt_preserves_request_and_original_start_time(self):
        with tempfile.TemporaryDirectory(prefix="adoption-") as td:
            run=pathlib.Path(td)
            worker=spawn([sys.executable,"-c","import time; time.sleep(60)",run.name],run/"worker.log")
            proxy=spawn([sys.executable,"-c","import time; time.sleep(60)",run.name],run/"proxy.log")
            try:
                time.sleep(.1)
                (run/"manifest.json").write_text(json.dumps({"endpoints":[]}))
                (run/"events.jsonl").write_text(json.dumps(dict(event="trial_started",job="job",ts=1234))+"\n")
                row=dict(event="request_started",request_id="in-flight",session_id="job",request_sha256="sha",ts=1250)
                (run/"bonsai.jsonl").write_text(json.dumps(row)+"\n")
                saved={"lanes":[dict(label="bonsai",proxy_pid=proxy.pid,worker_pid=worker.pid,job="job",task="session-window-debug",quarantined=None)]}
                lane=restore_lanes(run,saved)[0]
                self.assertIsNone(lane["worker"].poll())
                self.assertEqual(lane["worker"].pid,worker.pid)
                self.assertEqual(lane["started"],1234)
                self.assertIn("in-flight",lane["progress"].pending)
                self.assertEqual(lane["offset"],(run/"bonsai.jsonl").stat().st_size)
                self.assertEqual(lane["progress"].event(dict(row,request_id="duplicate")),"duplicate_request_in_same_session")
                stop(lane["worker"])
                self.assertIsNotNone(worker.poll())
            finally:
                stop(worker)
                stop(proxy)

    def test_unrelated_process_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            worker=spawn([sys.executable,"-c","import time; time.sleep(60)","actual-owner"],pathlib.Path(td)/"log")
            try:
                time.sleep(.1)
                with self.assertRaises(RuntimeError):
                    AdoptedProcess(worker.pid,"different-owner")
                self.assertIsNone(worker.poll())
            finally:
                stop(worker)

    def test_exited_process_can_be_reconciled_from_harbor_result(self):
        with tempfile.TemporaryDirectory() as td:
            worker=spawn([sys.executable,"-c","pass"],pathlib.Path(td)/"log")
            worker.wait(timeout=5)
            self.assertEqual(AdoptedProcess(worker.pid,"unused").poll(),0)


if __name__=="__main__":
    unittest.main(verbosity=2)
