"""Guard and integration checks; physical calibration requires separate evidence."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[3]
SERVICE = (ROOT / "firmware/gld/src/GldNullingService.cpp").read_text(encoding="utf-8")
MAIN = (ROOT / "firmware/gld/src/GldUnifiedMain.cpp").read_text(encoding="utf-8")
INI = (ROOT / "firmware/platformio.ini").read_text(encoding="utf-8")


class NullingStabilityScopeTests(unittest.TestCase):
    def test_guard_specific_to_fast_model_one(self):
        guard = SERVICE.split("constexpr bool GLD1_STABILITY_GUARD = true", 1)[0]
        for token in ("PGL_GLD1_FAST_NULLING", "PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8",
                      "!PGL_GLD_BOARD_PROFILE_GLD2"):
            self.assertIn(token, guard)
        sections = dict(re.findall(r"(?ms)^\[([^\]]+)\]\s*\n(.*?)(?=^\[|\Z)", INI))
        self.assertEqual([name for name, body in sections.items() if "-DPGL_GLD1_FAST_NULLING=1" in body],
                         ["env:gld_model_1"])

    def test_final_and_verify_are_critical_decisions(self):
        for marker in ("STABILITY_DECISION_MAX_ATTEMPTS = 3", '"exp_recheck"', '"verify"',
                       '"final"', '"final_bump_verify"', "decisionSampleUsable(verify)",
                       "decisionSampleUsable(after)", "high >= board::GLD_DAC_CODE_MAX"):
            self.assertIn(marker, SERVICE)
        self.assertIn("std::memcmp(&readback, &profile, sizeof(profile)) == 0", SERVICE)

    def test_incomplete_full_profile_never_saved(self):
        save = MAIN.split("bool saveCompleteNullingProfile(", 1)[1].split("void rememberIncompleteNullingResult", 1)[0]
        self.assertIn("result.status != pgl::gld::GldNullingStatus::Ok", save)
        self.assertIn("result.successCount != pgl::gld::board::SENSOR_COUNT", save)
        self.assertLess(save.index("result.successCount !="), save.index("saveNullingProfile(toSave)"))

    def test_single_channel_prechecks_and_failure_invalidates_runtime(self):
        single = MAIN.split("void onRunNullingSingleJson(", 1)[1].split("void onRunFullScaleSweepJson", 1)[0]
        self.assertLess(single.index("loadNullingProfile(existing)"), single.index("runNullingServiceSingleChannel("))
        failed = single.split("if (!result.success)", 1)[1].split("if (existing.profileId == UINT8_MAX)", 1)[0]
        self.assertIn("existing.dacCode[channel]", failed)
        self.assertIn("nullingProfileApplied = false", failed)
        self.assertIn("lastInferenceValid = false", failed)


if __name__ == "__main__":
    unittest.main()
