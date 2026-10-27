import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from supervisor import Progress, spawn, stop
from guardian import terminate_owned


def event(rid="a", digest="hash", session="trial1", ts=0):
    return dict(event="request_started",request_id=rid,request_sha256=digest,session_id=session,ts=ts)


def slot(n, busy=True):
    return [dict(is_processing=busy,id_task=1,n_prompt_tokens_processed=100,
                 next_token=[dict(n_decoded=n)])]


class WatchdogTests(unittest.TestCase):
    def test_identical_request_quarantines_even_after_success(self):
        p=Progress(0)
        self.assertIsNone(p.event(event()))
        p.event(dict(event="response_sent",request_id="a"))
        self.assertEqual(p.event(event("b")),"duplicate_request_in_same_session")

    def test_same_prompt_different_trial_is_not_duplicate(self):
        p=Progress(0)
        p.event(event())
        p.event(dict(event="response_sent",request_id="a"))
        self.assertIsNone(p.event(event("b",session="trial2")))

    def test_overlap_and_proxy_error(self):
        p=Progress(0)
        p.event(event())
        self.assertEqual(p.event(event("b",digest="new")),"overlapping_requests")
        self.assertEqual(p.event(dict(event="proxy_error",request_id="a")),"proxy_error")

    def test_slow_but_progressing_for_hours_is_healthy(self):
        p=Progress(0)
        p.event(event())
        for t in range(0,7200,15):
            self.assertIsNone(p.poll(t,slot(t+1)))

    def test_frozen_generation_stops_in_three_minutes(self):
        p=Progress(0)
        p.event(event())
        self.assertIsNone(p.poll(0,slot(1)))
        self.assertEqual(p.poll(181,slot(1)),"no_backend_token_progress_180s")

    def test_lost_request_stops(self):
        p=Progress(0)
        p.event(event())
        p.poll(0,[])
        self.assertEqual(p.poll(181,[]),"request_without_backend_work_180s")

    def test_orphan_backend_stops(self):
        p=Progress(0)
        self.assertIsNone(p.poll(1,slot(1)))
        self.assertEqual(p.poll(62,slot(2)),"orphan_backend_generation_60s")

    def test_health_failure_requires_three_and_resets(self):
        p=Progress(0)
        self.assertIsNone(p.poll(0,[],False))
        self.assertIsNone(p.poll(15,[],False))
        self.assertIsNone(p.poll(30,[]))
        p.poll(45,[],False)
        p.poll(60,[],False)
        self.assertEqual(p.poll(75,[],False),"three_failed_health_checks")

    def test_guardian_terminates_only_owned_process(self):
        with tempfile.TemporaryDirectory() as td:
            proc=spawn([sys.executable,"-c","import time; time.sleep(60)","test-owned-marker"],pathlib.Path(td)/"log")
            try:
                terminate_owned(proc.pid,"wrong-marker")
                self.assertIsNone(proc.poll())
                terminate_owned(proc.pid,"test-owned-marker")
                self.assertEqual(proc.wait(timeout=5),-15)
            finally:
                stop(proc)


if __name__ == "__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(WatchdogTests))
    if result.wasSuccessful():
        pathlib.Path(__file__).with_name("watchdog-validation.json").write_text(json.dumps({"passed":result.testsRun}))
    sys.exit(not result.wasSuccessful())
