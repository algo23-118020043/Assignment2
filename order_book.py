from bisect import bisect, insort_left
import collections

from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from .order_types import Instrument, Lifespan, Side


MINIMUM_BID = 1
MAXIMUM_ASK = 2 ** 31 - 1
TOP_LEVEL_COUNT = 5


class Order(object):
    """A request to buy or sell at a given price."""
    __slots__ = ("client_order_id", "instrument", "lifespan", "price", "remaining_volume", "side",
                 "total_fees", "volume")

    def __init__(self, client_order_id: int, instrument: Instrument, lifespan: Lifespan, side: Side, price: int,
                 volume: int, listener: Optional[IOrderListener] = None):
        """Initialise a new instance of the Order class."""
        self.client_order_id: int = client_order_id
        self.instrument: Instrument = instrument
        self.lifespan: Lifespan = lifespan
        self.side: Side = side
        self.price: int = price
        self.remaining_volume: int = volume
        self.total_fees: int = 0
        self.volume: int = volume

    def __str__(self):
        """Return a string containing a description of this order object."""
        args = (self.client_order_id, self.instrument, self.lifespan.name, self.side.name, self.price, self.volume,
                self.remaining_volume, self.total_fees)
        s = "{client_order_id=%d, instrument=%s, lifespan=%s, side=%s, price=%d, volume=%d, remaining=%d, "\
            "total_fees=%d}"
        return s % args


class OrderBook(object):
    """A collection of orders arranged by the price-time priority principle."""

    def __init__(self, instrument: Instrument, maker_fee: float, taker_fee: float):
        """Initialise a new instance of the OrderBook class."""
        self.instrument: Instrument = instrument
        self.maker_fee: float = maker_fee
        self.taker_fee: float = taker_fee

        self.__ask_prices: List[int] = []
        self.__ask_ticks: Dict[int, int] = collections.defaultdict(int)
        self.__bid_prices: List[int] = []
        self.__bid_ticks: Dict[int, int] = collections.defaultdict(int)
        self.__last_traded_price: Optional[int] = None
        self.__levels: Dict[int, Deque[Order]] = {}         # 字典，对应价格以及order队列
        self.__total_volumes: Dict[int, int] = {}           # 字典，记录价格对应的所有订单量

        # Signals
        self.trade_occurred: List[Callable[[Any], None]] = list()

    def __str__(self):
        """Return a string representation of this order book."""
        ask_prices = [0] * TOP_LEVEL_COUNT
        ask_volumes = [0] * TOP_LEVEL_COUNT
        bid_prices = [0] * TOP_LEVEL_COUNT
        bid_volumes = [0] * TOP_LEVEL_COUNT
        self.top_levels(ask_prices, ask_volumes, bid_prices, bid_volumes)
        return ("BidVol\tPrice\tAskVol\n"
                + "\n".join("\t%dc\t%6d" % (p, v) for p, v in zip(reversed(ask_prices), reversed(ask_volumes)) if p)
                + "\n" + "\n".join("%6d\t%dc" % (v, p) for p, v in zip(bid_prices, bid_volumes) if p))

    def amend(self, now: float, order: Order, new_volume: int) -> None:
        """
        Amend an order in this order book by decreasing its volume.
        通过减少现有订单量来修改订单（只能减少订单（因为增加订单量涉及排队先后问题））
        如果已经成交的成交量要高于希望修改的新订单量，那我们实际上只能取消该订单
        """
        if order.remaining_volume > 0:
            fill_volume = order.volume - order.remaining_volume
            diff = order.volume - (fill_volume if new_volume < fill_volume else new_volume)
            self.remove_volume_from_level(order.price, diff, order.side)
            order.volume -= diff
            order.remaining_volume -= diff

    def best_ask(self) -> Optional[int]:
        """Return the current best ask price, or None if there are no ask orders."""
        return -self.__ask_prices[-1] if self.__ask_prices else None

    def best_bid(self) -> Optional[int]:
        """Return the current best ask price, or None if there are no ask orders."""
        return self.__bid_prices[-1] if self.__bid_prices else None

    def cancel(self, now: float, order: Order) -> None:
        """
        Cancel an order in this order book.
        取消订单，直接将未成交的全部删除
        """
        if order.remaining_volume > 0:
            self.remove_volume_from_level(order.price, order.remaining_volume, order.side)
            remaining = order.remaining_volume
            order.remaining_volume = 0

    def insert(self, now: float, order: Order) -> None:
        """
        Insert a new order into this order book.
        插入新的订单
        
        如果下单的价格可以直接进行成交，则先进行交易
        如果交易后仍然存在订单量，则将剩余的订单挂单到订单薄上
        """
        if order.side == Side.SELL and self.__bid_prices and order.price <= self.__bid_prices[-1]:
            self.trade_ask(now, order)      # if self.__bid_prices 保证空集情况下不会被处理
        elif order.side == Side.BUY and self.__ask_prices and order.price >= self.__ask_prices[-1]:
            self.trade_bid(now, order)

        if order.remaining_volume > 0:
            if order.lifespan == Lifespan.FILL_AND_KILL:
                remaining = order.remaining_volume
                order.remaining_volume = 0
            else:
                self.place(now, order)

    def last_traded_price(self) -> Optional[int]:
        """Return the last traded price."""
        return self.__last_traded_price

    def midpoint_price(self) -> Optional[float]:
        """Return the midpoint price."""
        if self.__bid_prices and self.__ask_prices:
            return (self.__bid_prices[-1] + -self.__ask_prices[-1]) / 2.0
        return None

    def place(self, now: float, order: Order) -> None:
        """
        Place an order that does not match any existing order in this order book.
        如果订单不能或不能完全与订单薄上现有订单成交 我们则将其place进订单薄中
        同时需要更改orderbook中其它的属性参数
        """
        price = order.price

        if price not in self.__levels:
            self.__levels[price] = collections.deque()
            self.__total_volumes[price] = 0
            if order.side == Side.SELL:
                insort_left(self.__ask_prices, -price)
            else:
                insort_left(self.__bid_prices, price)

        self.__levels[price].append(order)
        self.__total_volumes[price] += order.remaining_volume

    def remove_volume_from_level(self, price: int, volume: int, side: Side) -> None:
        """
        删除某价格的固定数量的订单

        如果要删除的与 orderbook 上剩余数量正好相等，则删除全部对应信息
        如果不相等，则只删除对应数量
        对应的level以及total_volumes统计信息也会删除这一个price段
        """
        if self.__total_volumes[price] == volume:
            del self.__levels[price]
            del self.__total_volumes[price]
            if side == Side.SELL:
                self.__ask_prices.pop(bisect(self.__ask_prices, -price) - 1)
            elif side == Side.BUY:
                self.__bid_prices.pop(bisect(self.__bid_prices, price) - 1)
        else:
            self.__total_volumes[price] -= volume

    def top_levels(self, ask_prices: List[int], ask_volumes: List[int], bid_prices: List[int],
                   bid_volumes: List[int]) -> None:
        """
        Populate the supplied lists with the top levels for this book.
        获取最优 TOP_LEVEL_COUNT 数量的订单报价以及数量
        如果订单薄是稀疏的 只会获取有单的 TOP_LEVEL_COUNT 档订单
        """
        i = 0
        j = len(self.__ask_prices) - 1
        while i < TOP_LEVEL_COUNT and j >= 0:
            ask_prices[i] = -self.__ask_prices[j]
            ask_volumes[i] = self.__total_volumes[ask_prices[i]]
            i += 1
            j -= 1
        while i < TOP_LEVEL_COUNT:
            ask_prices[i] = ask_volumes[i] = 0
            i += 1

        i = 0
        j = len(self.__bid_prices) - 1
        while i < TOP_LEVEL_COUNT and j >= 0:
            bid_prices[i] = self.__bid_prices[j]
            bid_volumes[i] = self.__total_volumes[bid_prices[i]]
            i += 1
            j -= 1
        while i < TOP_LEVEL_COUNT:
            bid_prices[i] = bid_volumes[i] = 0
            i += 1

    def trade_ask(self, now: float, order: Order) -> None:
        """
        Check to see if any existing bid orders match the specified ask order.
        检查是否存在匹配的bid单可以跟新到达的ask单进行交易
        """
        best_bid = self.__bid_prices[-1]

        while order.remaining_volume > 0 and best_bid >= order.price and self.__total_volumes[best_bid] > 0:
            self.trade_level(now, order, best_bid)
            if self.__total_volumes[best_bid] == 0:
                del self.__levels[best_bid]
                del self.__total_volumes[best_bid]
                self.__bid_prices.pop()
                if not self.__bid_prices:   #如果删除后列表为空，则break循环
                    break
                best_bid = self.__bid_prices[-1]    #如果列表不为空，则更新best_bid

    def trade_bid(self, now: float, order: Order) -> None:
        """Check to see if any existing ask orders match the specified bid order."""
        best_ask = -self.__ask_prices[-1]

        while order.remaining_volume > 0 and best_ask <= order.price and self.__total_volumes[best_ask] > 0:
            self.trade_level(now, order, best_ask)
            if self.__total_volumes[best_ask] == 0:
                del self.__levels[best_ask]
                del self.__total_volumes[best_ask]
                self.__ask_prices.pop()
                if not self.__ask_prices:
                    break
                best_ask = -self.__ask_prices[-1]

    def trade_level(self, now: float, order: Order, best_price: int) -> None:
        """
        Match the specified order with existing orders at the given level.
        在特定的level下成交订单
        """
        remaining: int = order.remaining_volume
        order_queue: Deque[Order] = self.__levels[best_price]
        total_volume: int = self.__total_volumes[best_price]

        while remaining > 0 and total_volume > 0:
            while order_queue[0].remaining_volume == 0:
                order_queue.popleft() #把订单列表中已经成交完的订单删除
            passive: Order = order_queue[0]     # 更改 passive 中的属性会一起更改原来的Order实例，代表这是一次浅复制
            volume: int = remaining if remaining < passive.remaining_volume else passive.remaining_volume
            fee: int = round(best_price * volume * self.maker_fee)
            total_volume -= volume
            remaining -= volume
            passive.remaining_volume -= volume
            passive.total_fees += fee

        self.__total_volumes[best_price] = total_volume
        traded_volume_at_this_level: int = order.remaining_volume - remaining

        if order.side == Side.BUY:
            self.__ask_ticks[best_price] += traded_volume_at_this_level
        else:
            self.__bid_ticks[best_price] += traded_volume_at_this_level

        fee: int = round(best_price * traded_volume_at_this_level * self.taker_fee)
        order.remaining_volume = remaining
        order.total_fees += fee

        self.__last_traded_price = best_price
        for callback in self.trade_occurred:
            callback(self)

    def try_trade(self, side: Side, limit_price: int, volume: int) -> Tuple[int, int]:
        """
        Return the volume that would trade and the average price per lot for
        the requested trade without changing the order book.
        在不更改订单簿的情况下返回所请求交易的交易量和每手平均价格。
        """
        total_volume: int = 0
        total_value: int = 0

        if side == Side.ASK:
            i = len(self.__bid_prices) - 1
            while total_volume < volume and i >= 0 and self.__bid_prices[i] and self.__bid_prices[i] >= limit_price:
                price: int = self.__bid_prices[i]
                available: int = self.__total_volumes[price]
                required: int = volume - total_volume
                weight: int = required if required <= available else available
                total_volume += weight
                total_value += weight * price
                i -= 1
        else:
            i = len(self.__ask_prices) - 1
            while total_volume < volume and i >= 0 and -self.__ask_prices[i] and -self.__ask_prices[i] <= limit_price:
                price: int = -self.__ask_prices[i]
                available: int = self.__total_volumes[price]
                required: int = volume - total_volume
                weight: int = required if required <= available else available
                total_volume += weight
                total_value += weight * price
                i -= 1

        return total_volume, total_value // total_volume if total_volume > 0 else 0
