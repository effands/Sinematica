import unittest
from pathlib import Path


class ExtensionTrpcAuthContextTests(unittest.TestCase):
    def test_media_redirect_runs_inside_authenticated_flow_tab(self):
        source = (Path(__file__).parents[1] / "engine" / "chrome-extension" / "background.js").read_text(
            encoding="utf-8"
        )
        start = source.index("async function handleTrpcRequest")
        end = source.index("async function handleDownloadRequest", start)
        handler = source[start:end]

        self.assertIn("FlowTab.ensureFlowTab", handler)
        self.assertIn("chrome.scripting.executeScript", handler)
        self.assertIn("world: 'MAIN'", handler)
        self.assertIn("credentials: 'include'", handler)
        self.assertIn("redirect: 'follow'", handler)
        self.assertNotIn("requestHeaders.authorization", handler)
        self.assertIn("workerResponse = await fetch", handler)
        self.assertIn("googlevideo\\.com", handler)


if __name__ == "__main__":
    unittest.main()
