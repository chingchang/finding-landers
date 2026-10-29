from landers import config


def test_default_root_is_under_repo():
    assert config.REPO_ROOT.joinpath("pyproject.toml").exists()
