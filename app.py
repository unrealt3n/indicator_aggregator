"""
BTC Trend Prediction Dashboard — Flask Entry Point.
"""

import logging
from flask import Flask, send_from_directory
from flask_cors import CORS

import config
from presentation.routes import api

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = Flask(__name__, static_folder="static")
CORS(app)
app.register_blueprint(api)


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
