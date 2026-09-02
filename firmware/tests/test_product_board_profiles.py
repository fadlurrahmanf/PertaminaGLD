from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FIRMWARE = REPO_ROOT / "firmware"


def assert_pin_map(test: unittest.TestCase, relative: str, expected: dict[str, int]) -> None:
    source = (FIRMWARE / relative).read_text(encoding="utf-8")
    for name, value in expected.items():
        with test.subTest(file=relative, signal=name):
            test.assertRegex(source, rf"\b{name}\s*=\s*{value}\s*;")


class ProductBoardProfileTests(unittest.TestCase):
    def test_circle_pin_maps_match_e220_ver4_archive_audit(self) -> None:
        expected = {
            "PIN_SPI_SCK": 12, "PIN_SPI_MOSI": 11, "PIN_SPI_MISO": 13,
            "PIN_RADIO_A_TXEN": 5, "PIN_RADIO_A_RXEN": 6,
            "PIN_RADIO_A_RST": 7, "PIN_RADIO_A_DIO1": 15,
            "PIN_RADIO_A_CS": 16, "PIN_RADIO_A_BUSY": 17,
            "PIN_RADIO_B_RXEN": 39, "PIN_RADIO_B_TXEN": 40,
            "PIN_RADIO_B_BUSY": 41, "PIN_RADIO_B_CS": 42,
            "PIN_RADIO_B_RST": 1, "PIN_RADIO_B_DIO1": 2,
        }
        assert_pin_map(self, "ch/include/ChBoardPinsCircle.h", expected)
        gateway_expected = {
            key.replace("PIN_RADIO_A_", "PIN_RADIO_UNUSED_A_"): value
            for key, value in expected.items()
            if key not in {"PIN_RADIO_A_DIO1", "PIN_RADIO_A_BUSY"}
        }
        gateway_expected.update({key: value for key, value in expected.items() if "RADIO_B" in key or "SPI" in key})
        gateway_expected["PIN_STATUS_LED"] = 19
        assert_pin_map(self, "gateway/include/GatewayBoardPinsCircle.h", gateway_expected)

    def test_rectangle_pin_maps_match_e220_ver5_archive_audit(self) -> None:
        expected = {
            "PIN_SPI_SCK": 12, "PIN_SPI_MOSI": 11, "PIN_SPI_MISO": 13,
            "PIN_RADIO_A_TXEN": 5, "PIN_RADIO_A_RXEN": 6,
            "PIN_RADIO_A_CS": 7, "PIN_RADIO_A_BUSY": 15,
            "PIN_RADIO_A_RST": 16, "PIN_RADIO_A_DIO1": 17,
            "PIN_RADIO_B_CS": 39, "PIN_RADIO_B_BUSY": 40,
            "PIN_RADIO_B_DIO1": 41, "PIN_RADIO_B_RXEN": 42,
            "PIN_RADIO_B_TXEN": 2, "PIN_RADIO_B_RST": 1,
        }
        assert_pin_map(self, "ch/include/ChBoardPinsRectangle.h", expected)
        gateway_expected = {
            key.replace("PIN_RADIO_A_", "PIN_RADIO_UNUSED_A_"): value
            for key, value in expected.items()
            if key not in {"PIN_RADIO_A_DIO1", "PIN_RADIO_A_BUSY"}
        }
        gateway_expected.update({key: value for key, value in expected.items() if "RADIO_B" in key or "SPI" in key})
        gateway_expected["PIN_STATUS_LED"] = 20
        assert_pin_map(self, "gateway/include/GatewayBoardPinsRectangle.h", gateway_expected)

    def test_six_product_environments_are_explicit(self) -> None:
        source = (FIRMWARE / "platformio.ini").read_text(encoding="utf-8")
        for environment in (
            "ch_small", "ch_large", "gw_small", "gw_large", "gw_small_tls", "gw_large_tls",
        ):
            self.assertIn(f"[env:{environment}]", source)
        self.assertIn("-DPGL_CH_BOARD_RECTANGLE=1", source)
        self.assertIn("-DPGL_CH_BOARD_CIRCLE=1", source)
        self.assertIn("-DPGL_GW_BOARD_RECTANGLE=1", source)
        self.assertIn("-DPGL_GW_BOARD_CIRCLE=1", source)
        self.assertEqual(source.count("-DPGL_GW_MQTT_TLS=1"), 2)

    def test_lora_band_is_clamped_to_920_923(self) -> None:
        ch = (FIRMWARE / "ch/src/ChStarMeshRuntimeMain.cpp").read_text(encoding="utf-8")
        gw = (FIRMWARE / "gateway/src/GatewayMqttMeshMain.cpp").read_text(encoding="utf-8")
        for source in (ch, gw):
            self.assertIn(">= 920.0", source)
            self.assertIn("<= 923.0", source)
            self.assertNotIn("out-of-range-900-930", source)

    def test_tls_is_ca_verified_and_status_uses_json_booleans(self) -> None:
        source = (FIRMWARE / "gateway/src/GatewayMqttMeshMain.cpp").read_text(encoding="utf-8")
        self.assertIn("wifiClient.setCACert(netConfig.tlsCaPem)", source)
        self.assertNotIn("wifiClient.setInsecure(", source)
        self.assertIn("GW_TLS_WAIT trustedTime=0 mqttBlocked=1", source)
        self.assertIn('"tlsCapable\\\":%s', source)
        self.assertIn('tlsCapable() ? "true" : "false"', source)

    def test_gateway_network_config_is_verified_after_nvs_write(self) -> None:
        source = (FIRMWARE / "gateway/src/GatewayMqttMeshMain.cpp").read_text(encoding="utf-8")
        save_start = source.index("bool saveNetConfig(const RuntimeNetConfig& candidate)")
        save_end = source.index("struct RuntimeMeshConfig", save_start)
        save = source[save_start:save_end]
        journal_start = source.index("constexpr const char* NET_CONFIG_SLOT_NAMESPACES")
        journal = source[journal_start:save_end]
        self.assertIn('{"gwnet0", "gwnet1"}', journal)
        self.assertIn("NET_CONFIG_SELECTOR_PREFIX", journal)
        self.assertIn("const bool cleared = prefs.clear();", journal)
        self.assertIn("return cleared && netConfigSlotIsEmpty(slot);", journal)
        self.assertIn('prefs.putUInt("generation", generation)', journal)
        self.assertIn('prefs.putUInt("magic", NET_CONFIG_MAGIC)', journal)
        for key in ("ssid", "pass", "host", "port", "user", "mqttPass", "mqttOn"):
            self.assertIn(f'prefs.isKey("{key}")', journal)
        self.assertIn('prefs.putBool("tlsReady", candidate.tlsReady)', journal)
        self.assertIn("candidate.wifiSsid", journal)
        self.assertIn("writeInactiveNetConfigSlotAndVerify(targetSlot, candidate, nextGeneration)", save)
        inactive_write = save.index("writeInactiveNetConfigSlotAndVerify(targetSlot, candidate, nextGeneration)")
        selector_commit = save.index("writeActiveNetConfigSelectionAndVerify(targetSlot, nextGeneration)")
        self.assertLess(inactive_write, selector_commit)
        self.assertIn("const bool candidateInvalidated = clearNetConfigSlotAndVerify(targetSlot);", save)
        self.assertIn("currentGeneration", save)
        self.assertIn("NET_CONFIG_LEGACY_NAMESPACE", journal)
        self.assertIn("return true;", save)

    def test_gateway_dual_slot_fault_model_preserves_last_committed_config(self) -> None:
        old = {"generation": 7, "value": "old", "valid": True}
        partial = {"generation": 8, "value": "partial", "valid": False}
        candidate = {"generation": 8, "value": "new", "valid": True}

        def boot(selector: tuple[int, int] | None, slots: list[dict[str, object]]) -> str:
            if selector is not None:
                slot, generation = selector
                selected = slots[slot]
                if selected["valid"] and selected["generation"] == generation:
                    return str(selected["value"])
                other = slots[slot ^ 1]
                if other["valid"]:
                    return str(other["value"])
            valid = [record for record in slots if record["valid"]]
            if len(valid) >= 2:
                # Missing/corrupt selector must not promote a newer,
                # uncommitted candidate.
                return str(min(valid, key=lambda item: int(item["generation"]))["value"])
            return "legacy"

        # Every failure or power loss before the selector commit retains the
        # old selector. A partial or even fully written inactive slot is inert.
        self.assertEqual(boot((0, 7), [old, partial]), "old")
        self.assertEqual(boot((0, 7), [old, candidate]), "old")
        # If selector readback/repair itself is corrupt, the older committed
        # generation wins instead of the uncommitted higher generation.
        self.assertEqual(boot(None, [old, candidate]), "old")
        # A lone valid slot with no selector may be a first-save candidate
        # written immediately before power loss; durable legacy/default wins.
        self.assertEqual(boot(None, [candidate, partial]), "legacy")
        # Only the final generation-bound selector switch makes new durable.
        self.assertEqual(boot((1, 8), [old, candidate]), "new")

    def test_gateway_journal_has_bounded_nvs_budget_and_safe_legacy_cleanup(self) -> None:
        source = (FIRMWARE / "gateway/src/GatewayMqttMeshMain.cpp").read_text(encoding="utf-8")
        self.assertIn("board_build.partitions = default_16MB.csv",
                      (FIRMWARE / "platformio.ini").read_text(encoding="utf-8"))

        # Arduino-ESP32 default_16MB.csv assigns 0x5000 bytes to NVS. ESP-IDF
        # NVS uses 32-byte entries, 126 entries/page, and reserves one page for
        # garbage collection. Variable strings consume one index entry plus
        # ceil((payload + NUL) / 32) data entries.
        nvs_partition_bytes = 0x5000
        page_bytes = 0x1000
        entries_per_page = 126
        usable_entries = (nvs_partition_bytes // page_bytes - 1) * entries_per_page

        def string_entries(max_bytes: int) -> int:
            return 1 + (max_bytes + 1 + 31) // 32

        string_limits = (32, 64, 64, 32, 64, 3900, 64)
        slot_entries = 1 + sum(string_entries(limit) for limit in string_limits) + 5
        selector_entries = 2  # control namespace + one uint64 active selector
        other_namespace_reserve_entries = page_bytes // 32
        self.assertLessEqual(
            2 * slot_entries + selector_entries + other_namespace_reserve_entries,
            usable_entries,
        )

        save_start = source.index("bool saveNetConfig(const RuntimeNetConfig& candidate)")
        save_end = source.index("struct RuntimeMeshConfig", save_start)
        save = source[save_start:save_end]
        commit = save.index("if (writeActiveNetConfigSelectionAndVerify(targetSlot, nextGeneration))")
        cleanup_after_commit = save.index("clearLegacyNetConfigRecordAndVerify();", commit)
        self.assertLess(commit, cleanup_after_commit)
        self.assertIn("cleanup.clear()", source)
        writer_start = source.index("bool writeInactiveNetConfigSlotAndVerify(")
        writer_end = source.index("void loadNetConfig()", writer_start)
        writer = source[writer_start:writer_end]
        self.assertLess(
            writer.index("clearNetConfigSlotAndVerify(slot)"),
            writer.index('prefs.putString("tlsCaPem", candidate.tlsCaPem)'),
        )
        self.assertGreaterEqual(writer.count("clearNetConfigSlotAndVerify(slot)"), 3)
        self.assertIn("clearLegacyNetConfigRecordAndVerify();\n        return;", source)
        load_start = source.index("void loadNetConfig()")
        load_end = source.index("bool saveNetConfig(", load_start)
        load = source[load_start:load_end]
        legacy_first = load.index("if (!selected.valid &&")
        slot_fallback = load.index("uint32_t generation0 = 0;")
        self.assertLess(legacy_first, slot_fallback)

    def test_gateway_journal_schema_is_uniform_across_tls_variants(self) -> None:
        source = (FIRMWARE / "gateway/src/GatewayMqttMeshMain.cpp").read_text(encoding="utf-8")
        struct_start = source.index("struct RuntimeNetConfig")
        struct_end = source.index("};", struct_start)
        runtime_struct = source[struct_start:struct_end]
        self.assertIn("tlsCaPem[TLS_CA_PEM_MAX_BYTES + 1]", runtime_struct)
        self.assertIn("ntpHost[NTP_HOST_MAX_BYTES + 1]", runtime_struct)
        self.assertNotIn("#if defined(PGL_GW_MQTT_TLS)", runtime_struct)

        write_start = source.index("bool writeInactiveNetConfigSlotAndVerify(")
        write_end = source.index("void loadNetConfig()", write_start)
        slot_writer = source[write_start:write_end]
        self.assertIn('prefs.putString("tlsCaPem", candidate.tlsCaPem)', slot_writer)
        self.assertIn('prefs.putString("ntpHost", candidate.ntpHost)', slot_writer)
        self.assertIn('prefs.putBool("tlsReady", candidate.tlsReady)', slot_writer)
        self.assertNotIn("#if defined(PGL_GW_MQTT_TLS)", slot_writer)
        self.assertIn("stagedNetConfig.tlsReady = false;", source)
        self.assertIn("stagedNetConfig.tlsReady = true;", source)
        self.assertIn("return netConfig.tlsReady &&", source)
        self.assertIn(
            '!netConfig.tlsReady &&\n        (!doc.containsKey("tlsCaPem") || !doc.containsKey("ntpHost"))',
            source,
        )
        self.assertIn("tls_fields_required_after_transport_change", source)

    def test_gateway_network_config_commits_live_state_only_after_verified_save(self) -> None:
        source = (FIRMWARE / "gateway/src/GatewayMqttMeshMain.cpp").read_text(encoding="utf-8")
        wifi_start = source.index("void handleSetWifiConfigJson(")
        mqtt_start = source.index("void handleSetMqttConfigJson(")
        mesh_start = source.index("void handleSetMeshLoraJson(")
        wifi = source[wifi_start:source.index("void handleTestWifi(", wifi_start)]
        mqtt = source[mqtt_start:mesh_start]
        for handler in (wifi, mqtt):
            with self.subTest(handler="wifi" if handler is wifi else "mqtt"):
                stage = handler.index("stagedNetConfig = netConfig;")
                saved = handler.index("saveNetConfig(stagedNetConfig)")
                committed = handler.index("netConfig = stagedNetConfig;")
                self.assertLess(stage, saved)
                self.assertLess(saved, committed)
                self.assertNotIn("copyBounded(netConfig.", handler)

    def test_gateway_rejects_overlength_utf8_fields_before_staging(self) -> None:
        source = (FIRMWARE / "gateway/src/GatewayMqttMeshMain.cpp").read_text(encoding="utf-8")
        expected_limits = {
            "WIFI_SSID_MAX_BYTES": 32,
            "WIFI_PASSWORD_MAX_BYTES": 64,
            "MQTT_HOST_MAX_BYTES": 64,
            "MQTT_USER_MAX_BYTES": 32,
            "MQTT_PASSWORD_MAX_BYTES": 64,
            "NTP_HOST_MAX_BYTES": 64,
        }
        for name, value in expected_limits.items():
            self.assertIn(f"constexpr size_t {name} = {value};", source)

        wifi_start = source.index("void handleSetWifiConfigJson(")
        mqtt_start = source.index("void handleSetMqttConfigJson(")
        mesh_start = source.index("void handleSetMeshLoraJson(")
        wifi = source[wifi_start:source.index("void handleTestWifi(", wifi_start)]
        mqtt = source[mqtt_start:mesh_start]
        wifi_stage = wifi.index("stagedNetConfig = netConfig;")
        for guard in (
            "ssidBytes > WIFI_SSID_MAX_BYTES",
            "passwordBytes > WIFI_PASSWORD_MAX_BYTES",
            "strlen(mqttHost) > MQTT_HOST_MAX_BYTES",
            "strlen(mqttUser) > MQTT_USER_MAX_BYTES",
            "strlen(mqttPassword) > MQTT_PASSWORD_MAX_BYTES",
        ):
            self.assertLess(wifi.index(guard), wifi_stage)
        mqtt_stage = mqtt.index("stagedNetConfig = netConfig;")
        for guard in (
            "strlen(host) > MQTT_HOST_MAX_BYTES",
            "strlen(username) > MQTT_USER_MAX_BYTES",
            "strlen(password) > MQTT_PASSWORD_MAX_BYTES",
            "strlen(ntpHost) > NTP_HOST_MAX_BYTES",
        ):
            self.assertLess(mqtt.index(guard), mqtt_stage)

    def test_gateway_status_log_buffer_has_json_readback_headroom(self) -> None:
        source = (FIRMWARE / "gateway/src/GatewayMqttMeshMain.cpp").read_text(encoding="utf-8")
        self.assertIn("char buffer[512];", source)
        self.assertIn("GW_STATUS_JSON", source)


if __name__ == "__main__":
    unittest.main()
