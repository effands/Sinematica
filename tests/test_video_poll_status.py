import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from omniflash.generators.i2v import find_failure_reason, is_item_successful


class VideoPollStatusTests(unittest.TestCase):
    def test_nested_flow_failure_is_terminal(self):
        media = {
            "mediaMetadata": {
                "mediaStatus": {
                    "error": {
                        "code": 3,
                        "message": "PUBLIC_ERROR_PROMINENT_PEOPLE_FILTER_FAILED",
                    },
                    "failureReasons": ["PROMINENT_PERSON"],
                    "mediaGenerationStatus": "MEDIA_GENERATION_STATUS_FAILED",
                }
            }
        }

        reason = find_failure_reason(media)

        self.assertIn("PUBLIC_ERROR_PROMINENT_PEOPLE_FILTER_FAILED", reason)
        self.assertIn("tokoh terkenal", reason)
        self.assertFalse(is_item_successful(media))

    def test_nested_flow_success_is_detected(self):
        media = {
            "mediaMetadata": {
                "mediaStatus": {
                    "mediaGenerationStatus": "MEDIA_GENERATION_STATUS_SUCCESSFUL"
                }
            }
        }

        self.assertIsNone(find_failure_reason(media))
        self.assertTrue(is_item_successful(media))


if __name__ == "__main__":
    unittest.main()
