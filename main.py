from flask import Flask
from flask import request
from flask import render_template
from datetime import datetime
from threading import Lock
from threading import Thread
import urllib.request
import time
import json

ERC20 = ["ETH"]


def match(request_data, trx_data):
    if request_data[0] is not None and request_data[1] is not None:
        return request_data[0] == trx_data[0] and request_data[1] == trx_data[1]
    elif request_data[0] is not None and request_data[1] is None:
        return request_data[0] == trx_data[0]
    elif request_data[0] is None and request_data[1] is not None:
        return request_data[1] == trx_data[1]
    else:
        return True


def check_request(key, address, trx_timestamp, trx_sender, trx_value, trx_hash):
    for i in range(len(requests[key][address]["requests"])):
        if requests[key][address]["requests"][i]["processed"] is False and \
                requests[key][address]["requests"][i]["start_date"] >= trx_timestamp:

            if match([requests[key][address]["requests"][i]["sender"],
                      requests[key][address]["requests"][i]["value"]],
                     [trx_sender, trx_value]):
                print("\t\tProcessed:", requests[key][address]["requests"][i])
                requests[key][address]["requests"][i]["processed"] = True
                requests[key][address]["requests"][i]["hash"] = trx_hash


def call_api_ERC20(key, address):
    url_base = "https://api.etherscan.io/api?module=account&action=txlist"
    url_address = "&address=" + address
    url_block_data = "&startblock=" + str(requests[key][address]["last_block_checked"]) + "&endblock=99999999"
    url_last = "&sort=asc&apikey=DBQ2CTXH6NDZNDR8RKBDPDVWVSFSDZBJ5Y"
    url = url_base + url_address + url_block_data + url_last
    transaction_list = json.loads(urllib.request.urlopen(url).read().decode())["result"]

    for transaction in transaction_list:
        trx_block_number = int(transaction["blockNumber"])
        trx_timestamp = time.gmtime(int(transaction["timeStamp"]))
        trx_sender = transaction["from"]
        trx_value = int(transaction["value"])
        trx_hash = transaction["hash"]

        requests[key][address]["last_block_checked"] = trx_block_number

        check_request(key, address, trx_timestamp, trx_sender, trx_value, trx_hash)


class Watcher(Thread):
    def __init__(self):
        super(Watcher, self).__init__()

    def run(self):
        while True:
            print("Watcher - Starting")
            for key in requests:
                print("\tChecking for", keys[key]["owner"])
                for address in requests[key]:
                    if address["coin"] in ERC20:
                        call_api_ERC20(key, address)

            time.sleep(300)


app = Flask(__name__)
requests = json.load(open("db/watch_requests.json"))
keys = json.load(open("db/api_keys.json"))
accepted_coins = ["btc", "eth"]
db_lock = Lock()


@app.route('/api', methods=["GET"])
def api():
    db_lock.acquire()
    key = request.args.get("key")
    coin = request.args.get("coin")
    value = request.args.get("value")
    sender = request.args.get("sender")
    address = request.args.get("address")
    start_date = request.args.get("start_date")
    if start_date is None:
        start_date = datetime.now().strftime("%d-%m%Y")

    if None not in [key, coin] and key in keys and coin in accepted_coins:
        if key not in requests:
            requests[key] = {}
        if address not in requests[key]:
            requests[key][address] = {
                "last_block_checked": 0,
                "coin": coin,
                "requests": [],
                "processed": []
            }
        requests[key][address]["requests"].append({
            "id": len(requests[key][address]["requests"]),
            "value": value,
            "sender": sender,
            "start_date": time.strptime(start_date, "%d-%m-%Y"),
            "processed": False
        })

        open("db/watch_requests.json", 'w').write(json.dumps(requests, sort_keys=True, indent=4))
        response = "approved"
    else:
        response = "denied"

    db_lock.release()
    return render_template("main.html", response=response)


@app.route('/')
def index():
    return 'Web App with Python Flask!'


watcher = Watcher()
# watcher.start()

app.run(host='0.0.0.0', port=8000)
