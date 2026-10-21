"""Structural and algorithm checks; cannot validate real analog behavior."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "firmware/gld/src/GldNullingService.cpp"
PLATFORMIO = ROOT / "firmware/platformio.ini"
EXPERIMENT = ROOT / "firmware/platformio.gld1-nulling-experiment.ini"


def trajectory(first, initial_step, maximum=4095, resume=0):
    step = initial_step if resume == 0 else 64
    previous = resume
    current = first if resume == 0 else min(resume + step, maximum)
    out = []
    while current <= maximum:
        out.append((previous, current))
        previous = current
        step = min(step * 2, 64)
        current = min(current + step, maximum)
        if previous == current:
            break
    return out


class NullingExperimentTests(unittest.TestCase):
    def test_experiment_is_opt_in_and_scoped_to_model_one(self):
        source = SOURCE.read_text(encoding="utf-8")
        guard = source.split("// Laboratory-only GLD1 Model 1 experiment.", 1)[1].split("#endif", 1)[0]
        for marker in ("PGL_GLD1_EXPERIMENT_EARLY_EXP_SKIP", "PGL_GLD1_FAST_NULLING",
                       "PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8", "!PGL_GLD_BOARD_PROFILE_GLD2"):
            self.assertIn(marker, guard)
        fast, default = guard.split("#else", 1)
        self.assertRegex(fast, r"EXP_FIRST_CODE\s*=\s*63;")
        self.assertRegex(fast, r"EXP_INIT_STEP\s*=\s*32;")
        self.assertRegex(default, r"EXP_FIRST_CODE\s*=\s*1;")
        self.assertRegex(default, r"EXP_INIT_STEP\s*=\s*1;")
        self.assertNotIn("PGL_GLD1_EXPERIMENT_EARLY_EXP_SKIP", PLATFORMIO.read_text(encoding="utf-8"))
        ini = EXPERIMENT.read_text(encoding="utf-8")
        self.assertIn("extends = env:gld_model_1", ini)
        self.assertRegex(ini, r"(?m)^extra_scripts =\s*$")

    def test_all_eligible_brackets_match_baseline(self):
        baseline = trajectory(1, 1)
        experimental = trajectory(63, 32)
        self.assertEqual([p for p in baseline if p[1] >= 100],
                         [p for p in experimental if p[1] >= 100])
        self.assertEqual([p[1] for p in baseline[:6]], [1, 3, 7, 15, 31, 63])

    def test_resume_path_does_not_change(self):
        for resume in (1, 63, 127, 319, 1023, 4031, 4095):
            with self.subTest(resume=resume):
                self.assertEqual(trajectory(1, 1, resume=resume),
                                 trajectory(63, 32, resume=resume))

    def test_all_checks_and_confirm_remain(self):
        source = SOURCE.read_text(encoding="utf-8")
        for marker in ("current >= EXP_MIN_BRACKET_DAC", "recheckExponentialCrossing(",
                       "confirmCode(", "NULLING_CONFIRM_VERIFY", "stage=final_check"):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
