import io
import shutil
import sys
import unittest
from pathlib import Path

from PIL import Image
import pillow_heif


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
TMP_ROOT = Path(__file__).resolve().parents[1] / "_tmp"

from project.mobboss_apps.rooms.adapters.outbound.media.filesystem_impl import (  # noqa: E402
    FilesystemRoomItemMediaOutboundPortImpl,
)


class FilesystemRoomItemMediaOutboundPortImplTests(unittest.TestCase):
    def setUp(self) -> None:
        self.media_root = TMP_ROOT / "filesystem_media_adapter"
        if self.media_root.exists():
            shutil.rmtree(self.media_root, ignore_errors=True)
        self.adapter = FilesystemRoomItemMediaOutboundPortImpl(media_root=self.media_root)

    def tearDown(self) -> None:
        if self.media_root.exists():
            shutil.rmtree(self.media_root, ignore_errors=True)

    def test_save_room_item_image_rejects_undecodable_phone_image_bytes(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported image file type"):
            self.adapter.save_room_item_image(
                room_id="r-1",
                classification="knife",
                original_filename="knife.heic",
                chunks=[b"fake-image"],
            )

        self.assertFalse((self.media_root / "rooms").exists())

    def test_save_room_item_image_keeps_supported_extension(self) -> None:
        image_path = self.adapter.save_room_item_image(
            room_id="r-1",
            classification="knife",
            original_filename="knife.png",
            chunks=[_image_bytes("PNG")],
        )

        self.assertTrue(image_path.startswith("/media/rooms/r-1/items/knife-"))
        self.assertTrue(image_path.endswith(".png"))

    def test_save_preset_item_image_converts_bmp_to_jpg(self) -> None:
        image_path = self.adapter.save_preset_item_image(
            user_id="7",
            preset_id=11,
            classification="knife",
            original_filename="knife.bmp",
            chunks=[_image_bytes("BMP")],
        )

        self.assertTrue(image_path.startswith("/media/presets/7/11/items/knife-"))
        self.assertTrue(image_path.endswith(".jpg"))

    def test_save_room_item_image_converts_heic_phone_photo_to_jpg(self) -> None:
        image_path = self.adapter.save_room_item_image(
            room_id="r-1",
            classification="knife",
            original_filename="knife.heic",
            chunks=[_heif_bytes()],
        )

        self.assertTrue(image_path.startswith("/media/rooms/r-1/items/knife-"))
        self.assertTrue(image_path.endswith(".jpg"))

    def test_clone_item_image_to_preset_converts_legacy_bin_source_when_bytes_are_valid(self) -> None:
        room_items_dir = self.media_root / "rooms" / "r-1" / "items"
        room_items_dir.mkdir(parents=True, exist_ok=True)
        (room_items_dir / "knife-legacy.bin").write_bytes(_image_bytes("BMP"))

        image_path = self.adapter.clone_item_image_to_preset(
            user_id="7",
            preset_id=11,
            classification="knife",
            source_image_path="/media/rooms/r-1/items/knife-legacy.bin",
        )

        self.assertTrue(image_path.startswith("/media/presets/7/11/items/knife-"))
        self.assertTrue(image_path.endswith(".jpg"))

    def test_clone_item_image_to_preset_rejects_legacy_bin_source_with_invalid_bytes(self) -> None:
        room_items_dir = self.media_root / "rooms" / "r-1" / "items"
        room_items_dir.mkdir(parents=True, exist_ok=True)
        (room_items_dir / "knife-legacy.bin").write_bytes(b"fake-image")

        with self.assertRaisesRegex(ValueError, "Unsupported image file type"):
            self.adapter.clone_item_image_to_preset(
                user_id="7",
                preset_id=11,
                classification="knife",
                source_image_path="/media/rooms/r-1/items/knife-legacy.bin",
            )


def _image_bytes(format_name: str) -> bytes:
    buffer = io.BytesIO()
    image = Image.new("RGB", (2, 2), color=(200, 50, 25))
    image.save(buffer, format=format_name)
    return buffer.getvalue()


def _heif_bytes() -> bytes:
    image = Image.new("RGB", (2, 2), color=(20, 80, 160))
    heif_file = pillow_heif.from_pillow(image)
    buffer = io.BytesIO()
    heif_file.save(buffer)
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
