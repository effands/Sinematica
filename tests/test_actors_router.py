import io
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

if "fastapi" not in sys.modules:
    fastapi = types.ModuleType("fastapi")
    class APIRouter:
        def __init__(self, *args, **kwargs): pass
        def get(self, *args, **kwargs): return lambda fn: fn
        def post(self, *args, **kwargs): return lambda fn: fn
        def delete(self, *args, **kwargs): return lambda fn: fn
    class HTTPException(Exception):
        def __init__(self, status_code, detail):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
    fastapi.APIRouter = APIRouter
    fastapi.File = lambda default=None, **kwargs: default
    fastapi.Form = lambda default=None, **kwargs: default
    fastapi.UploadFile = object
    fastapi.HTTPException = HTTPException
    sys.modules["fastapi"] = fastapi
if "dotenv" not in sys.modules:
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv

from backend.routers import actors as actors_router


def upload(name, content=b"image", content_type="image/png"):
    return SimpleNamespace(filename=name, content_type=content_type, file=io.BytesIO(content))


class ActorsRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_actor_persists_multiple_images_with_primary_alias(self):
        saved = []
        with TemporaryDirectory() as temp_dir, patch.object(actors_router, "ACTORS_IMAGE_DIR", Path(temp_dir)), \
                patch.object(actors_router, "_load_actors", return_value=[]), \
                patch.object(actors_router, "_save_actors", side_effect=lambda actors: saved.extend(actors)):
            response = await actors_router.create_actor(
                name="Son Goku", description="Saiyan", seed=123,
                image_files=[upload("front.png"), upload("side.webp", content_type="image/webp")],
                image_file=None,
            )

        actor = response["actor"]
        self.assertEqual(len(actor["images"]), 2)
        self.assertEqual(actor["image_path"], actor["images"][0]["path"])
        self.assertTrue(actor["images"][0]["primary"])
        self.assertEqual(saved[0]["id"], actor["id"])

    async def test_five_images_are_rejected_before_database_save(self):
        with patch.object(actors_router, "_load_actors", return_value=[]), \
                patch.object(actors_router, "_save_actors") as save:
            with self.assertRaises(Exception) as caught:
                await actors_router.create_actor(
                    name="Son Goku", image_files=[upload(f"{i}.png") for i in range(5)], image_file=None
                )
        self.assertEqual(getattr(caught.exception, "status_code", None), 400)
        save.assert_not_called()

    def test_delete_actor_removes_all_owned_files_only(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            owned = [root / "front.png", root / "side.png"]
            other = root / "other.png"
            for path in [*owned, other]:
                path.write_bytes(b"x")
            records = [{
                "id": "goku", "name": "Son Goku", "images": [
                    {"path": str(owned[0]), "url": "/front.png"},
                    {"path": str(owned[1]), "url": "/side.png"},
                ]
            }, {"id": "vegeta", "image_path": str(other), "image_url": "/other.png"}]
            saved = []
            with patch.object(actors_router, "ACTORS_IMAGE_DIR", root), \
                    patch.object(actors_router, "_load_actors", return_value=records), \
                    patch.object(actors_router, "_save_actors", side_effect=lambda value: saved.extend(value)):
                actors_router.delete_actor("goku")

            self.assertFalse(any(path.exists() for path in owned))
            self.assertTrue(other.exists())
            self.assertEqual([a["id"] for a in saved], ["vegeta"])


if __name__ == "__main__":
    unittest.main()
