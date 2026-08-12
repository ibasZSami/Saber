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
        assert pixmap.height() == 61  # rows 10..70 inclusive — tight on all sides now


class TestSpriteLoaderCaptionExclusion:
    def test_excludes_content_below_a_real_transparency_gap(self, tmp_path):
        """Regression test: one asset pack bakes a Portuguese caption + folder
        icon under some sprites, separated from the character by a gap. The
        caption is also *wider* than the character, so picking by width alone
        would grab it — picking by connected-component area must not."""
        character = (20, 10, 80, 40)   # area 61*31 = 1891
        caption = (5, 51, 95, 70)      # area 91*20 = 1820 — wider, but smaller overall
        _make_image(tmp_path / "sleep.png", (100, 100), [character, caption])
        loader = SpriteLoader(str(tmp_path))

        pixmap = loader.load_sprite("sleep")

        assert pixmap.width() == 61   # the character's width, not the wider caption's
        assert pixmap.height() == 31  # tight crop, caption fully excluded


class TestSpriteLoaderBleedExclusion:
    def test_excludes_small_disconnected_fragment(self, tmp_path):
        """Regression test: another asset pack has a sliver of the neighboring
        sprite bleeding in at the top edge (leftover from being cut out of a
        larger sheet). The main character is always the biggest blob."""
        bleed_fragment = (0, 0, 15, 8)     # tiny, disconnected, near a corner
        character = (20, 20, 90, 95)       # much larger
        _make_image(tmp_path / "thinking.png", (100, 100), [bleed_fragment, character])
        loader = SpriteLoader(str(tmp_path))

        pixmap = loader.load_sprite("thinking")

        assert pixmap.width() == 71   # 20..90 inclusive — bleed fragment excluded
        assert pixmap.height() == 76  # 20..95 inclusive


class TestSpriteLoaderMultiplePoses:
    def test_picks_the_largest_pose_by_area(self, tmp_path):
        narrow_pose = (10, 10, 39, 60)   # width 30, area 30*51=1530
        wide_pose = (80, 10, 149, 60)    # width 70, area 70*51=3570
        _make_image(tmp_path / "game.png", (200, 100), [narrow_pose, wide_pose])
        loader = SpriteLoader(str(tmp_path))

        pixmap = loader.load_sprite("game")

        assert pixmap.width() == 70
        assert pixmap.height() == 51
