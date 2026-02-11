import threading
import time
from datetime import datetime

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.ticktype import TickTypeEnum

"""
Based off of Roman Paolucci's https://github.com/romanmichaelpaolucci/Quant-Guild-Library/blob/main/2026%20Video%20Lectures/84.%20How%20to%20Build%20a%20Live%20Volatility%20Surface%20in%20Python%20(Interactive%20Brokers)/quant_guild_live_iVol_source_code.py#L119
"""

class GetData(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)

        self.connected_event = threading.Event()
        self.underlying_contract_details_event = threading.Event()
        self.spot_price_event = threading.Event()
        self.chain_resolved = threading.Event()

        self.next_order_id = None

        self.id_map = {}
        self.expirations = []
        self.strikes = []

        self.file = open("data.log", "a")

    def connectAck(self):
        print("connectAck")

    def nextValidId(self, orderId: int):
        print(f"nextValidId: {orderId}")
        self.next_order_id = orderId
        self.connected_event.set()   # API is ready

    def contractDetails(self, reqId, contractDetails):
        self.underlying_conId = contractDetails.contract.conId
        self.underlying_contract_details_event.set()

    def tickPrice(self, reqId, tickType, price, attrib):
        if reqId == 999 and tickType in [68] and price > 0:
            self.spot_price = price
            self.spot_price_event.set()
        elif reqId in self.id_map and tickType in [66, 67, 68] and price > 0:
            exp, strike, right = self.id_map[reqId]
            now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z %z")
            print(f"time: {now}, reqId: {reqId}, tickType: {TickTypeEnum.toStr(tickType)}, price: {price}, attrib: {attrib}, expiry: {exp}, strike: {strike}, right: {right}")
            
    def tickSize(self, reqId, tickType, size):
        tick_types = [
            69, # delayed bid size
            70, # delayed ask size
            71, # delayed last size
                ]
        if tickType in tick_types:
            now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z %z")
            print(f"time: {now}, reqId: {reqId}, tickType: {TickTypeEnum.toStr(tickType)}, size: {size}")
            print(f"time: {now}, reqId: {reqId}, tickType: {TickTypeEnum.toStr(tickType)}, size: {size}, expiry: {exp}, strike: {strike}, right: {right}")


    # Callback receiving the list of strikes and expirations for the asset
    def securityDefinitionOptionParameter(self, reqId, exchange, underlyingConId, tradingClass, multiplier, expirations, strikes):
        self.expirations = sorted(list(expirations))
        self.strikes = sorted(list(strikes))
        self.chain_resolved.set()

    def error(self, reqId, errorCode, errorString, advancedOrderReject=""):
        if reqId in self.id_map:
            exp, strike, right = self.id_map[reqId] 
            print(f"exp: {exp}, strike: {strike}, right: {right}", end = ", ")
        print(
            f"reqId: {reqId}, "
            f"errorCode: {errorCode}, "
            f"errorString: {errorString}, "
            f"orderReject: {advancedOrderReject}"
        )

    def shutdown(self):
        print("Shutting down...")

        try:
            self.cancelMktData(69)
        except:
            pass

        self.disconnect()

        if hasattr(self, "api_thread"):
            self.api_thread.join(timeout=5)

        self.file.flush()
        self.file.close()

        print("Shutdown complete.")

def start_app():
    app = GetData()

    # app.connect("127.0.0.1", 7496, clientId=1)
    app.connect("127.0.0.1", 4002, clientId=1)

    api_thread = threading.Thread(target=app.run, daemon=True)
    api_thread.start()
    app.api_thread = api_thread

    if not app.connected_event.wait(timeout=10):
        raise RuntimeError("IBKR connection timed out")

    app.reqMarketDataType(3)  # Delayed data
    return app

def run_app(app): 
    symbol = "3690"
    exchange = "SEHK"
    currency = "HKD"

    underlying = Contract()
    underlying.symbol = symbol
    underlying.secType = 'STK'
    underlying.exchange = exchange 
    underlying.currency = currency

    app.reqContractDetails(1, underlying)
    if not app.underlying_contract_details_event.wait(timeout=5):
        raise RuntimeError("Contract Details didn't resolve?")
    
    print("Underlying Contract ID", app.underlying_conId)
    app.reqSecDefOptParams(2, symbol, "", "STK", app.underlying_conId)
    if not app.chain_resolved.wait(timeout=5):
        raise RuntimeError("Option Chain didn't resolve?")
     
    app.reqMktData(999, underlying, "", False, False, [])
    if not app.spot_price_event.wait(timeout = 60):
        raise RuntimeError("Could not receive Spot Price")
    spot = app.spot_price
    
    print("Expirations", app.expirations)
    print("Strikes", app.strikes)
    
    today = time.strftime('%Y%m%d')
    # target_exps = [e for e in app.expirations if e >= today][:6]
    target_exps = ["20260330", "20260429"]

    # grab middle 20 strikes
    n = len(app.strikes) # TODO: strikes range from 50 to 320, half way is  185 and no one is trading at 185

    k = 5 # how many strikes away
    # target_strikes = app.strikes[n//2 - k: n//2 + k] 
    target_strikes = [80, 90, 100]

    req_id = 1000
    for exp in target_exps:
        for strike in target_strikes:
            opt = Contract()
            opt.symbol = symbol
            opt.secType = 'OPT'
            opt.exchange = exchange
            opt.currency = currency
            opt.lastTradeDateOrContractMonth = exp
            opt.strike = strike

            right = 'C' if strike >= spot else 'P' # Use Calls for OTM/ITM split based on spot
            opt.right = right
            app.id_map[req_id] = (exp, strike, right)
            app.reqMktData(req_id, opt, "", False, False, [])
            req_id += 1
            time.sleep(0.01) # Avoid rate-limiting the API

    return app

if __name__ == "__main__":
    app_instance = start_app()
    run_app(app_instance)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt received")
        app_instance.shutdown()

