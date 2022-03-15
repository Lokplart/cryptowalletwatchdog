from firebase_admin import credentials, firestore, initialize_app
from google.cloud.firestore_v1 import Increment
from flask import Flask, request, render_template
from threading import Thread, Lock
from uuid import uuid1
import urllib.request
import datetime
import time
import json


def API_BTC(watch_request):
    url = "https://blockchain.info/rawaddr/" + watch_request.address + "?offset=" + str(watch_request.last_block_checked)
    trx_data = json.loads(urllib.request.urlopen(url).read().decode())

    if watch_request.last_block_checked < trx_data["n_tx"]:
        watch_request.last_block_checked = trx_data["n_tx"]
        requests.document(watch_request.address).update({"last_block_checked": str(trx_data["n_tx"])})

    earliest_starting_time = datetime.datetime.now(tz=datetime.timezone.utc)
    for watch_data in watch_request.watch_data:
        if watch_data.processed is False and watch_data.start_date < earliest_starting_time:
            earliest_starting_time = watch_data.start_date

    for trx in trx_data["txs"]:
        trx_time = datetime.datetime.fromtimestamp(trx["time"], tz=datetime.timezone.utc)
        if trx_time < earliest_starting_time and watch_request.address not in trx["inputs"]:
            break

        print("checking", trx["hash"], "for", watch_request.address)

        for watch_data in watch_request.watch_data:
            if watch_data.processed is True or trx_time < watch_data.start_date:
                continue

            if watch_data.sender is not None:
                match_sender = watch_data.sender in trx["inputs"]
            else:
                match_sender = True

            if watch_data.value is not None:
                match_value = None
                for out in trx["out"]:
                    if out["addr"] == watch_request.address:
                        match_value = out["value"] == watch_data.value
                        break
            else:
                match_value = True

            if match_value and match_sender:
                watch_data.processed = True
                watch_data.hash = trx["hash"]
                requests.document(watch_request.address).collection('data').document(watch_data.data_id).update({
                    "processed": True,
                    "hash": watch_data.hash
                })
                watch_request.key.update({"active_requests": Increment(-1)})
                print("--- found", watch_data.hash, "for", watch_data.data_id)
                break


class WatchData:
    def __init__(self, data_id, sender, value, start_date, request_date, trx_hash, processed):
        self.data_id = data_id
        self.sender = sender
        if value is not None:
            self.value = int(value)
        else:
            self.value = None
        self.request_date = request_date
        self.start_date = start_date
        self.hash = trx_hash
        self.processed = processed

    @staticmethod
    def from_dict(data_id, data):
        return WatchData(data_id, data["sender"], data["value"], data["start_date"], data["request_date"], data["hash"],
                         data["processed"])


class WatchRequest:
    def __init__(self, address, coin, last_block_checked, key):
        self.address = address
        self.coin = coin
        self.last_block_checked = int(last_block_checked)
        self.key = key
        self.watch_data = []

    def has_active_requests(self):
        for watch_data in self.watch_data:
            if watch_data.processed is False:
                return True

        return False

    @staticmethod
    def from_dict(address, request_data):
        return WatchRequest(address, request_data["coin"], request_data["last_block_checked"], request_data["key"])


class Watcher(Thread):
    def __init__(self):
        super(Watcher, self).__init__()

    def run(self):
        while True:
            for address in watches:
                if not watches[address].has_active_requests():
                    continue

                if watches[address].coin == "btc":
                    API_BTC(watches[address])

            time.sleep(300)


def pull():
    global watches
    watches = {}
    for address in requests.stream():
        watches[address.id] = (WatchRequest.from_dict(address.id, address.to_dict()))
        for data in requests.document(address.id).collection("data").stream():
            watches[address.id].watch_data.append(WatchData.from_dict(data.id, data.to_dict()))
        watches[address.id].watch_data.sort(key=lambda x: x.request_date)


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


@app.route('/api/request', methods=["GET", "POST"])
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
    if coin is not None:
        coin = coin.lower()
        if coin not in accepted_coins:
            request_lock.release()
            return render_template("main.html", response="invalid coin")
    else:
        request_lock.release()
        return render_template("main.html", response="invalid coin")

    # getting and verifying value - optional
    value = request.args.get("value")
    if value is not None:
        try:
            value = float(value)
            if value <= 0:
                request_lock.release()
                return render_template("main.html", response="invalid value")
            if coin == "btc":
                value *= 10e+7
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
            start_date = datetime.datetime(year=int(start_date[2]), month=int(start_date[1]), day=int(start_date[0]),
                                           tzinfo=datetime.timezone.utc)
        except ValueError:
            request_lock.release()
            return render_template("main.html", response="invalid date")

    # getting client address - mandatory
    address = request.args.get("address")
    # getting expected sender address - optional
    sender = request.args.get("sender")

    request_date = datetime.datetime.now(tz=datetime.timezone.utc)

    # if new address, add it to db
    if not requests.document(address).get().exists:
        requests.document(address).set({
            'key': key,
            'coin': coin,
            'last_block_checked': "0"
        })
        watches[address] = WatchRequest(address, coin, 0, key)

    # storing request
    data_id = str(uuid1())
    requests.document(address).collection('data').document(data_id).set({
        'request_date': request_date,
        'start_date': start_date,
        'processed': False,
        'sender': sender,
        'value': str(value),
        'hash': ""
    })

    watches[address].watch_data.append(WatchData(data_id, sender, value, start_date, request_date, "", False))
    watches[address].watch_data.sort(key=lambda x: x.request_date)

    key.update({'active_requests': Increment(1)})

    request_lock.release()
    return render_template("main.html", response=data_id)


@app.route('/')
def index():
    return 'Web App with Python Flask!'


watcher = Watcher()
watcher.start()

app.run(threaded=True, host='0.0.0.0', port=8000)
