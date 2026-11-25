import struct
import zlib

import pytest

from cont.generation import (GenerationError, ImageRequest, ImageResult, get_generator, list_models,
                             list_purposes, register_type)


def _png_size(b):
    assert b[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", b[16:24])
    return w, h


def _idat_ok(b):
    # walk chunks, check every crc and that the pixel data decompresses to the expected size
    i, w, h, data = 8, 0, 0, b""
    while i < len(b):
        n, tag = struct.unpack(">I4s", b[i:i + 8])
        body = b[i + 8:i + 8 + n]
        assert struct.unpack(">I", b[i + 8 + n:i + 12 + n])[0] == zlib.crc32(tag + body) & 0xFFFFFFFF
        if tag == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
        if tag == b"IDAT":
            data += body
        i += 12 + n
    assert len(zlib.decompress(data)) == h * (1 + 3 * w)


def test_fake_makes_valid_png_marked_not_real():
    g = get_generator("fake")
    r = g.generate(ImageRequest("a bolt", width=128, height=64, seed=3))
    assert r.real is False and g.real is False
    assert _png_size(r.png) == (128, 64) == (r.width, r.height)
    _idat_ok(r.png)


def test_fake_is_deterministic_and_seed_changes_it():
    g = get_generator("fake")
    a = g.generate(ImageRequest("a bolt", seed=1))
    assert a.png == g.generate(ImageRequest("a bolt", seed=1)).png
    assert a.sha256 != g.generate(ImageRequest("a bolt", seed=2)).sha256
    assert a.sha256 != g.generate(ImageRequest("a nut", seed=1)).sha256


def test_fake_keeps_asked_size_in_record_but_draws_small():
    r = get_generator("fake").generate(ImageRequest("x", width=1024, height=1024))
    assert (r.width, r.height) == (256, 256)
    rec = r.record()
    assert rec["params"]["asked_width"] == 1024 and rec["real"] is False
    assert rec["sha256"] == r.sha256 and "png" not in rec


@pytest.mark.parametrize("kw", [
    {"prompt": ""}, {"prompt": "   "}, {"prompt": "x", "width": 100}, {"prompt": "x", "width": 32},
    {"prompt": "x", "height": 4096}, {"prompt": "x", "width": True}, {"prompt": "x", "width": 512.0},
    {"prompt": "x", "seed": -1}, {"prompt": "x", "seed": 1.5}, {"prompt": "x", "steps": 0},
    {"prompt": "x", "steps": 500}, {"prompt": 5},
])
def test_bad_requests_refused(kw):
    with pytest.raises(GenerationError):
        ImageRequest(**kw)


def test_purposes_map_to_models_and_unknown_refused():
    assert {"draft", "general", "text_heavy"} <= set(list_purposes())
    assert get_generator(purpose="general").name == "fake"
    with pytest.raises(KeyError, match="purpose"):
        get_generator(purpose="poster")
    with pytest.raises(KeyError):
        get_generator("nope")


def test_every_purpose_points_at_a_listed_model():
    assert set(list_purposes().values()) <= set(list_models())


def test_env_overrides_purpose(monkeypatch, tmp_path):
    (tmp_path / "generation").mkdir()
    (tmp_path / "generation" / "models.yaml").write_text(
        "default: a\npurposes: {general: a}\nmodels:\n  a: {type: fake}\n  b: {type: fake}\n", encoding="utf-8")
    assert get_generator(purpose="general", config_dir=tmp_path).name == "a"
    monkeypatch.setenv("CONT_GEN_MODEL", "b")
    assert get_generator(purpose="general", config_dir=tmp_path).name == "b"
    assert get_generator("a", config_dir=tmp_path).name == "a"  # explicit name wins


def test_local_file_adds_models(tmp_path):
    d = tmp_path / "generation"
    d.mkdir()
    (d / "models.yaml").write_text("default: a\nmodels:\n  a: {type: fake}\n", encoding="utf-8")
    (d / "models.local.yaml").write_text("models:\n  mine: {type: fake, max_side: 64}\n", encoding="utf-8")
    g = get_generator("mine", config_dir=tmp_path)
    assert g.generate(ImageRequest("x", width=512, height=512)).width == 64


def test_register_new_type(tmp_path):
    class Fixed:
        real = True

        def __init__(self, name, model="m", **_):
            self.name, self.model = name, model

        def generate(self, request):
            return ImageResult(b"x", 8, 8, self.name, "w", request.seed, True)

    register_type("fixed_test", Fixed)
    (tmp_path / "generation").mkdir()
    (tmp_path / "generation" / "models.yaml").write_text(
        "default: f\nmodels:\n  f: {type: fixed_test}\n", encoding="utf-8")
    r = get_generator(config_dir=tmp_path).generate(ImageRequest("x"))
    assert r.real is True and r.record()["weights"] == "w"


def test_unregistered_type_refused(tmp_path):
    (tmp_path / "generation").mkdir()
    (tmp_path / "generation" / "models.yaml").write_text(
        "default: f\nmodels:\n  f: {type: nowhere}\n", encoding="utf-8")
    with pytest.raises(KeyError, match="not registered"):
        get_generator(config_dir=tmp_path)


# ---- diffusers adapter: tested with a fake pipeline, no diffusers/GPU needed ----
import io
import os

from cont.generation.diffusers_gen import Diffusers


class _Img:
    def __init__(self, w, h):
        self.width, self.height = w, h

    def save(self, buf, format):
        buf.write(b"\x89PNG-fake")


class _Pipe:
    def __init__(self):
        self.calls = []

    def __call__(self, **kw):
        self.calls.append(kw)

        class Out:
            images = [_Img(kw["width"], kw["height"])]
        return Out()


def _adapter(pipe, **kw):
    loads = []

    def loader(model, dtype, offload, pipeline):
        loads.append((model, dtype, offload, pipeline))
        return pipe

    return Diffusers(name="m", model="org/model", loader=loader, **kw), loads


def test_diffusers_adapter_passes_request_and_marks_real():
    pipe = _Pipe()
    g, loads = _adapter(pipe, steps=20, guidance=4.5)
    r = g.generate(ImageRequest("a bolt", width=512, height=256, seed=7, negative_prompt="blur"))
    c = pipe.calls[0]
    assert (c["width"], c["height"], c["num_inference_steps"], c["guidance_scale"]) == (512, 256, 20, 4.5)
    assert c["prompt"] == "a bolt" and c["negative_prompt"] == "blur"
    assert r.real is True and r.weights == "org/model" and r.record()["params"]["steps"] == 20
    assert (r.width, r.height) == (512, 256)


def test_diffusers_loads_once_and_request_steps_win():
    pipe = _Pipe()
    g, loads = _adapter(pipe, steps=20)
    g.generate(ImageRequest("a"))
    g.generate(ImageRequest("b", steps=4))
    assert len(loads) == 1 and [c["num_inference_steps"] for c in pipe.calls] == [20, 4]
    assert "negative_prompt" not in pipe.calls[0]


def test_diffusers_empty_output_is_an_error():
    class Empty:
        def __call__(self, **kw):
            class O:
                images = []
            return O()

    g, _ = _adapter(Empty())
    with pytest.raises(GenerationError, match="no image"):
        g.generate(ImageRequest("a"))


def test_diffusers_type_is_registered_and_lazy():
    # building one must not import diffusers or touch a GPU
    import sys
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp()) / "generation"
    d.mkdir()
    (d / "models.yaml").write_text("default: s\nmodels:\n  s: {type: diffusers, model: x/y}\n", encoding="utf-8")
    g = get_generator(config_dir=d.parent)
    assert g.real is True and "diffusers" not in sys.modules


@pytest.mark.skipif(os.environ.get("CONT_GEN_REAL") != "1",
                    reason="real model run is off by default: set CONT_GEN_REAL=1 and CONT_GEN_REAL_MODEL=<name>")
def test_real_model_makes_a_png():
    g = get_generator(os.environ.get("CONT_GEN_REAL_MODEL"))
    r = g.generate(ImageRequest("a steel hex bolt on white background", width=512, height=512, seed=1, steps=10))
    assert r.real and r.png[:8] == b"\x89PNG\r\n\x1a\n" and r.width == 512
