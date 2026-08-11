from PIL import Image, ImageDraw

from src.character.sprite_loader import SpriteLoader


def _make_image(path, size, rects, fill=(200, 100, 50, 255)):
    """Draws one or more opaque rectangles on an otherwise fully transparent
    canvas — a controlled stand-in for a real (messy) sprite sheet, so the
    crop-detection logic can be verified deterministically."""
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for rect in rects:
        draw.rectangle(rect, fill=fill)
    img.save(path)


class TestSpriteLoaderMissingAndCaching:
    def test_missing_file_returns_none(self, tmp_path):
        loader = SpriteLoader(str(tmp_path))
        assert loader.load_sprite("nonexistent") is None

    def test_caches_loaded_sprite(self, tmp_path):
        _make_image(tmp_path / "idle.png", (100, 100), [(20, 10, 80, 70)])
        loader = SpriteLoader(str(tmp_path))

        first = loader.load_sprite("idle")
        second = loader.load_sprite("idle")

        assert first is second

    def test_fully_transparent_image_does_not_crash(self, tmp_path):
        Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(tmp_path / "empty.png")
        loader = SpriteLoader(str(tmp_path))

        pixmap = loader.load_sprite("empty")

        assert pixmap is not None


class TestSpriteLoaderSinglePose:
    def test_crops_tightly_around_a_single_clean_pose(self, tmp_path):
        _make_image(tmp_path / "idle.png", (100, 100), [(20, 10, 80, 70)])
        loader = SpriteLoader(str(tmp_path))

        pixmap = loader.load_sprite("idle")

        assert pixmap.width() == 61   # columns 20..80 inclusive
        assert pixmap.height() == 71  # rows 0..70 (only the bottom edge is trimmed)


class TestSpriteLoaderCaptionExclusion:
    def test_excludes_content_below_a_real_transparency_gap(self, tmp_path):
        """Regression test: this asset pack bakes a Portuguese caption + folder
        icon under some sprites, separated from the character by a transparent
        gap. That caption used to get sliced into the displayed frame."""
        character = (20, 10, 80, 40)
        caption = (5, 51, 95, 70)  # wider than the character — must NOT leak in
        _make_image(tmp_path / "sleep.png", (100, 100), [character, caption])
        loader = SpriteLoader(str(tmp_path))

        pixmap = loader.load_sprite("sleep")

        assert pixmap.height() == 41   # rows 0..40 only, gap+caption excluded
        assert pixmap.width() == 61    # the character's width, NOT the wider caption's


class TestSpriteLoaderMultiplePoses:
    def test_picks_the_widest_column_run_as_the_representative_pose(self, tmp_path):
        narrow_pose = (10, 10, 39, 60)   # width 30
        wide_pose = (80, 10, 149, 60)    # width 70
        _make_image(tmp_path / "game.png", (200, 100), [narrow_pose, wide_pose])
        loader = SpriteLoader(str(tmp_path))

        pixmap = loader.load_sprite("game")

        assert pixmap.width() == 70
