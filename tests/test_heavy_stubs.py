"""Picture/clip decoding with the real OpenCV, the depth map and local music with stand-ins for the big model libraries."""
import subprocess
import sys
import types

import pytest

cv2 = pytest.importorskip("cv2")
imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
np = pytest.importorskip("numpy")

import local_audio as la  # noqa: E402
from studio_app import gallery  # noqa: E402


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    p = tmp_path_factory.mktemp("clip") / "c.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=96x64:r=12:d=1", "-pix_fmt", "yuv420p", str(p)], check=True)
    return p


@pytest.fixture()
def picture(tmp_path):
    from PIL import Image
    p = tmp_path / "p.png"
    Image.new("RGB", (300, 200), "blue").save(p)
    return p


class TestLoadRgb:
    def test_picture_and_clip(self, picture, clip):
        assert gallery.load_rgb(picture).size == (300, 200) and gallery.load_rgb(clip).size == (96, 64)

    def test_a_clip_that_cannot_be_read(self, tmp_path):
        bad = tmp_path / "bad.mp4"
        bad.write_bytes(b"not a video")
        with pytest.raises(OSError, match="cannot read a frame"):
            gallery.load_rgb(bad)

    def test_thumbnails_are_small_jpegs(self, picture, clip, tmp_path):
        from PIL import Image
        for src in (picture, clip):
            dest = tmp_path / "thumbs" / (src.stem + ".jpg")
            gallery.make_thumb(src, dest)
            im = Image.open(dest)
            assert im.format == "JPEG" and max(im.size) <= gallery.THUMB_PX and not dest.with_suffix(".tmp").exists()


class TestDepth:
    def test_writes_a_grey_map_and_loads_the_model_once(self, picture, tmp_path, monkeypatch):
        from PIL import Image
        loads = []

        def pipeline(task, model, device):
            loads.append((task, model, device))
            return lambda im: {"depth": Image.fromarray((np.linspace(0, 255, im.size[0] * im.size[1]).reshape(im.size[1], im.size[0])).astype("uint8"))}
        mod = types.ModuleType("transformers")
        mod.pipeline = pipeline
        monkeypatch.setitem(sys.modules, "transformers", mod)
        monkeypatch.setattr(gallery, "_DEPTH", {})
        dest = tmp_path / "depth" / "d.png"
        gallery.make_depth(picture, dest)
        gallery.make_depth(picture, tmp_path / "depth" / "d2.png")
        out = Image.open(dest)
        assert out.mode == "L" and out.size == (300, 200) and loads == [("depth-estimation", gallery.DEPTH_MODEL, "cpu")]
        arr = np.asarray(out)
        assert arr.min() == 0 and arr.max() == 255            # stretched to the full range


class TestLocalMusic:
    def test_makes_each_missing_cue_whole_or_not_at_all(self, book, monkeypatch, capsys):
        (book / "audio_chapters.csv").write_text("chapter,music\n1,calm strings\n2,drums\n")
        out = book / "audio" / "musicgen_chapters"
        out.mkdir(parents=True)
        (out / "music-0001.wav").write_bytes(b"x")                     # already made: kept
        prompts = []

        class Tensor:
            def numpy(self):
                return np.zeros(8)

        class Audio:
            def __getitem__(self, i):
                return Tensor() if i == (0, 0) else self
        class Model:
            config = types.SimpleNamespace(audio_encoder=types.SimpleNamespace(sampling_rate=8000))

            def generate(self, **kw):
                return Audio()
        transformers = types.ModuleType("transformers")
        transformers.AutoProcessor = types.SimpleNamespace(from_pretrained=lambda name: lambda text, padding, return_tensors: prompts.append(text) or {})
        transformers.MusicgenForConditionalGeneration = types.SimpleNamespace(from_pretrained=lambda name: Model())
        written = []
        wavfile = types.ModuleType("scipy.io.wavfile")
        wavfile.write = lambda path, rate, data: (written.append((path, rate)), open(path, "wb").write(b"wav"))
        scipy = types.ModuleType("scipy")
        scipy_io = types.ModuleType("scipy.io")
        scipy_io.wavfile = wavfile
        scipy.io = scipy_io
        for name, mod in (("transformers", transformers), ("scipy", scipy), ("scipy.io", scipy_io), ("scipy.io.wavfile", wavfile)):
            monkeypatch.setitem(sys.modules, name, mod)
        la.music(book)
        assert prompts == [["drums"]] and (out / "music-0002.wav").read_bytes() == b"wav" and (out / "music-0001.wav").read_bytes() == b"x"
        assert written[0][1] == 8000 and not list(out.glob("*.tmp.wav")) and "cue 2/2" in capsys.readouterr().out
