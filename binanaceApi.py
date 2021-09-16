import hashlib
import hmac
import threading
import time
import typing
from urllib.parse import urlencode
import websocket
import requests
import logging
import json
import pprint
from strategy import TechnicalStrategy, BreakoutStrategy

logger = logging.getLogger()


class BinanceFuturesClient:
    def __init__(self, public_key: str, secret_key: str, testnet: bool):
        if testnet:
            self._base_url = "https://testnet.binancefuture.com"
            self._wss_url = "wss://stream.binancefuture.com/ws"
        else:
            self._base_url = "https://api.binance.com"
            self._wss_url = "wss://stream.binance.com:9443/ws"
        self._public_key = public_key
        self._secret_key = secret_key
        self._headers = {'X-MBX-APIKEY': self._public_key}
        self.contracts = self.get_contracts()
        self.balances = self.get_balances()
        self.prices = dict()
        self.strategies: typing.Dict[int, typing.Union[TechnicalStrategy, BreakoutStrategy]] = dict()
        self.logs = []

        self._ws_id = 1
        self._ws = None
        t = threading.Thread(target=self._start_ws)
        t.start()
        logger.info("Binance Futures Client successfully initialized")
        print("Binance Futures Client successfully initialized")

    def _add_log(self, msg: str):
        print("%s", msg)
        logger.info("%s", msg)
        self.logs.append({"log": msg, "displayed": False})

    def _generate_signature(self, data: typing.Dict) -> str:
        return hmac.new(self._secret_key.encode(), urlencode(data).encode(), hashlib.sha256).hexdigest()

    def _make_request(self, method: str, endpoint: str, data):
        if method == "GET":
            try:
                response = requests.get(self._base_url + endpoint, params=data, headers=self._headers)
            except Exception as e:
                logger.error("Connection error while making %s request to %s: %s", method, endpoint, e)
                print("Connection error while making %s request to %s: %s", method, endpoint, e)
                return None

        elif method == "POST":
            try:
                response = requests.post(self._base_url + endpoint, params=data, headers=self._headers)
            except Exception as e:
                logger.error("Connection error while making %s request to %s: %s", method, endpoint, e)
                print("Connection error while making %s request to %s: %s", method, endpoint, e)
                return None

        elif method == "DELETE":
            try:
                response = requests.delete(self._base_url + endpoint, params=data, headers=self._headers)
            except Exception as e:
                logger.error("Connection error while making %s request to %s: %s", method, endpoint, e)
                print("Connection error while making %s request to %s: %s", method, endpoint, e)
                return None
        else:
            raise ValueError()

        if response.status_code == 200:
            return response.json()
        else:
            logger.error("Error while making %s request to %s: %s (error code %s)",
                         method, endpoint, response.json(), response.status_code)
            print("Error while making %s request to %s: %s (error code %s)",
                  method, endpoint, response.json(), response.status_code)
            return None

    def get_contracts(self):
        exchange_info = self._make_request("GET", "/api/v3/exchangeInfo", dict())
        contracts = dict()
        if exchange_info is not None:
            for contract_data in exchange_info['symbols']:
                contracts[contract_data['symbol']] = contract_data
            return contracts

    def get_historical_candles(self, symbol, interval: str):
        data = dict()
        data['symbol'] = symbol
        data['interval'] = interval
        data['limit'] = 1000
        raw_candles = self._make_request("GET", "/api/v1/klines", data)
        candels_array = []
        if raw_candles is not None:
            for c in raw_candles:
                candels_array.append({'Open time': c[0],
                                      'Open': float(c[1]),
                                      'High': float(c[2]),
                                      'Low': float(c[3]),
                                      'Close': float(c[4]),
                                      'Volume': float(c[5]),
                                      'Close time': float(c[6]),
                                      'Quote asset volume': float(c[7]),
                                      'Number of trades': float(c[8]),
                                      'Taker buy base asset volume': float(c[9]),
                                      'Taker buy quote asset volume': float(c[10]),
                                      })
        return candels_array

    def get_bid_ask(self, contract):
        data = dict()
        data['symbol'] = contract
        ob_data = self._make_request("GET", "/api/v3/ticker/bookTicker", data)
        if ob_data is not None:
            if contract not in self.prices:
                self.prices[contract] = {'bid': float(ob_data['bidPrice']), 'ask': float(ob_data['askPrice'])}
            else:
                self.prices[contract]['bid'] = float(ob_data['bidPrice'])
                self.prices[contract]['ask'] = float(ob_data['askPrice'])
            return self.prices[contract]

    def get_balances(self):
        data = dict()
        data['timestamp'] = int(time.time() * 1000)
        data['signature'] = self._generate_signature(data)
        balances = dict()  # sapi/v1/margin/isolated/account
        account_data = self._make_request("GET", "/api/v3/account", data)
        if account_data is not None:
            for a in account_data['balances']:
                # balances[a['baseAsset']['asset']] = a['baseAsset']
                if float(a['free']) > 0.0:
                    balances[a['asset']] = (a['free'])
        return balances

    def place_order(self, symbol, side: str,order_type: str, quantity: float,
                    price,
                    tif=None):
        data = dict()
        data['symbol'] = symbol
        data['side'] = side
        data['type'] = order_type
        data['quantity'] = quantity
        if price is not None:
            data['price'] = price
        if tif is not None:
            data['timeInForce'] = tif
        data['timestamp'] = int(time.time() * 1000)
        data['signature'] = self._generate_signature(data)
        order_status = self._make_request("POST", "/api/v3/order", data)
        return order_status

    def cancel_order(self, symbol):
        data = dict()
        data['symbol'] = symbol
        data['timestamp'] = int(time.time() * 1000)
        data['signature'] = self._generate_signature(data)
        order_status = self._make_request("DELETE", "/api/v3/openOrders", data)
        print(order_status)
        return order_status

    def get_order_status(self, symbol, order_id: int):
        data = dict()
        data['timestamp'] = int(time.time() * 1000)
        data['symbol'] = symbol
        data['orderId'] = order_id
        data['signature'] = self._generate_signature(data)
        order_status = self._make_request("GET", "/api/v3/order", data)
        if order_status is not None:
            order_status = order_status
        return order_status


    ########################
    ###### WEBSOCKETS ######
    ########################
    def _start_ws(self):
        self._ws = websocket.WebSocketApp(self._wss_url,
                                          on_open=self._on_open,
                                          on_close=self._on_close,
                                          on_error=self._on_error,
                                          on_message=self._on_message)
        while True:
            try:
                self._ws.run_forever()
            except Exception as e:
                logger.error("Binance error in run_forever() method: %s", e)
                print("Binance error in run_forever() method: %s", e)
            time.sleep(2)

    ##################
    ####   OPEN   ####
    ##################
    def _on_open(self, ws):
        logger.info("Binance connection opened")
        #self.subscribe_channel(list(self.contracts.values()), "bookTicker")
        self.subscribe_channel("ETHUSDT", "bookTicker")
        self.subscribe_channel("ETHUSDT", "aggTrade")

    ##################
    ####   CLOSE  ####
    ##################
    def _on_close(self, ws):
        logger.warning("Binance Websocket connection closed")

    ##################
    ####   ERROR  ####
    ##################
    def _on_error(self, ws, msg: str):
        logger.error("Binance connection error: %s", msg)

    ##################
    ####   MESSG  ####
    ##################
    def _on_message(self, ws, msg: str):
        data = json.loads(msg)
        symbol = data['s']
        if symbol not in self.prices:
            self.prices[symbol] = {'bid': float(data['b']), 'ask': float(data['a'])}
        else:
            self.prices[symbol]['bid'] = float(data['b'])
            self.prices[symbol]['ask'] = float(data['a'])

        print(self.prices[symbol])

    ##################
    ####   CHAN1  ####
    ##################
    def subscribe_channel(self, symbol, channel: str):
        data = dict()
        data['method'] = "SUBSCRIBE"
        data['params'] = []
        data['params'].append(symbol.lower() + "@" + channel)
        data['id'] = self._ws_id
        #for contract in contracts:
            #data['params'].append(symbol.lower() + "@" + channel)
        #data['id'] = self._ws_id

        try:
            self._ws.send(json.dumps(data))
            print(data,type(data))
            print(json.dumps(data),type(json.dumps(data)))
        except Exception as e:
            print("Websocket error while subscribing to %s %s updates: %s", len(symbol), channel, e)
            logger.error("Websocket error while subscribing to %s %s updates: %s", len(symbol), channel, e)

        self._ws_id += 1
