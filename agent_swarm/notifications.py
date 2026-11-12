"""Limits for explicit agent notifications (UTC calendar days)."""
COOLDOWN_SECONDS = 5 * 60
DAILY_LIMIT = 6
MAX_TEXT_LENGTH = 1000
LIMIT_MESSAGE = "notification limit reached; send a normal message instead"


class NotificationLimit(ValueError):
    def __init__(self, retry_after: int):
        super().__init__(LIMIT_MESSAGE)
        self.retry_after = retry_after
