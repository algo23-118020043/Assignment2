from order_book import Order, OrderBook
from order_types import Instrument, Lifespan, Side
import time

LOB = OrderBook('foo')
"""
SUB juhb B foo 10 450
SUB bpjl B foo 7 500
SUB lpqn B foo 10 1000
SUB jyfu S foo 10 1200
SUB zqcu S foo 15 400
CXL zqcu
"""

LOB.insert( time.time(), Order('juhb', Side.BUY, 10, 450, 'foo') )
print(LOB)
LOB.insert( time.time(), Order('bpjl', Side.BUY, 7, 500, 'foo') )
print(LOB)
LOB.insert( time.time(), Order('lpqn', Side.BUY, 10, 1000, 'foo') )
print(LOB)
LOB.insert( time.time(), Order('jyfu', Side.SELL, 10, 1200, 'foo') )
print(LOB)
LOB.insert( time.time(), Order('zqcu', Side.SELL, 15, 400, 'foo') )
print(LOB)
LOB.cancel( time.time(), Order('zqcu', Side.SELL, 15, 400, 'foo') )
print(LOB)

