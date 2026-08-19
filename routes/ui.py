import os

from flask import Blueprint, render_template

ui_bp = Blueprint("ui", __name__)


@ui_bp.route("/")
def index():
    return render_template("index.html")


@ui_bp.route("/favicon.ico")
def favicon():
    return "", 204


#  STATUS & PROCESS CONTROL


@ui_bp.route("/api/legal/<doc_name>")
def api_legal(doc_name: str):
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    valid = {
        "license": os.path.join(root_dir, "LICENSE"),
        "thirdparty": os.path.join(root_dir, "THIRD_PARTY_LICENSES.md"),
        "privacy": os.path.join(root_dir, "docs", "legal", "PRIVACY_POLICY.md"),
        "checklist": os.path.join(root_dir, "docs", "legal", "COMPLIANCE_CHECKLIST.md"),
    }
    if doc_name not in valid:
        return "Not found", 404

    path = valid[doc_name]
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return "File not found on server", 404
