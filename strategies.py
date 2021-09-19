import logging
from typing import *
import time
import  pprint

from threading import Timer

import pandas as pd

logger = logging.getLogger()

TF_EQUIV = {"1m": 60, "5m": 300, "15m": 900, "30m": 900, "1h": 3600, "4h": 14400}


class Strategy:
    def __init__(self, client, contract, exchange: str,
                 timeframe: str, balance_pct: float,
                 take_profit: float,
                 stop_loss: float):
        self.client = client
        self.contract = contract
        self.exchange = exchange
        self.tf = timeframe
        self.tf_equiv = TF_EQUIV[timeframe] * 1000
        self.balance_pct = balance_pct
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.ongoing_position = False
        self.candles: List = []
        self.trades: List = []
        self.logs = []

    def _add_log(self, msg: str):
        logger.info("%s", msg)
        self.logs.append({"log": msg, "displayed": False})

    def parse_trades(self, price: float, size: float, timestamp: int) -> str:
        timestamp_diff = int(time.time() * 1000) - timestamp
        if timestamp_diff >= 2000:
            logger.warning("%s %s: %s milliseconds of difference between the current time and the trade time",
                           self.exchange, self.contract, timestamp_diff)
        last_candle = self.candles[-1]
        # Same Candle
        if timestamp < last_candle['Close_time'] + self.tf_equiv:
            last_candle['Close'] = price
            last_candle['Volume'] += size
            if price > last_candle['High']:
                last_candle['High'] = price
            elif price < last_candle['Low']:
                last_candle['Low'] = price
            # Check Take profit / Stop loss
            for trade in self.trades:
                print(self.trades)
                if trade['status'] == "open" and trade['entry_price'] is not None:
                    self._check_tp_sl(trade)

            return "same_candle"

        # Missing Candle(s)

        elif timestamp >= last_candle['Close_time'] + 2 * self.tf_equiv:

            missing_candles = int((timestamp - last_candle['Close_time']) / self.tf_equiv) - 1
            print(missing_candles, "Missing Candle(s) --------------------------------")
            logger.info("%s missing %s candles for %s %s (%s %s)", self.exchange, missing_candles, self.contract,
                        self.tf, timestamp, last_candle['Close_time'])

            for missing in range(missing_candles):
                new_ts = last_candle['Close_time'] + self.tf_equiv
                candle_info = {'ts': new_ts, 'open': last_candle['Close'],
                               'high': last_candle['Close'],
                               'low': last_candle['Close'],
                               'close': last_candle['Close'],
                               'volume': 0}
                new_candle = (candle_info, self.tf, "parse_trade")

                self.candles.append(new_candle)

                last_candle = new_candle

            new_ts = last_candle['Close_time'] + self.tf_equiv
            candle_info = {'ts': new_ts, 'open': price,
                           'high': price, 'low': price, 'close': price,
                           'volume': size}
            new_candle = (candle_info, self.tf, "parse_trade")

            self.candles.append(new_candle)

            return "new_candle"

        # New Candle

        elif timestamp >= last_candle['Close_time'] + self.tf_equiv:
            new_ts = float(last_candle['Close_time']) + self.tf_equiv
            print(new_ts)
            candle_info = {
                'Open': price,
                'High': price,
                'Low': price,
                'Close': price,
                'Volume': size,
                'Close_time': new_ts}
            new_candle = (candle_info)
            self.candles.append(new_candle)
            print(candle_info)
            logger.info("%s New candle for %s %s", self.exchange,
                        self.contract, self.tf)

            return "new_candle"

    def _check_order_status(self, order_id):
        print(order_id)
        order_status = self.client.get_order_status(self.contract, order_id)
        print(order_status)
        if order_status is not None:

            logger.info("%s order status: %s", self.exchange, order_status["status"])

            if order_status['status'] == "filled":
                for trade in self.trades:
                    if trade['orderId'] == order_id:
                        trade['entry_price']= order_status[0]['avgPrice']
                        break
                return

        t = Timer(2.0, lambda: self._check_order_status(order_id))
        t.start()

    def _open_position(self, signal_result: int):

        trade_size = self.client.get_trade_size(self.contract,
                                                self.candles[-1]["Close"],
                                                self.balance_pct)
        if trade_size is None:
            return

        print(signal_result,"signal_result")
        print(trade_size, "trade_size-")

        order_side = "buy" if signal_result == 1 else "sell"

        position_side = "long" if signal_result == 1 else "short"
        print(self.contract, "position_side-")
        self._add_log(f"{position_side.capitalize()} signal on "
                      f"{self.contract} {self.tf}")
        order_status = self.client.place_order(self.contract, "MARKET",
                                               trade_size, order_side)
        print(order_status, "order_status-")
        if order_status is not None:
            self._add_log(f"{order_side.capitalize()} order placed on "
                          f"{self.exchange} | Status: {order_status['status']}")

            self.ongoing_position = True
            print(self.ongoing_position, "self.ongoing_position-")
            avg_fill_price = None

            if order_status['status'] == "FILLED":
                avg_fill_price = order_status['avgPrice']
                print(avg_fill_price, "avg_fill_price-")
            else:
                t = Timer(2.0, lambda: self._check_order_status(order_status['orderId']))
                t.start()

            new_trade = { "time": int(time.time() * 1000),
                          "entry_price": avg_fill_price,
                          "contract": self.contract,
                          "strategy": "RSI+MACD",
                          "side": position_side,
                          "status": "open", "pnl": 0,
                          "quantity": trade_size,
                          "entry_id": order_status['orderId']}
            print(new_trade, "new_trade")
            self.trades.append(new_trade)
            print(self.trades,"tradces")

    def _check_tp_sl(self, trade):

        tp_triggered = False
        sl_triggered = False

        price = self.candles[-1]['Close']
        print(price,'PRICE FOR LAST CANDELE')
        if trade['side'] == "long":
            if self.stop_loss is not None:
                if price <= trade['entry_price'] * (1 - self.stop_loss / 100):
                    sl_triggered = True
            if self.take_profit is not None:
                if price >= trade['entry_price'] * (1 + self.take_profit / 100):
                    tp_triggered = True

        elif trade['side'] == "short":
            if self.stop_loss is not None:
                if price >= trade['entry_price'] * (1 + self.stop_loss / 100):
                    sl_triggered = True
            if self.take_profit is not None:
                if price <= trade['entry_price'] * (1 - self.take_profit / 100):
                    tp_triggered = True

        if tp_triggered or sl_triggered:
            print(tp_triggered, 'tp_triggered')
            print(sl_triggered, 'sl_triggered')
            self._add_log(f"{'Stop loss' if sl_triggered else 'Take profit'} for "
                          f"{self.contract} {self.tf}")

            order_side = "SELL" if trade['side'] == "long" else "BUY"
            order_status = self.client.place_order(self.contract, "MARKET",
                                                   trade['quantity'], order_side)
            print(order_status, 'order_status FOR LAST CANDELE')
            if order_status is not None:
                self._add_log(f"Exit order on {self.contract}"
                              f" {self.tf} placed successfully")
                trade['status'] = "closed"
                self.ongoing_position = False


class TechnicalStrategy(Strategy):
    def __init__(self, client, contract, exchange: str, timeframe: str,
                 balance_pct: float, take_profit: float,
                 stop_loss: float, ema_fast: float,
                 ema_slow: float, ema_signal: float,
                 rsi_length: float):
        super().__init__(client, contract, exchange, timeframe,
                         balance_pct, take_profit, stop_loss)
        self._ema_fast = ema_fast
        self._ema_slow = ema_slow
        self._ema_signal = ema_signal
        self._rsi_length = rsi_length

    def _rsi(self):
        close_list = []
        for candle in self.candles:
            close_list.append(candle['Close'])

        closes = pd.Series(close_list)

        delta = closes.diff().dropna()

        up, down = delta.copy(), delta.copy()
        up[up < 0] = 0
        down[down > 0] = 0

        avg_gain = up.ewm(com=(self._rsi_length - 1), min_periods=self._rsi_length).mean()
        avg_loss = down.abs().ewm(com=(self._rsi_length - 1), min_periods=self._rsi_length).mean()

        rs = avg_gain / avg_loss

        rsi = 100 - 100 / (1 + rs)
        rsi = rsi.round(2)

        return rsi.iloc[-2]

    def _macd(self) -> Tuple[float, float]:

        close_list = []
        for candle in self.candles:
            close_list.append(candle['Close'])

        closes = pd.Series(close_list)

        ema_fast = closes.ewm(span=self._ema_fast).mean()
        ema_slow = closes.ewm(span=self._ema_slow).mean()

        macd_line = ema_fast - ema_slow
        macd_signal = macd_line.ewm(span=self._ema_signal).mean()

        return macd_line.iloc[-2], macd_signal.iloc[-2]

    def _check_signal(self):

        macd_line, macd_signal = self._macd()
        rsi = self._rsi()
       # print(rsi,"RSI")
       # print("-----------------------")
        #print(round(macd_line,2), "macd_line >")
       # print("---------------------------")
       # print(round(macd_signal,2), "macd_signal <")
       # print("---------------------------")
        # if rsi < 30 and macd_line > macd_signal:
        # elif rsi > 70 and macd_line < macd_signal:
        if rsi < 30:
            return 1
        elif rsi > 40:
            return -1
        else:
            return 0

    def check_trade(self, tick_type: str):
        #tick_type=same_candle
        #self.ongoing_position=False

        if tick_type == "new_candle" and not self.ongoing_position:
            signal_result = self._check_signal()

            if signal_result in [1, -1]:
                self._open_position(signal_result)
