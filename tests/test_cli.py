import subprocess
import sys


def test_cli_help_runs():
    result = subprocess.run(
        [sys.executable, "-m", "gridreport.cli", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "learn" in result.stdout
    assert "render" in result.stdout
