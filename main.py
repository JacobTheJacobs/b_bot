import ccxt
import pandas as pd
from binanaceApi import BinanceFuturesClient
from strategy import TechnicalStrategy,BreakoutStrategy
import logging
import json
import pprint



timeframes = ["1m", "5m", "15m", "30m", "1h", "4h"]

#pprint.pprint(binanceC.get_historical_candles("BTCUSDT",'15m'))
pprint.pprint(binanceC.get_balances())
#pprint.pprint(binanceC.place_order("ETHUSDT","SELL","LIMIT",0.01,4000,"GTC"))
#pprint.pprint(binanceC.get_order_status("ETHUSDT",5834783425))
#pprint.pprint(binanceC.cancel_order("ETHUSDT"))

contract = binanceC.get_contracts()
new_strategy=TechnicalStrategy(binanceC,contract,'Binance',"15m",1,20,20,{
    "ema_fast":2,
    "ema_slow":2,
    "ema_signal":2,
    "rsi_length":14
})