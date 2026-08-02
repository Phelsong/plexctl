"""Test configuration for plexctl."""

import os
import tempfile
import warnings
from pathlib import Path
from unittest.mock import patch

from plexctl.config import (
    PlexConfig,
    _check_permissions,
    _read_toml_config,
    config_dir,
    config_path,
    load_config,
)
from plexctl.plugins.shoko.config import ShokoConfig, load_shoko_config


def test_config_defaults() -> None:
    """PlexConfig should have sensible defaults."""
    config = PlexConfig(url="http://localhost:32400", token="test-token")
    assert config.url == "http://localhost:32400"
    assert config.token == "test-token"
    assert config.timeout == 30


def test_config_is_valid_with_required_fields() -> None:
    """Config should validate when required fields are present."""
    config = PlexConfig(url="http://localhost:32400", token="test-token")
    assert config.is_valid()


def test_config_is_invalid_without_token() -> None:
    """Config should be invalid when token is empty."""
    config = PlexConfig(url="http://localhost:32400", token="")
    assert not config.is_valid()


class TestShokoConfig:
    """Test ShokoConfig validation."""

    def test_shoko_config_defaults(self) -> None:
        config = ShokoConfig(url="http://localhost:8111", apikey="test-key")
        assert config.url == "http://localhost:8111"
        assert config.apikey == "test-key"
        assert config.timeout == 30

    def test_shoko_config_valid(self) -> None:
        config = ShokoConfig(url="http://localhost:8111", apikey="test-key")
        assert config.is_valid()

    def test_shoko_config_invalid_without_key(self) -> None:
        config = ShokoConfig(url="http://localhost:8111", apikey="")
        assert not config.is_valid()


class TestConfigPath:
    """Test XDG config path resolution."""

    def test_default_config_dir(self) -> None:
        """Config dir should be ~/.config/plexctl by default."""
        # Clear lru_cache so environment changes take effect.
        config_dir.cache_clear()
        config_path.cache_clear()
        env = os.environ.copy()
        env.pop("XDG_CONFIG_HOME", None)
        with patch.dict(os.environ, env, clear=True):
            result = config_dir()
            assert result == Path.home() / ".config" / "plexctl"

    def test_xdg_config_home_override(self) -> None:
        """Config dir should respect XDG_CONFIG_HOME."""
        # Clear lru_cache so environment changes take effect.
        config_dir.cache_clear()
        config_path.cache_clear()
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "/custom/config"}):
            result = config_dir()
            assert result == Path("/custom/config/plexctl")

    def test_config_path_is_plexctl_toml(self) -> None:
        """Config path should be config_dir/plexctl.toml."""
        config_dir.cache_clear()
        config_path.cache_clear()
        result = config_path()
        assert result.name == "plexctl.toml"
        assert result.parent.name == "plexctl"


class TestReadTomlConfig:
    """Test TOML config file reading."""

    def test_read_valid_toml(self) -> None:
        """Should parse a valid TOML config file."""
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w") as f:
            f.write(
                '[plex]\nurl = "https://plex.test"\ntoken = "abc123"\n\n'
                '[shoko]\nurl = "https://shoko.test"\napikey = "key456"\n'
            )
            f.flush()
            data = _read_toml_config(Path(f.name))
            assert data["plex"]["url"] == "https://plex.test"
            assert data["shoko"]["apikey"] == "key456"

    def test_read_missing_file(self) -> None:
        """Should return empty dict for missing file."""
        data = _read_toml_config(Path("/nonexistent/plexctl.toml"))
        assert data == {}

    def test_read_invalid_toml(self) -> None:
        """Should warn and return empty dict for invalid TOML."""
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w") as f:
            f.write("this is not valid toml = = =")
            f.flush()
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                data = _read_toml_config(Path(f.name))
                assert data == {}
                assert len(w) == 1
                assert "Could not read config file" in str(w[0].message)


class TestCheckPermissions:
    """Test config file permission checking."""

    def test_mode_400_no_warning(self) -> None:
        """Mode 400 should not trigger a warning."""
        with tempfile.NamedTemporaryFile() as f:
            os.chmod(f.name, 0o400)
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                _check_permissions(Path(f.name))
                perm_warnings = [x for x in w if "permissions" in str(x.message)]
                assert len(perm_warnings) == 0

    def test_mode_600_no_warning(self) -> None:
        """Mode 600 should not trigger a warning."""
        with tempfile.NamedTemporaryFile() as f:
            os.chmod(f.name, 0o600)
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                _check_permissions(Path(f.name))
                perm_warnings = [x for x in w if "permissions" in str(x.message)]
                assert len(perm_warnings) == 0

    def test_mode_644_warns(self) -> None:
        """Mode 644 should trigger a permission warning."""
        with tempfile.NamedTemporaryFile() as f:
            os.chmod(f.name, 0o644)
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                _check_permissions(Path(f.name))
                perm_warnings = [x for x in w if "permissions" in str(x.message)]
                assert len(perm_warnings) == 1
                assert "chmod 400" in str(perm_warnings[0].message)

    def test_mode_755_warns(self) -> None:
        """Mode 755 should trigger a permission warning."""
        with tempfile.NamedTemporaryFile() as f:
            os.chmod(f.name, 0o755)
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                _check_permissions(Path(f.name))
                perm_warnings = [x for x in w if "permissions" in str(x.message)]
                assert len(perm_warnings) == 1

    def test_nonexistent_file_no_warning(self) -> None:
        """Missing file should not trigger any warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _check_permissions(Path("/nonexistent/file"))
            perm_warnings = [x for x in w if "permissions" in str(x.message)]
            assert len(perm_warnings) == 0


class TestLoadConfigFromToml:
    """Test loading config from TOML file."""

    def test_load_plex_from_toml(self) -> None:
        """PlexConfig should read from a TOML [plex] section."""
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w") as f:
            f.write(
                '[plex]\nurl = "https://plex.toml.test"\n' 'token = "toml-token"\ntimeout = 60\n'
            )
            f.flush()
            with patch("plexctl.config.config_path", return_value=Path(f.name)):
                config = load_config()
                assert config.url == "https://plex.toml.test"
                assert config.token == "toml-token"
                assert config.timeout == 60

    def test_load_shoko_from_toml(self) -> None:
        """ShokoConfig should read from a TOML [shoko] section."""
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w") as f:
            f.write(
                '[shoko]\nurl = "https://shoko.toml.test"\n'
                'apikey = "toml-key"\nmedia_root = "/media/anime"\n'
            )
            f.flush()
            with patch("plexctl.config.config_path", return_value=Path(f.name)):
                config = load_shoko_config()
                assert config.url == "https://shoko.toml.test"
                assert config.apikey == "toml-key"
                assert config.media_root == "/media/anime"

    def test_env_vars_override_toml(self) -> None:
        """Environment variables should override TOML values."""
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w") as f:
            f.write('[plex]\nurl = "https://toml.test"\ntoken = "toml-token"\n')
            f.flush()
            with (
                patch("plexctl.config.config_path", return_value=Path(f.name)),
                patch.dict(os.environ, {"PLEX_URL": "https://env.test"}, clear=False),
            ):
                config = load_config()
                # Env var should win over TOML
                assert config.url == "https://env.test"
                assert config.token == "toml-token"

    def test_no_toml_file_uses_defaults(self) -> None:
        """Without a TOML file and no env vars, should use defaults."""
        with (
            patch("plexctl.config.config_path", return_value=Path("/nonexistent")),
            # Clear env vars and set a nonexistent .env to prevent .env file loading
            patch.dict(os.environ, {}, clear=True),
        ):
            # Provide env_path that doesn't exist to bypass .env file
            config = load_config(env_path=Path("/nonexistent/.env"))
            assert config.url == "http://localhost:32400"
            assert config.token == ""
