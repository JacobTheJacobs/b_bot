import ccxt
import pandas as pd
from binanaceApi import BinanceFuturesClient
import logging
import json
import matplotlib.pyplot as plt
import pprint
from typing import *
import time
from strategies import TechnicalStrategy

logger = logging.getLogger()

# pprint.pprint(binanceC.get_historical_candles("BTCUSDT",'15m'))
pprint.pprint(binanceClient.get_balances())
# pprint.pprint(binanceC.place_order("ETHUSDT","LIMIT",0.01,"SELL",4000,"GTC"))
# pprint.pprint(binanceC.get_order_status("ETHUSDT",5834783425))
# pprint.pprint(binanceC.cancel_order("ETHUSDT"))


