from firebase_admin import credentials, firestore, initialize_app
from flask import Flask, request, render_template
from datetime import datetime
from threading import Lock
import time
import json


class WatchRequest:
    def __init__(self, address, sender, value, start_date):
        self.address = address
        self.sender = sender
        self.value = value
        self.start_date = start_date
        self.hash = ""
        self.processed = False

    def to_dict(self):
        return {
            u'address': self.address,
            u'sender': self.sender,
            u'value': self.value,
            u'start_date': self.start_date,
            u'hash': self.hash,
            u'processed': self.processed
        }


app = Flask(__name__)
cred = credentials.Certificate("db/key.json")
default_app = initialize_app(cred)
db = firestore.client()


ERC20 = ["ETH"]
accepted_coins = ["btc", "eth"]


@app.route('/api/request', methods=["GET"])
def api_request():
    key = request.args.get("key")

    if len(db.collection(u'keys').where(u'id', u'==', key).get()) == 0:
        return render_template("main.html", response="invalid key")

    address = request.args.get("address")
    sender = request.args.get("sender")
    value = request.args.get("value")
    start_date = None
    # start_date = request.args.get("start_date")
    if start_date is None:
        start_date = datetime.now()
#    else:
#        start_date = start_date.split('-')
#        start_date = datetime(year=int(start_date[3]), month=int(start_date[2]), day=int(start_date[0]))

    db.collection(u'requests').add({
        u'address': address,
        u'sender': sender,
        u'value': int(value),
        u'start_date': start_date,
        u'key': key
    })

    return render_template("main.html", response="request approved")


@app.route('/')
def index():
    return 'Web App with Python Flask!'


app.run(threaded=True, host='0.0.0.0', port=8000)
