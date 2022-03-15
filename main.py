from firebase_admin import credentials, firestore, initialize_app
from google.cloud.firestore_v1 import Increment
from flask import Flask, request, render_template
from threading import Thread, Lock
from string import digits, ascii_lowercase, ascii_uppercase
from random import choice
import datetime
import time


class WatchData:
    def __init__(self, data_id, sender, value, start_date, trx_hash, processed):
        self.data_id = data_id
        self.sender = sender
        self.value = value
        self.start_date = start_date
        self.hash = trx_hash
        self.processed = processed

    @staticmethod
    def from_dict(data_id, data):
        return WatchData(data_id, data["sender"], data["value"], data["start_date"], data["hash"], data["processed"])


class WatchRequest:
    def __init__(self, address, coin, last_block_checked, key):
        self.address = address
        self.coin = coin
        self.last_block_checked = last_block_checked
        self.key = key
        self.watch_data = []

    @staticmethod
    def from_dict(address, request_data):
        return WatchRequest(address, request_data["coin"], request_data["last_block_checked"], request_data["key"])


class Watcher(Thread):
    def __init__(self):
        super(Watcher, self).__init__()

    def run(self):
        while True:

            time.sleep(300)


def generate_data_id(collection_ref):
    data_id = ''.join(choice(digits + ascii_lowercase + ascii_uppercase) for _ in range(20))
    while collection_ref.document(data_id).get().exists:
        data_id = ''.join(choice(digits + ascii_lowercase + ascii_uppercase) for _ in range(20))

    return data_id


def pull():
    global watches
    watches = {}
    for address in requests.stream():
        watches[address] = (WatchRequest.from_dict(address.id, address.to_dict()))
        for data in requests.document(address).collection("data").stream():
            watches[address].watch_data.append(WatchData.from_dict(data.id, data.to_dict()))


app = Flask(__name__)
cred = credentials.Certificate("db/key.json")
default_app = initialize_app(cred)
db = firestore.client()

keys = db.collection('keys')
requests = db.collection('requests')
watches = {}
pull()

ERC20 = ["ETH"]
accepted_coins = ["btc", "eth"]
request_lock = Lock()


@app.route('/api/request', methods=["GET"])
def api_request():
    request_lock.acquire()
    global watches

    # getting and verifying key - mandatory
    key = request.args.get("key")
    if key is not None:
        key = keys.document(key)
        if not key.get().exists:
            request_lock.release()
            return render_template("main.html", response="invalid key")
    else:
        request_lock.release()
        return render_template("main.html", response="invalid key")

    # getting and verifying coin - mandatory
    coin = request.args.get("coin")
    if coin not in accepted_coins:
        return render_template("main.html", response="invalid coin")

    # getting and verifying value - optional
    value = request.args.get("value")
    if value is not None:
        try:
            value = float(value)
            if value <= 0:
                request_lock.release()
                return render_template("main.html", response="invalid value")
        except ValueError:
            request_lock.release()
            return render_template("main.html", response="invalid value")

    # getting and verifying starting date - optional, will be current date & time if None
    start_date = request.args.get("start_date")
    if start_date is None:
        start_date = datetime.datetime.now(tz=datetime.timezone.utc)
    else:
        start_date = start_date.split('-')
        try:
            start_date = datetime.datetime(year=int(start_date[3]), month=int(start_date[2]), day=int(start_date[0]),
                                           tzinfo=datetime.timezone.utc)
        except ValueError:
            request_lock.release()
            return render_template("main.html", response="invalid date")

    # getting client address - mandatory
    address = request.args.get("address")
    # getting expected sender address - optional
    sender = request.args.get("sender")

    # if new address, add it to db
    if not requests.document(address).get().exists:
        requests.document(address).set({
            'key': key,
            'coin': coin,
            'last_block_checked': "0"
        })
        watches[address] = WatchRequest(address, coin, 0, key)

    # storing request
    data_id = generate_data_id(requests.document(address).collection('data'))
    requests.document(address).collection('data').document(data_id).set({
        'start_date': start_date,
        'processed': False,
        'sender': sender,
        'value': value,
        'hash': "",
    })

    watches[address].watch_data.append(WatchData(data_id, sender, value, start_date, "", False))

    key.update({'active_requests': Increment(1)})

    request_lock.release()
    return render_template("main.html", response="request approved")


@app.route('/')
def index():
    return 'Web App with Python Flask!'


app.run(threaded=True, host='0.0.0.0', port=8000)
