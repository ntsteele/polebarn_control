#!/usr/bin/env python3
from flask import Blueprint, render_template

diag_bp = Blueprint("diagnostics", __name__)

@diag_bp.route("/diagnostics")
def diagnostics_page():
    """Serve the Diagnostics dashboard."""
    return render_template("diagnostics.html")
