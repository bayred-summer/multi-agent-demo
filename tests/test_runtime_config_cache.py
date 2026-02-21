"""Runtime config cache behavior tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.utils.runtime_config import load_runtime_config


class TestRuntimeConfigCache(unittest.TestCase):
    """Ensures config cache invalidation is safe and deterministic."""

    def test_cache_returns_copy_and_detects_file_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                '\n'.join(
                    [
                        "[defaults]",
                        'provider = "codex"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            config_a = load_runtime_config(str(config_path))
            config_a["defaults"]["provider"] = "mutated"

            config_b = load_runtime_config(str(config_path))
            self.assertEqual(config_b["defaults"]["provider"], "codex")

            config_path.write_text(
                '\n'.join(
                    [
                        "[defaults]",
                        'provider = "claude-minimax"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            config_c = load_runtime_config(str(config_path))
            self.assertEqual(config_c["defaults"]["provider"], "claude-minimax")

    def test_loads_utf8_bom_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            content = '[defaults]\nprovider = "codex"\n'
            config_path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))

            config = load_runtime_config(str(config_path))
            self.assertEqual(config["defaults"]["provider"], "codex")


if __name__ == "__main__":
    unittest.main()
