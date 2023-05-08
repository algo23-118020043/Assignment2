import enum


class Instrument(enum.IntEnum):
    FUTURE = 0
    ETF = 1


class Side(enum.IntEnum):
    SELL = 0
    BUY = 1
    ASK = SELL
    BID = BUY
    A = SELL
    B = BUY
    S = SELL


class Lifespan(enum.IntEnum):
    FILL_AND_KILL = 0  # Fill and kill orders trade immediately if possible, otherwise they are cancelled
    GOOD_FOR_DAY = 1  # Good for day orders remain in the market until they trade or are explicitly cancelled
    IMMEDIATE_OR_CANCEL = FILL_AND_KILL
    LIMIT_ORDER = GOOD_FOR_DAY
    FAK = FILL_AND_KILL
    GFD = GOOD_FOR_DAY
    F = FILL_AND_KILL
    G = GOOD_FOR_DAY