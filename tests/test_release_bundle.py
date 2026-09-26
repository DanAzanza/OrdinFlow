"""
Automated Pytest Suite for OrdinFlow Release Packaging and Verification.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from scripts.build_release import build_release_archive, get_pyproject_version
from scripts.verify_release import verify_bundle, check_hygiene, check_manifest


def test_build_and_verify_release_bundle(tmp_path: Path):
    """Verifies that building a release archive produces a valid, compliant, and verified bundle."""
    current_version = get_pyproject_version()
    dist_dir = tmp_path / "dist"

    # 1. Build release archive
    zip_path, checksum_path = build_release_archive(
        version=current_version,
        output_dir=dist_dir,
        allow_version_mismatch=False,
    )

    assert zip_path.is_file()
    assert checksum_path.is_file()
    assert zip_path.stat().st_size > 50000  # At least 50 KB

    # 2. Run adversarial release verification gate
    verification_success = verify_bundle(
        archive_path=zip_path,
        checksum_path=checksum_path,
    )
    assert verification_success is True


def test_version_mismatch_fails_fast(tmp_path: Path):
    """Ensures build_release_archive fails immediately if git tag disagrees with pyproject.toml."""
    dist_dir = tmp_path / "dist"

    with pytest.raises(ValueError, match="Version mismatch"):
        build_release_archive(
            version="99.99.99",
            output_dir=dist_dir,
            allow_version_mismatch=False,
        )


def test_hygiene_flags_dirty_configs(tmp_path: Path):
    """Ensures hygiene audit flags dirty development paths in settings/config.yaml."""
    fake_bundle = tmp_path / "fake_bundle"
    settings_dir = fake_bundle / "settings"
    settings_dir.mkdir(parents=True)

    dirty_yaml = settings_dir / "config.yaml"
    dirty_yaml.write_text("watch_dir: C:\\DeveloperLocal\\Inbox\ntarget_base_dir: C:\\DeveloperLocal\\Cases\n", encoding="utf-8")

    assert check_hygiene(fake_bundle) is False


def test_manifest_flags_missing_files(tmp_path: Path):
    """Ensures manifest checker detects missing core files."""
    empty_bundle = tmp_path / "empty_bundle"
    empty_bundle.mkdir()

    assert check_manifest(empty_bundle) is False
