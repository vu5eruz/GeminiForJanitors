"""Proxy Application."""

from flask import Flask, Response, request, redirect, url_for
from flask_cors import CORS

################################################################################

app = Flask(__name__)
CORS(app)


@app.route("/", methods=["GET"])
@app.route("/index", methods=["GET"])
@app.route("/index.html", methods=["GET"])
def index():
    requested_path = request.path
    if requested_path == "/index.html":
        return redirect(url_for("index"), code=301)

    return "Hello, World!", 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/health")
@app.route("/healthz")
def health():
    return "All good.", 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/", methods=["POST"])
@app.route("/chat/completions", methods=["POST"])
@app.route("/quiet/", methods=["POST"])
@app.route("/quiet/chat/completions", methods=["POST"])
def proxy():
    return "Not Implemented", 501, {"Content-Type": "text/plain; charset=utf-8"}


################################################################################
