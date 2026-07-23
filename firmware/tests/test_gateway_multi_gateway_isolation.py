"""Focused source/contract guards for shared-topic multi-Gateway isolation."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
GATEWAY_SOURCE = ROOT / "firmware/gateway/src/GatewayMqttMeshMain.cpp"


def accepts_target(value: object, local_gateway_id: int) -> bool:
    """Model the firmware's required exact 0x0001..0x000F target rule."""
    if isinstance(value, str):
        if not re.fullmatch(r"(?:0[xX][0-9a-fA-F]+)|(?:[0-9]+)", value):
            return False
        parsed = int(value, 16 if value.lower().startswith("0x") else 10)
    elif isinstance(value, int) and not isinstance(value, bool):
        parsed = value
    else:
        return False
    return 0x0001 <= parsed <= 0x000F and parsed == local_gateway_id


class GatewayMultiGatewayIsolationTest(unittest.TestCase):
    def test_target_range_and_exact_match(self) -> None:
        self.assertTrue(accepts_target("0x0001", 0x0001))
        self.assertTrue(accepts_target(15, 0x000F))
        self.assertFalse(accepts_target(None, 0x0001))
        self.assertFalse(accepts_target("0x0001junk", 0x0001))
        self.assertFalse(accepts_target(0, 0x0001))
        self.assertFalse(accepts_target(0x0010, 0x0001))
        self.assertFalse(accepts_target(0x0002, 0x0001))

    def test_mqtt_commands_fail_closed_before_build(self) -> None:
        source = GATEWAY_SOURCE.read_text(encoding="utf-8")
        callback = source[source.index("void mqttCallback(char* topic") : source.index("bool publishTopologyReport")]
        self.assertIn('doc["targetGatewayId"]', source)
        self.assertIn('doc["gatewayId"]', source)
        self.assertIn("missing-gateway-target", source)
        self.assertIn("gateway-target-mismatch", source)
        self.assertRegex(
            callback,
            r'(?s)if \(strcmp\(topic, TOPIC_PULL\).*?commandTargetsThisGateway\(doc, topic\).*?handlePullCommand\(doc\)',
        )
        self.assertRegex(
            callback,
            r'(?s)else if \(strcmp\(topic, TOPIC_NODE_COMMAND\).*?commandTargetsThisGateway\(doc, topic\).*?handleNodeCommand\(doc\)',
        )

    def test_other_gateway_destination_drops_before_publish(self) -> None:
        source = GATEWAY_SOURCE.read_text(encoding="utf-8")
        receive = source[source.index("void receiveMeshOnce()") : source.index("void printBootHeader")]
        guard = receive.index("isProvisionableGatewayId(addressedFrame.dstId)")
        drop = receive.index("GW_MESH_RX_DROP")
        publish = receive.index("publishMeshFrame")
        self.assertLess(guard, drop)
        self.assertLess(drop, publish)
        self.assertIn("addressedFrame.dstId != gatewayId", receive)

    def test_runtime_gateway_identity_is_nvs_backed_and_role_bounded(self) -> None:
        source = GATEWAY_SOURCE.read_text(encoding="utf-8")
        self.assertIn("uint16_t gatewayId = DEFAULT_GATEWAY_ID;", source)
        self.assertIn('GATEWAY_ID_CONFIG_NAMESPACE = "gw-cfg"', source)
        self.assertIn("loadGatewayIdentity();", source)
        self.assertIn("saveGatewayIdentity(requestedGatewayId)", source)
        self.assertIn("SET_GATEWAY_ADDRESS_JSON", source)
        self.assertIn("GET_GATEWAY_ADDRESS", source)
        self.assertIn("isProvisionableGatewayId", source)
        self.assertNotRegex(
            source.replace("pgl::config::gw::GATEWAY_ID", ""),
            r"\bGATEWAY_ID\b",
        )


if __name__ == "__main__":
    unittest.main()
