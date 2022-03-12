from firebase_admin import credentials, firestore, initialize_app
from flask import Flask, request, render_template
from google.cloud.firestore_v1 import Increment
import datetime


class WatchRequest:
    def __init__(self, last_block_checked):
        self.last_block_checked = last_block_checked
        self.requests = []

    def to_dict(self):
        return {
            'last_block_checked': self.last_block_checked
        }


class WatchData:
    def __init__(self, sender, value, start_date):
        self.sender = sender
        self.value = value
        self.start_date = start_date
        self.hash = ""
        self.processed = False

    def to_dict(self):
        return {
            'sender': self.sender,
            'value': self.value,
            'start_date': self.start_date,
            'hash': self.hash,
            'processed': self.processed
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

    key = db.collection('keys').document(key)
    if not key.get().exists:
        return render_template("main.html", response="invalid key")

    value = request.args.get("value")
    if value is not None:
        try:
            value = float(value)
            if value <= 0:
                return render_template("main.html", response="invalid value")
        except ValueError:
            return render_template("main.html", response="invalid value")

    start_date = request.args.get("start_date")
    if start_date is None:
        start_date = datetime.datetime.now(tz=datetime.timezone.utc)
    else:
        start_date = start_date.split('-')
        try:
            start_date = datetime.datetime(year=int(start_date[3]), month=int(start_date[2]), day=int(start_date[0]),
                                           tzinfo=datetime.timezone.utc)
        except ValueError:
            return render_template("main.html", response="invalid date")

    address = request.args.get("address")
    sender = request.args.get("sender")

    if not db.collection('requests').document(address).get().exists:
        db.collection('requests').document(address).set({
            'last_block_checked': "0"
        })

    db.collection('requests').document(address).collection('data').add({
        'start_date': start_date,
        'processed': False,
        'sender': sender,
        'value': value,
        'hash': "",
        'key': key,
    })

    key.update({'active_requests': Increment(1)})

    return render_template("main.html", response="request approved")


@app.route('/')
def index():
    return 'Web App with Python Flask!'


app.run(threaded=True, host='0.0.0.0', port=8000)
