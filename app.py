import json
import os

import requests

from flask import Flask
from flask_marshmallow import Marshmallow
from flask_sqlalchemy import SQLAlchemy

import config

app = Flask(__name__)
if app.config['ENV'] == 'development':
    app.config.from_object(config.Config)
else:
    app.config.from_object(config.ConfigProd)

db = SQLAlchemy(app)
ma = Marshmallow(app)




@app.route("/")
def hello_world():
    req = requests.get('https://www.googleapis.com/books/v1/volumes?q=Hobbit')
    jsdata = req.json()
    return jsdata


if __name__ == '__main__':
    app.run()
