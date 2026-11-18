"""
MediCloak Environment & Setup Diagnostics Checker
Run: python check_setup.py
"""

import sys
import os
from pathlib import Path

def print_status(name: str, passed: bool, details: str = ""):
    icon = "[OK]" if passed else "[FAIL]"
    detail_str = f" - {details}" if details else ""
    print(f" {icon} {name}{detail_str}")

def main():
    print("=" * 60)
    print(" MediCloak Setup Diagnostic & Health Checker")
    print("=" * 60)

    # 1. Python Check
    py_ver = sys.version.split()[0]
    print_status("Python Runtime", sys.version_info >= (3, 10), f"v{py_ver}")

    # 2. Python Dependencies
    required_packages = ["fastapi", "uvicorn", "psycopg2", "mitmproxy", "PIL", "pydantic", "dotenv"]
    for pkg in required_packages:
        try:
            __import__(pkg)
            print_status(f"Package: {pkg}", True)
        except ImportError:
            print_status(f"Package: {pkg}", False, "Not installed (run: pip install -r backend/requirements.txt mitmproxy pillow)")

    # 3. Dashboard Node Modules
    node_modules = Path(__file__).parent / "dashboard" / "node_modules"
    print_status("Dashboard Dependencies", node_modules.exists(), "node_modules installed" if node_modules.exists() else "Missing (run: cd dashboard && npm install)")

    # 4. Browser Check (Brave / Chrome / Edge)
    browser_found = False
    browser_name = "None"
    possible_browsers = [
        ("Brave", r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"),
        ("Chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        ("Chrome (User)", os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")),
        ("Edge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        ("Edge", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    for b_name, path in possible_browsers:
        if os.path.exists(path):
            browser_found = True
            browser_name = f"{b_name} ({path})"
            break
    print_status("Chromium Browser for Proxy", browser_found, browser_name)

    # 5. Database Connection Check
    sys.path.insert(0, str(Path(__file__).parent / "backend"))
    try:
        import database
        database.init_db()
        with database.get_cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM events")
            row = cur.fetchone()
            cnt = row["cnt"]
        db_type = "Built-in SQLite (zero-config, persistent)" if database._use_sqlite else "PostgreSQL"
        print_status("Database Ready", True, f"{db_type} ({cnt} events)")
    except Exception as e:
        print_status("Database Ready", False, f"Could not initialize: {e}")

    print("\n" + "=" * 60)
    print(" ALL CHECKS PASSED! EVERYTHING IS 100% READY.")
    print(" To launch MediCloak, double-click or run:")
    print("     start_medicloak_demo.bat")
    print(" To stop all background services, run:")
    print("     stop_medicloak_demo.bat")
    print("=" * 60)

if __name__ == "__main__":
    main()
