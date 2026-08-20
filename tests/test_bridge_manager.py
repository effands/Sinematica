import unittest
from unittest.mock import patch

from backend import bridge_manager


class _ReconnectingBridge:
    active_instance_id = None

    def __init__(self, snapshots):
        self.snapshots = list(snapshots)

    def instance_snapshot(self):
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]


class EnsureReadyTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_until_profile_is_connected_logged_in_and_ready(self):
        bridge = _ReconnectingBridge([
            [],
            [{"logged_in": False, "ready": True}],
            [{"logged_in": True, "ready": True}],
        ])

        with patch.object(bridge_manager, "_bridge", bridge):
            await bridge_manager.ensure_ready(timeout=0.1, poll_interval=0)

    async def test_rejects_connected_profile_that_never_logs_in(self):
        bridge = _ReconnectingBridge([[{"logged_in": False, "ready": True}]])

        with patch.object(bridge_manager, "_bridge", bridge):
            with self.assertRaisesRegex(RuntimeError, "terhubung atau ter-login"):
                await bridge_manager.ensure_ready(timeout=0.01, poll_interval=0.001)


if __name__ == "__main__":
    unittest.main()
