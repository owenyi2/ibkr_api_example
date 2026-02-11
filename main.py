import threading
import time
from datetime import datetime

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.ticktype import TickTypeEnum

from collections import defaultdict
from dataclasses import dataclass

class GetData(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)

        self.connected_event = threading.Event()
        self.next_order_id = None

        self.file = open("data.log", "a")

    def connectAck(self):
        print("connectAck")

    def nextValidId(self, orderId: int):
        print(f"nextValidId: {orderId}")
        self.next_order_id = orderId
        self.connected_event.set()   # API is ready

    def error(self, reqId, errorCode, errorString, advancedOrderReject=""):
        print(
            f"reqId: {reqId}, "
            f"errorCode: {errorCode}, "
            f"errorString: {errorString}, "
            f"orderReject: {advancedOrderReject}"
        )

    # ---- market data ----

    # def tickPrice(self, reqId, tickType, price, attrib):
    #     # Delayed Bid / Ask
    #     if tickType == 66:
    #         self.prices[reqId].bid = price
    #     elif tickType == 67:
    #         self.prices[reqId].ask = price
    
    def tickPrice(self, reqId, tickType, price, attrib):
        tick_types = [
            66, # delayed bid
            67, # delayed ask
            68, # delayed last
                ]
        if tickType in tick_types and price > 0:
            now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z %z")
            print(f"time: {now}, reqId: {reqId}, tickType: {TickTypeEnum.toStr(tickType)}, price: {price}, attrib: {attrib}")
            self.file.write(f"{now}\t{TickTypeEnum.toStr(tickType)}\t{price}\n")
      
    def tickSize(self, reqId, tickType, size):
        tick_types = [
            69, # delayed bid size
            70, # delayed ask size
            71, # delayed last size
                ]
        if tickType in tick_types:
            now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z %z")
            print(f"time: {now}, reqId: {reqId}, tickType: {TickTypeEnum.toStr(tickType)}, size: {size}")
            self.file.write(f"{now}\t{TickTypeEnum.toStr(tickType)}\t{size}\n")
   
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
    ## for experimenting after SEHK closes roughly evening Sydney time
    # c = Contract() 
    # c.symbol = "ULVR"
    # c.secType = "STK"
    # c.exchange = "LSE"
    # c.currency = "GBP"
    
    c = Contract()
    c.symbol = "3690"
    c.secType = "STK"
    c.exchange = "SEHK"
    c.currency = "HKD"
 
    app.reqMktData(
        reqId = 69,
        contract = c,
        genericTickList="",
        snapshot=False,
        regulatorySnapshot=False,
        mktDataOptions=[]
            )

    # symbols = [2800, 3690]

    # for symbol in symbols:
    #     c = Contract()
    #     c.symbol = str(symbol)
    #     c.secType = "STK"
    #     c.exchange = "SEHK"
    #     c.currency = "HKD"

    #     app.reqMktData(
    #         reqId=symbol,
    #         contract=c,
    #         genericTickList="",
    #         snapshot=False,
    #         regulatorySnapshot=False,
    #         mktDataOptions=[]
    #     ) 

    # time.sleep(10)
    # app.disconnect()

if __name__ == "__main__":
    app_instance = start_app()
    run_app(app_instance)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt received")
        app_instance.shutdown()

