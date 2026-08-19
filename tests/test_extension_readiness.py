import unittest

from engine.omniflash.bridge import ExtensionBridge


class _OpenWebSocket:
    closed = False


class ExtensionReadinessTests(unittest.TestCase):
    def test_connected_profile_without_flow_tab_is_not_routable(self):
        bridge = ExtensionBridge()
        ws = _OpenWebSocket()
        bridge.register_instance(
            "profile-1",
            ws,
            "Chrome Profile",
            project_id="project-1",
            ready=False,
            readiness_error="NO_FLOW_WINDOW",
        )
        bridge.record_instance_token("profile-1", "bearer-token")

        snapshot = bridge.instance_snapshot()[0]

        self.assertFalse(snapshot["ready"])
        self.assertEqual(snapshot["readiness_error"], "NO_FLOW_WINDOW")
        self.assertEqual(bridge._get_target_ws_with_entry("profile-1"), (None, None))

    def test_profile_with_valid_flow_tab_token_and_project_is_routable(self):
        bridge = ExtensionBridge()
        ws = _OpenWebSocket()
        bridge.register_instance(
            "profile-1",
            ws,
            "Chrome Profile",
            project_id="project-1",
            ready=True,
        )
        bridge.record_instance_token("profile-1", "bearer-token")

        selected_ws, selected = bridge._get_target_ws_with_entry("profile-1")

        self.assertIs(selected_ws, ws)
        self.assertEqual(selected["instance_id"], "profile-1")

    def test_profile_transition_to_ready_sets_backend_readiness_event(self):
        bridge = ExtensionBridge()
        ws = _OpenWebSocket()
        bridge.register_instance("profile-1", ws, ready=False)
        bridge.record_instance_token("profile-1", "bearer-token")
        self.assertFalse(bridge._connected.is_set())

        bridge.register_instance("profile-1", ws, project_id="project-1", ready=True)

        self.assertTrue(bridge._connected.is_set())


if __name__ == "__main__":
    unittest.main()
