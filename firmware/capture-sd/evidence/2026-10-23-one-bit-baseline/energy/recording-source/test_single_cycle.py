"""No-device tests for the temporary root-owned one-cycle runner."""
from contextlib import redirect_stdout, redirect_stderr
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import single_cycle as run


class Clock:
    def __init__(self): self.time=100.0
    def now(self): return self.time
    def sleep(self, seconds): self.time+=seconds


class Owner:
    def __init__(self, clock, *, initial=.008, on="normal", off_zero=True, stale=False):
        self.clock=clock; self.initial=initial; self.on=on
        self.off_zero=off_zero; self.stale=stale
        self.state="initial"; self.changed=clock.now(); self.commands=[]; self.logs=[]
    def latest(self):
        at=self.clock.now(); seq=int(at*2)
        if self.state=="initial": current=self.initial
        elif self.state=="off": current=0 if self.off_zero else .008
        elif self.on=="never-active": current=.008
        elif self.on=="never-idle": current=.2
        else: current=.2 if at-self.changed<3 else .008
        return dict(sequence=seq,received=dict(monotonic_ns=int((at-(3 if self.stale else 0))*1e9)),
                    current=dict(avg=current),voltage=dict(avg=4.9),power=dict(avg=current*4.9))
    def command(self,state):
        self.commands.append((state,self.clock.now()))
        self.state=state; self.changed=self.clock.now()
    def log(self,event,**values): self.logs.append((event,values))


class Tests(unittest.TestCase):
    def perform(self, **kwargs):
        clock=Clock(); owner=Owner(clock,**kwargs)
        run.perform_cycle(owner,clock=clock.now,sleep=clock.sleep)
        return owner

    def test_success_one_cycle_with_full_off_time_and_distinct_plateau_samples(self):
        owner=self.perform()
        self.assertEqual([s for s,t in owner.commands],["off","auto"])
        self.assertGreaterEqual(owner.commands[1][1]-owner.commands[0][1],15)
        for event,data in owner.logs:
            if event in ("starting_plateau","terminal_plateau"):
                self.assertEqual(len(data["statistics"]),6)
                self.assertEqual(len({s["sequence"] for s in data["statistics"]}),6)
        self.assertLess(owner.clock.now()-100,30)

    def test_invalid_initial_or_stale_statistics_never_switch_power(self):
        for kwargs in (dict(initial=.2),dict(stale=True)):
            clock=Clock(); owner=Owner(clock,**kwargs)
            with self.subTest(kwargs=kwargs),self.assertRaises(RuntimeError):
                run.perform_cycle(owner,clock=clock.now,sleep=clock.sleep)
            self.assertEqual(owner.commands,[])

    def test_no_active_or_no_idle_never_issues_another_off(self):
        for mode in ("never-active","never-idle"):
            clock=Clock(); owner=Owner(clock,on=mode)
            with self.subTest(mode=mode),self.assertRaisesRegex(RuntimeError,"leave power on"):
                run.perform_cycle(owner,clock=clock.now,sleep=clock.sleep)
            self.assertEqual([s for s,t in owner.commands],["off","auto"])

    def test_failed_off_current_check_never_sends_auto(self):
        clock=Clock(); owner=Owner(clock,off_zero=False)
        with self.assertRaisesRegex(RuntimeError,"baseline was not observed"):
            run.perform_cycle(owner,clock=clock.now,sleep=clock.sleep)
        self.assertEqual([s for s,t in owner.commands],["off"])

    def test_dry_run_does_not_spawn_or_create_directory(self):
        out=run.ROOT/"tmp"/"one-cycle-offline-nonexistent-test"
        self.assertFalse(out.exists())
        with patch.object(sys,"argv",["runner","--out",str(out)]), \
             patch.object(subprocess,"Popen",side_effect=AssertionError("No process allowed")), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(run.main(),0)
        self.assertFalse(out.exists())

    def test_existing_directory_rejected_before_spawn(self):
        with tempfile.TemporaryDirectory(dir=run.ROOT/"tmp") as name:
            out=Path(name)
            with patch.object(sys,"argv",["runner","--out",str(out),"--execute","--owner-confirmed"]), \
                 patch.object(subprocess,"Popen",side_effect=AssertionError("No process allowed")), \
                 redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exc: run.main()
            self.assertEqual(exc.exception.code,2)
            self.assertEqual(list(out.iterdir()),[])


if __name__=="__main__": unittest.main()
