"""Source-contract checks for the GLD1 Model 1 nulling sample counts.

These checks do not replace calibration tests with an actual sensor board.
"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "firmware/gld/src/GldNullingService.cpp"
PLATFORMIO = ROOT / "firmware/platformio.ini"


def section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


class FastNullingScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.ini = PLATFORMIO.read_text(encoding="utf-8")

    def test_sample_counts_are_guarded_and_other_profiles_unchanged(self):
        guard = ("#if defined(PGL_GLD1_FAST_NULLING) && "
                 "PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8 && !PGL_GLD_BOARD_PROFILE_GLD2")
        guarded = section(self.source, guard, "#endif")
        fast, default = guarded.split("#else", 1)
        for text, average, confirm in ((fast, 6, 8), (default, 8, 10)):
            self.assertRegex(text, rf"AVG_COUNT\s*=\s*{average}\s*;")
            self.assertRegex(text, rf"CONFIRM_COUNT\s*=\s*{confirm}\s*;")

    def test_fast_flag_is_specific_to_model_one(self):
        environments = dict(re.findall(r"(?ms)^\[([^\]]+)\]\s*\n(.*?)(?=^\[|\Z)", self.ini))
        flagged = [name for name, body in environments.items()
                   if "-DPGL_GLD1_FAST_NULLING=1" in body]
        self.assertEqual(flagged, ["env:gld_model_1"])

    def test_measurement_and_final_guards_remain_present(self):
        for marker in (
            "constexpr uint8_t  STABILITY_WINDOW_COUNT  = 3;",
            "constexpr uint8_t  STABLE_GAIN_SAMPLES  = 3;",
            "constexpr uint8_t  MAX_AVERAGE_ATTEMPTS = AVG_COUNT + 16;",
            "recheckExponentialCrossing(",
            "readSettledAverage(ads, ch, CONFIRM_COUNT, tickFn, stabilityToleranceV)",
            "NULLING_CONFIRM_VERIFY",
            "NULLING_CH_FAIL ch=%u sensor=%s stage=final_check",
        ):
            self.assertIn(marker, self.source)


if __name__ == "__main__":
    unittest.main()
