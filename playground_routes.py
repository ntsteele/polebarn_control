#!/usr/bin/env python3
from flask import Blueprint, render_template

playground_bp = Blueprint("playground", __name__)

@playground_bp.route("/playground")
def playground():
    return render_template("playground.html", title="UI Playground")
