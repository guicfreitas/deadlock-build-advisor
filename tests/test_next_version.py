import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "next_version", Path(__file__).resolve().parent.parent / "packaging" / "next_version.py")
nv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nv)


def test_first_release_uses_the_declared_version():
    assert nv.next_version("0.2.1", []) == "0.2.1"


def test_unbumped_merge_gets_the_next_patch():
    assert nv.next_version("0.2.1", ["v0.2.0", "v0.2.1"]) == "0.2.2"
    assert nv.next_version("0.2.0", ["v0.2.0", "v0.2.9", "v0.2.10"]) == "0.2.11"


def test_manual_bump_wins():
    assert nv.next_version("0.3.0", ["v0.2.7"]) == "0.3.0"


def test_ignores_odd_tags():
    assert nv.next_version("0.2.0", ["v0.2.0", "nightly", "v1.0-beta"]) == "0.2.1"
