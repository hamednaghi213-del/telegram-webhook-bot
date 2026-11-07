"""Transport outcomes which must never be retried automatically."""

UNKNOWN_DELIVERY_PREFIX = "delivery outcome unknown:"


class DeliveryOutcomeUnknown(RuntimeError):
    def __init__(self, detail):
        super().__init__(f"{UNKNOWN_DELIVERY_PREFIX} {detail}")


def delivery_outcome_unknown(error):
    return str(error).startswith(UNKNOWN_DELIVERY_PREFIX)
