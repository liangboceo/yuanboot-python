import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "prepare_release", Path(__file__).resolve().parents[1] / "scripts/prepare_release.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.mark.parametrize("version", ["0.1.3", "1.0.0", "0.2.0rc1"])
def test_prepare_release_sets_single_version_source(tmp_path, version):
    directory = tmp_path / "src/yuanboot"
    directory.mkdir(parents=True)
    assert release.prepare_release(version, tmp_path) == "v" + version
    assert (directory / "_version.py").read_text() == f'__version__ = "{version}"\n'


@pytest.mark.parametrize("version", ["v0.1.3", "../bad", "1.2", "1.2.3\n", '1.2.3";bad'])
def test_invalid_release_version_never_writes_files(tmp_path, version):
    with pytest.raises(ValueError, match="Version"):
        release.prepare_release(version, tmp_path)
    assert not list(tmp_path.iterdir())
