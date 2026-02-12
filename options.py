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
    def __init__(self, symbols = ["3690", "5", "700"]):
        EClient.__init__(self, self)

        self.symbols = symbols

        self.connected_event = threading.Event()
        self.underlying_contract_details_event = threading.Event()
        self.spot_price_event = threading.Event()
        self.chain_resolved = threading.Event()
        
        self.underlying_conId = {} 
        self.underlying_conId_id_map = {}

        self.option_chain_id_map = {}
        self.strikes = {}
        self.expirations = {}
        self.spot_id_map = {}
        self.spot_price = {}

        self.next_order_id = None

        self.option_id_map = {}

        self.file = open("data.log", "a")

    def connectAck(self):
        print("connectAck")

    def nextValidId(self, orderId: int):
        print(f"nextValidId: {orderId}")
        self.next_order_id = orderId
        self.connected_event.set()   # API is ready

    def contractDetails(self, reqId, contractDetails):
        assert reqId in self.underlying_conId_id_map
        symbol = self.underlying_conId_id_map[reqId]

        self.underlying_conId[symbol] = contractDetails.contract.conId

        if self.underlying_conId.keys() == set(self.symbols):
            self.underlying_contract_details_event.set()

    def tickPrice(self, reqId, tickType, price, attrib):
        if reqId in self.spot_id_map and tickType in [68] and price > 0:
            symbol = self.spot_id_map[reqId]
            self.spot_price[symbol] = price

            if self.spot_price.keys() == set(self.symbols):
                self.spot_price_event.set()

        elif reqId in self.option_id_map and tickType in [66, 67, 68] and price > 0:
            symbol, exp, strike, right = self.option_id_map[reqId]
            now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z %z")
            print(f"time: {now}, reqId: {reqId}, tickType: {TickTypeEnum.toStr(tickType)}, price: {price}, attrib: {attrib}, symbol: {symbol}, expiry: {exp}, strike: {strike}, right: {right}")
            
    def tickSize(self, reqId, tickType, size):
        tick_types = [
            69, # delayed bid size
            70, # delayed ask size
            71, # delayed last size
                ]
        if reqId in self.option_id_map and tickType in tick_types:
            symbol, exp, strike, right = self.option_id_map[reqId]
            now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z %z")
            print(f"time: {now}, reqId: {reqId}, tickType: {TickTypeEnum.toStr(tickType)}, size: {size}, symbol: {symbol}, expiry: {exp}, strike: {strike}, right: {right}")


    # Callback receiving the list of strikes and expirations for the asset
    def securityDefinitionOptionParameter(self, reqId, exchange, underlyingConId, tradingClass, multiplier, expirations, strikes):
        assert reqId in self.option_chain_id_map
        symbol = self.option_chain_id_map[reqId] 

        self.expirations[symbol] = sorted(list(expirations))
        self.strikes[symbol] = sorted(list(strikes))

        if self.strikes.keys() == set(self.symbols) and self.expirations.keys() == set(self.symbols):
            self.chain_resolved.set()

    def error(self, reqId, errorCode, errorString, advancedOrderReject=""):
        if reqId in self.option_id_map:
            symbol, exp, strike, right = self.option_id_map[reqId] 
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

    app.connect("127.0.0.1", 7496, clientId=1)
    # app.connect("127.0.0.1", 4002, clientId=1)

    api_thread = threading.Thread(target=app.run, daemon=True)
    api_thread.start()
    app.api_thread = api_thread

    if not app.connected_event.wait(timeout=10):
        raise RuntimeError("IBKR connection timed out")

    app.reqMarketDataType(3)  # Delayed data
    return app

# TODO: it's a bit retarded to have all stocks resolve before proceeding to the next stage. If one stock fails, it might bring the rest down. Better to have independent processes for each stock running in parallel. 

# TODO: also need to store stock prices

def run_app(app):  
    exchange = "SEHK"
    currency = "HKD"
    
    req_id = 1
    
    # GRAB CONTRACT DETAILS
    for symbol in app.symbols:
        underlying = Contract()
        underlying.symbol = symbol
        underlying.secType = 'STK'
        underlying.exchange = exchange 
        underlying.currency = currency

        app.reqContractDetails(req_id, underlying)
        app.underlying_conId_id_map[req_id] = symbol

        req_id += 1

    if not app.underlying_contract_details_event.wait(timeout=5):
        raise RuntimeError("Contract Details didn't resolve?")
    
    print("Contract Details")

    # GRAB OPTION CHAIN 
    for symbol in app.symbols:
        app.reqSecDefOptParams(req_id, symbol, "", "STK", app.underlying_conId[symbol])
        app.option_chain_id_map[req_id] = symbol

        req_id += 1

    if not app.chain_resolved.wait(timeout=5):
        raise RuntimeError("Option Chain didn't resolve?")
    
    print("Option Chain")
   
    # GRAB SPOT PRICES
    for symbol in app.symbols:
        underlying = Contract()
        underlying.symbol = symbol
        underlying.secType = 'STK'
        underlying.exchange = exchange 
        underlying.currency = currency

        app.reqMktData(req_id, underlying, "", False, False, [])
        app.spot_id_map[req_id] = symbol
        req_id += 1
    
    if not app.spot_price_event.wait(timeout = 60):
        raise RuntimeError("Could not receive Spot Price")
    
    print("Spot") 

    # GRAB OPTION PRICES
    today = time.strftime('%Y%m%d')

    for symbol in app.symbols: 
        spot = app.spot_price[symbol]

        target_exps = [e for e in app.expirations[symbol] if e >= today][:6]

        k = 0.1 
        target_strikes = [s for s in app.strikes[symbol] if spot * (1-k) <= s <= spot * (1+k)]

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
                app.option_id_map[req_id] = (symbol, exp, strike, right)
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

