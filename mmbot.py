from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import BinanceWebSocketApiManager
from datetime import datetime
import ccxt
import requests
import logging
import time
import threading
import os
import json


class Binance:
    def __init__(self, api_key, api_secret):
        self.binance = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'options': {
                'defaultType': 'future',
            },
        })

    def limit_buy_order(self, symbol, quantity, price, post_only=False):
        if not post_only:
            result = self.binance.create_order(symbol=symbol, type="LIMIT", side="BUY", amount=quantity,
                                               price=price)
        else:
            result = self.binance.create_order(symbol=symbol, type="LIMIT", side="BUY", amount=quantity,
                                               price=price, params={"timeInForce": "GTX"})
        return result

    def limit_sell_order(self, symbol, quantity, price, post_only=False):
        if not post_only:
            result = self.binance.create_order(symbol=symbol, type="LIMIT", side="SELL", amount=quantity,
                                               price=price)
        else:
            result = self.binance.create_order(symbol=symbol, type="LIMIT", side="SELL", amount=quantity,
                                               price=price, params={"timeInForce": "GTX"})
        return result

    def market_buy_order(self, symbol, quantity):
        result = self.binance.create_order(symbol=symbol, type="MARKET", side="BUY", amount=quantity)
        return result

    def market_sell_order(self, symbol, quantity):
        result = self.binance.create_order(symbol=symbol, type="MARKET", side="SELL", amount=quantity)
        return result


class pycolor:
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    COLOR_DEFAULT = '\033[39m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    INVISIBLE = '\033[08m'
    REVERCE = '\033[07m'
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'
    BG_DEFAULT = '\033[49m'
    END = '\033[0m'


class robot_param:
    def __init__(self, param_data):
        # self. = param_data[""]
        self.api_key = param_data["api_key"]
        self.api_secret = param_data["api_secret"]
        self.pair = param_data["pair"]
        self.digit = param_data["digit"]
        self.lot = param_data["lot"]
        self.delta = param_data["delta"]
        self.spread = param_data["spread"]
        self.queue_number = param_data["queue_number"]
        self.force_close = param_data["force_close"]
        self.max_position = param_data["max_position"]
        self.wait_time = param_data["wait_time"] * 1000
        self.maker_fee_rate = param_data["maker_fee_rate"]
        self.taker_fee_rate = param_data["taker_fee_rate"]
        self.start_balance = param_data["start_balance"]
        self.slippage = param_data["slippage"]
        self.switch = param_data["switch"]

        self.unit = 1 / (10 ** self.digit)
        self.taker_maker_ratio = self.taker_fee_rate / self.maker_fee_rate

    def target_buy_price(self, sell_price):
        return round((sell_price * (1 - self.maker_fee_rate * self.taker_maker_ratio) / (1 + self.maker_fee_rate)),
                     self.digit)

    def target_sell_price(self, buy_price):
        return round((buy_price * (1 + self.maker_fee_rate) / (1 - self.maker_fee_rate * self.taker_maker_ratio)),
                     self.digit)


def volume_wam(price_lst, volume_lst):
    n = len(price_lst)
    weight = sum(volume_lst)
    weight_sum = 0
    for i in range(n):
        weight_sum += price_lst[i] * volume_lst[i]

    return weight_sum / weight


def color_print(text: str, color: pycolor):
    print(color + text + pycolor.END)


def get_time():
    return int(datetime.now().timestamp() * 1000)


def robot(binance_websocket_api_manager, binance: Binance):
    global wam_avg, price_queue, position_count, volume_wam_avg, counter, real_delta, volume_queue
    global simple_avg, position, ticker, bid, ask, order_time

    while True:
        if binance_websocket_api_manager.is_manager_stopping():
            exit(0)
        oldest_stream_data_from_stream_buffer = binance_websocket_api_manager.pop_stream_data_from_stream_buffer()
        if oldest_stream_data_from_stream_buffer is False:
            time.sleep(0.01)
        else:
            try:
                config_open = open("./param.json", "r")
                param_json = json.load(config_open)
                param = robot_param(param_json)

                raw_data = json.loads(oldest_stream_data_from_stream_buffer)
                if raw_data["stream"] == "btcusdt@aggTrade":
                    ticker = raw_data["data"]
                    if len(price_queue) <= param.queue_number + 1:
                        price_queue.append(float(ticker['p']))
                        volume_queue.append(float(ticker['q']))
                    print(json.dumps(ticker, indent=4))
                elif raw_data["stream"] == "btcusdt@depth5":
                    bid = float(raw_data["data"]["b"][0][0])
                    ask = float(raw_data["data"]["a"][0][0])

                if param.switch:
                    if len(price_queue) >= param.queue_number:
                        if not ticker['m']:
                            if float(ticker['p']) - volume_wam(price_queue, volume_queue) >= param.delta:
                                if position < param.max_position:
                                    now = get_time()
                                    if (now - order_time >= param.wait_time) or order_time == 0:
                                        order_price = bid + param.unit * param.slippage
                                        result = binance.limit_buy_order(param.pair, param.lot, order_price, True)
                                        order_time = get_time()
                                        order_status = binance.binance.fetch_order(id=result["id"], symbol=param.pair)
                                        if order_status["status"] == "open":
                                            binance.limit_sell_order(param.pair, param.lot,
                                                                     (param.target_sell_price(
                                                                         order_price) + param.spread))
                                            order_time = get_time()
                        else:
                            if volume_wam(price_queue, volume_queue) - float(ticker['p']) >= param.delta:
                                if position < param.max_position:
                                    now = get_time()
                                    if (now - order_time >= param.wait_time) or order_time == 0:
                                        order_price = ask - param.unit * param.slippage
                                        result = binance.limit_sell_order(param.pair, param.lot, order_price, True)
                                        order_time = get_time()
                                        order_status = binance.binance.fetch_order(id=result["id"], symbol=param.pair)
                                        if order_status["status"] == "open":
                                            binance.limit_buy_order(param.pair, param.lot,
                                                                    (param.target_buy_price(
                                                                        order_price) - param.spread))
                                            order_time = get_time()

                        price_queue.pop(0)
                        volume_queue.pop(0)
                    volume_wam_avg = volume_wam(price_queue, volume_queue)
                    real_delta = float(ticker['p']) - volume_wam_avg
                    print("=====Volume_WAM:{0}=====".format(round(volume_wam_avg, 5)))
                    if abs(real_delta) < param.delta:
                        if real_delta >= 0:
                            color_print("==========Delta:+{0}=====".format(
                                round((float(ticker['p']) - volume_wam_avg), 5)), pycolor.YELLOW)
                        else:
                            color_print(
                                "==========Delta:{0}=====".format(round((float(ticker['p']) - volume_wam_avg), 5)),
                                pycolor.YELLOW)
                    elif real_delta > 0 and abs(real_delta) >= param.delta:
                        color_print(
                            "==========Delta:+{0}=====".format(round((float(ticker['p']) - volume_wam_avg), 5)),
                            pycolor.GREEN)
                    elif real_delta < 0 and abs(real_delta) >= param.delta:
                        color_print(
                            "==========Delta:{0}=====".format(round((float(ticker['p']) - volume_wam_avg), 5)),
                            pycolor.RED)

                    print("=======Queue Size:{0}=====".format(len(price_queue)))
                else:
                    price_queue = []
                    volume_queue = []

            except Exception:
                # not able to process the data? write it back to the stream_buffer
                binance_websocket_api_manager.add_to_stream_buffer(oldest_stream_data_from_stream_buffer)


def rename_pair(pair: str):
    new_pair = pair.replace("/", "")
    return new_pair.lower()


def main():
    logging.basicConfig(level=logging.DEBUG,
                        filename=os.path.basename(__file__) + '.log',
                        format="{asctime} [{levelname:8}] {process} {thread} {module}: {message}",
                        style="{")

    binance_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com-futures")

    config_open = open("./param.json", "r")
    param_json = json.load(config_open)
    param = robot_param(param_json)
    binance = Binance(api_key=param.api_key, api_secret=param.api_secret)

    worker_thread = threading.Thread(target=robot, args=(binance_websocket_api_manager, binance))
    worker_thread.start()

    print("\r\n=========================== Starting aggTrade ===========================\r\n")

    markets = [rename_pair(param.pair)]

    aggtrade_stream_id = binance_websocket_api_manager.create_stream(["aggTrade", "depth5"], markets)
    time.sleep(7)


if __name__ == '__main__':
    price_queue = []
    volume_queue = []
    wam_avg = 0
    simple_avg = 0
    volume_wam_avg = 0
    position_count = 0
    position = 0
    real_delta = 0
    counter = None
    ticker = None
    order_time = 0
    bid = 0
    ask = 0

    main()
