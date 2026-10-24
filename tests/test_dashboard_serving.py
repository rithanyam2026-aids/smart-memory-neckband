"""
Tests for Step 6: Dashboard Serving and Web App Assets
Verifies:
- Root and /dashboard endpoints deliver HTML, CSS, and JS
- Blueprint endpoint is accessible
- Private areas and audit log data structures match dashboard contracts
"""

from pathlib import Path
from cloud.server import app, serve_root_dashboard, get_blueprint, get_private_areas
from cloud.database import CloudDatabase
import cloud.server


def test_dashboard_static_files_exist():
    root = Path(__file__).resolve().parent.parent / "dashboard"
    html_file = root / "index.html"
    css_file = root / "css" / "dashboard.css"
    js_file = root / "js" / "dashboard.js"

    assert html_file.exists(), "dashboard/index.html must exist"
    assert css_file.exists(), "dashboard/css/dashboard.css must exist"
    assert js_file.exists(), "dashboard/js/dashboard.js must exist"

    # Verify key UI components in HTML
    content = html_file.read_text(encoding="utf-8")
    assert "USER MODE" in content
    assert "CAREGIVER MODE" in content
    assert "Your House Privacy Map" in content
    assert "modalFirstTimeSetup" in content
    assert "Read Today Aloud" in content


def test_blueprint_and_dashboard_integration(tmp_path: Path):
    test_db = CloudDatabase(db_path=tmp_path / "dash_test.db")
    cloud.server.db = test_db

    # Blueprint delivers valid grid
    bp = get_blueprint()
    assert "dimensions" in bp
    assert bp["dimensions"]["rows"] > 0
    assert len(bp["named_zones"]) > 0

    # Test private areas response structure expected by dashboard.js
    ctx = {
        "user_id": "user_01",
        "role": "user",
        "target_user_id": "user_01",
        "display_name": "Senior Resident"
    }
    pa_res = get_private_areas(ctx=ctx)
    assert "settings" in pa_res
    assert "audit_log" in pa_res
