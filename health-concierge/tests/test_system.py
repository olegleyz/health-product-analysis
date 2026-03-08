"""Tests for system hardening scripts: backup_db and error_alert."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# backup_db tests
# ---------------------------------------------------------------------------

class TestBackupDb:
    """Tests for scripts/backup_db.py."""

    def test_backup_creates_file(self, tmp_path: Path) -> None:
        """Backup copies the database file to the backup directory."""
        from scripts.backup_db import backup_database

        db_file = tmp_path / "test.db"
        db_file.write_text("fake-db-content")
        backup_dir = tmp_path / "backups"

        result = backup_database(
            db_path=str(db_file),
            backup_dir=str(backup_dir),
        )

        assert result is not None
        assert result.exists()
        assert result.read_text() == "fake-db-content"
        assert result.name.startswith("concierge_")
        assert result.name.endswith(".db")

    def test_backup_returns_none_for_missing_db(self, tmp_path: Path) -> None:
        """Returns None when database file doesn't exist."""
        from scripts.backup_db import backup_database

        result = backup_database(
            db_path=str(tmp_path / "nonexistent.db"),
            backup_dir=str(tmp_path / "backups"),
        )
        assert result is None

    def test_backup_rotates_old_files(self, tmp_path: Path) -> None:
        """Keeps only max_backups files, deleting the oldest."""
        from scripts.backup_db import backup_database

        db_file = tmp_path / "test.db"
        db_file.write_text("content")
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        # Create 5 pre-existing backups with sequential names
        for i in range(5):
            (backup_dir / f"concierge_2025010{i}T000000Z.db").write_text(f"old-{i}")

        # Run backup with max_backups=3
        result = backup_database(
            db_path=str(db_file),
            backup_dir=str(backup_dir),
            max_backups=3,
        )

        assert result is not None
        remaining = sorted(backup_dir.glob("concierge_*.db"))
        assert len(remaining) == 3
        # The oldest files should have been deleted
        assert not (backup_dir / "concierge_20250100T000000Z.db").exists()
        assert not (backup_dir / "concierge_20250101T000000Z.db").exists()
        assert not (backup_dir / "concierge_20250102T000000Z.db").exists()


# ---------------------------------------------------------------------------
# error_alert tests
# ---------------------------------------------------------------------------

class TestErrorAlert:
    """Tests for scripts/error_alert.py."""

    def test_successful_command_returns_zero(self) -> None:
        """A successful command returns exit code 0 and sends no alert."""
        from scripts.error_alert import run_and_alert

        with patch("scripts.error_alert.send_message") as mock_send:
            with patch("scripts.error_alert.settings") as mock_settings:
                mock_settings.user_telegram_ids = ["123"]
                code = run_and_alert([sys.executable, "-c", "print('ok')"])

        assert code == 0
        mock_send.assert_not_called()

    def test_failed_command_returns_nonzero(self) -> None:
        """A failing command returns a non-zero exit code."""
        from scripts.error_alert import run_and_alert

        with patch("scripts.error_alert.send_message", new_callable=AsyncMock) as mock_send:
            with patch("scripts.error_alert.settings") as mock_settings:
                mock_settings.user_telegram_ids = ["123"]
                code = run_and_alert([sys.executable, "-c", "raise SystemExit(42)"])

        assert code == 42

    def test_failed_command_sends_alert(self) -> None:
        """A failing command triggers a Telegram alert to the admin."""
        from scripts.error_alert import run_and_alert

        with patch("scripts.error_alert.send_message", new_callable=AsyncMock) as mock_send:
            with patch("scripts.error_alert.settings") as mock_settings:
                mock_settings.user_telegram_ids = ["999"]
                run_and_alert([sys.executable, "-c", "import sys; sys.exit(1)"])

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[0][0] == "999"
        assert "Command failed" in call_args[0][1]
        assert "Exit code: 1" in call_args[0][1]

    def test_failed_command_no_users_configured(self) -> None:
        """No crash when user_telegram_ids is empty."""
        from scripts.error_alert import run_and_alert

        with patch("scripts.error_alert.send_message", new_callable=AsyncMock) as mock_send:
            with patch("scripts.error_alert.settings") as mock_settings:
                mock_settings.user_telegram_ids = []
                code = run_and_alert([sys.executable, "-c", "import sys; sys.exit(1)"])

        assert code == 1
        mock_send.assert_not_called()

    def test_alert_message_contains_stderr(self) -> None:
        """The alert message includes stderr output from the failed command."""
        from scripts.error_alert import run_and_alert

        with patch("scripts.error_alert.send_message", new_callable=AsyncMock) as mock_send:
            with patch("scripts.error_alert.settings") as mock_settings:
                mock_settings.user_telegram_ids = ["123"]
                run_and_alert([
                    sys.executable, "-c",
                    "import sys; sys.stderr.write('something broke'); sys.exit(1)",
                ])

        msg = mock_send.call_args[0][1]
        assert "something broke" in msg
