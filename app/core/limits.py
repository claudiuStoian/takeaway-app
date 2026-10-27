# These limits are only safe as a set: worst-case order total =
# MAX_LINES_PER_ORDER * MAX_QUANTITY_PER_ITEM * MAX_ITEM_PRICE_CENTS + MAX_DELIVERY_FEE_CENTS
# = 50 * 99 * 100_000 + 10_000 = 495_010_000 cents, below INTEGER's 2_147_483_647.
# Raising any of them means re-checking that sum.

MAX_ITEM_PRICE_CENTS = 100_000
MAX_DELIVERY_FEE_CENTS = 10_000
MAX_QUANTITY_PER_ITEM = 99
MAX_LINES_PER_ORDER = 50
