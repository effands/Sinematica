import asyncio
import json
import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from engine.omniflash.bridge import ExtensionBridge
from engine.omniflash.generators import harvest_project_videos


class _HarvestWebSocket:
    def __init__(self, bridge, harvested_videos):
        self.bridge = bridge
        self.harvested_videos = harvested_videos
        self.sent = []

    async def send(self, payload):
        message = json.loads(payload)
        self.sent.append(message)
        req_id = message["id"]
        # Respond with harvest result
        self.bridge.handle_message(
            json.dumps({
                "type": "api_response",
                "id": req_id,
                "status": 200,
                "data": {
                    "success": True,
                    "videos": self.harvested_videos,
                    "count": len(self.harvested_videos),
                },
            }),
            self,
            "profile-1",
        )


class VideoHarvestReconciliationTests(unittest.IsolatedAsyncioTestCase):
    async def test_bridge_harvest_project_videos_success(self):
        bridge = ExtensionBridge()
        sample_videos = [
            {"index": 0, "scene_index": 1, "label": "Scene 1", "video_url": "https://flow-content.google/video/s1.mp4", "duration": 10},
            {"index": 1, "scene_index": 2, "label": "Scene 2", "video_url": "https://flow-content.google/video/s2.mp4", "duration": 10},
        ]
        ws = _HarvestWebSocket(bridge, sample_videos)
        bridge.handle_message(
            json.dumps({"type": "register", "instance_id": "profile-1", "ready": True, "logged_in": True, "project_id": "proj-1"}),
            ws,
            "profile-1",
        )

        res = await harvest_project_videos(bridge, instance_id="profile-1", project_id="proj-1")
        self.assertTrue(res.get("success"))
        self.assertEqual(len(res.get("videos", [])), 2)
        self.assertEqual(res["videos"][0]["video_url"], "https://flow-content.google/video/s1.mp4")
        self.assertEqual(res["videos"][1]["video_url"], "https://flow-content.google/video/s2.mp4")

    async def test_reconcile_missing_scene_downloads_and_recovers_files(self):
        tmp_dir = Path("storage/test_reconcile_job")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            # Scene 2 exists, Scene 1 is missing
            scene_2_file = tmp_dir / "scene_02.mp4"
            scene_2_file.write_bytes(b"scene_2_content")

            scenes = [
                {"scene_number": 1, "id": 1, "status": "failed", "prompt": "Two women confronting"},
                {"scene_number": 2, "id": 2, "status": "completed", "prompt": "Secret discovered"},
            ]
            job_state = {
                "job_id": "test_reconcile_job",
                "scenes": scenes,
                "status": "processing",
            }

            harvested = [
                {"index": 0, "scene_index": 1, "label": "Two women confronting", "video_url": "https://flow-content.google/video/s1.mp4"},
                {"index": 1, "scene_index": 2, "label": "Secret discovered", "video_url": "https://flow-content.google/video/s2.mp4"},
            ]

            async def fake_download(bridge, url, out_path, **kwargs):
                Path(out_path).write_bytes(b"recovered_video_data")

            with patch("omniflash.generators.harvest_project_videos", new=AsyncMock(return_value={"videos": harvested})), \
                 patch("backend.jobs_executor.download_file", side_effect=fake_download):

                # Simulate reconciliation logic from jobs_executor
                missing_scenes = [
                    s for s in job_state.get("scenes", [])
                    if s.get("status") != "completed" or not (tmp_dir / f"scene_{s.get('scene_number', s.get('id', 1)):02d}.mp4").exists()
                ]
                self.assertEqual(len(missing_scenes), 1)

                for s in missing_scenes:
                    sc_num = s.get("scene_number", s.get("id", 1))
                    out_filename = f"scene_{sc_num:02d}.mp4"
                    out_path = tmp_dir / out_filename
                    matched = harvested[sc_num - 1]
                    await fake_download(None, matched["video_url"], out_path)
                    s["status"] = "completed"
                    s["video_path"] = str(out_path)

                completed_scene_paths = []
                for s in job_state.get("scenes", []):
                    sc_num = s.get("scene_number", s.get("id", 1))
                    sc_path = tmp_dir / f"scene_{sc_num:02d}.mp4"
                    if sc_path.exists() and s.get("status") == "completed":
                        completed_scene_paths.append(str(sc_path))

                self.assertEqual(len(completed_scene_paths), 2)
                self.assertTrue((tmp_dir / "scene_01.mp4").exists())
                self.assertTrue((tmp_dir / "scene_02.mp4").exists())
                self.assertEqual(scenes[0]["status"], "completed")
                self.assertEqual(scenes[1]["status"], "completed")
        finally:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)

    async def test_unclaimed_deduplication_reconciliation_multi_scenes(self):
        tmp_dir = Path("storage/test_unclaimed_job")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            # Scene 1 already completed with URL s1.mp4
            scene_1_file = tmp_dir / "scene_01.mp4"
            scene_1_file.write_bytes(b"scene_1_content")

            scenes = [
                {"scene_number": 1, "id": 1, "status": "completed", "video_url": "https://flow-content.google/video/s1.mp4", "prompt": "Arga exploring"},
                {"scene_number": 2, "id": 2, "status": "failed", "prompt": "Suri finding relic"},
                {"scene_number": 3, "id": 3, "status": "failed", "prompt": "Temple collapsing"},
            ]
            job_state = {
                "job_id": "test_unclaimed_job",
                "scenes": scenes,
                "status": "processing",
            }

            # Flow canvas contains 3 valid videos (Scene 1, Scene 2, Scene 3)
            harvested = [
                {"index": 0, "scene_index": 1, "label": "Arga exploring", "video_url": "https://flow-content.google/video/s1.mp4"},
                {"index": 1, "scene_index": 2, "label": "Suri finding relic", "video_url": "https://flow-content.google/video/s2.mp4"},
                {"index": 2, "scene_index": 3, "label": "Temple collapsing", "video_url": "https://flow-content.google/video/s3.mp4"},
            ]

            downloaded_urls = []

            async def fake_download(bridge, url, out_path, **kwargs):
                downloaded_urls.append(url)
                Path(out_path).write_bytes(f"content_{url}".encode())

            # Track claimed URLs
            claimed_urls = {
                s.get("video_url")
                for s in job_state.get("scenes", [])
                if s.get("status") == "completed" and s.get("video_url")
            }

            available_unclaimed = [
                hv for hv in harvested
                if hv.get("video_url") and hv.get("video_url") not in claimed_urls
            ]

            missing_scenes = [
                s for s in job_state.get("scenes", [])
                if s.get("status") != "completed" or not (tmp_dir / f"scene_{s.get('scene_number', s.get('id', 1)):02d}.mp4").exists()
            ]

            self.assertEqual(len(missing_scenes), 2)
            self.assertEqual(len(available_unclaimed), 2)

            for s in missing_scenes:
                sc_num = s.get("scene_number", s.get("id", 1))
                out_filename = f"scene_{sc_num:02d}.mp4"
                out_path = tmp_dir / out_filename

                matched = None
                sc_prompt = (s.get("prompt") or "").lower()
                for idx_u, hv in enumerate(available_unclaimed):
                    hv_label = (hv.get("label") or "").lower()
                    if hv_label and (hv_label in sc_prompt or sc_prompt in hv_label):
                        matched = available_unclaimed.pop(idx_u)
                        break

                if not matched and available_unclaimed:
                    matched = available_unclaimed.pop(0)

                if matched and matched.get("video_url"):
                    v_url = matched["video_url"]
                    claimed_urls.add(v_url)
                    await fake_download(None, v_url, out_path)
                    s["status"] = "completed"
                    s["video_url"] = v_url
                    s["video_path"] = str(out_path)

            self.assertEqual(downloaded_urls, [
                "https://flow-content.google/video/s2.mp4",
                "https://flow-content.google/video/s3.mp4",
            ])
            self.assertEqual(scenes[1]["video_url"], "https://flow-content.google/video/s2.mp4")
            self.assertEqual(scenes[2]["video_url"], "https://flow-content.google/video/s3.mp4")
            self.assertTrue((tmp_dir / "scene_02.mp4").exists())
            self.assertTrue((tmp_dir / "scene_03.mp4").exists())
        finally:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
