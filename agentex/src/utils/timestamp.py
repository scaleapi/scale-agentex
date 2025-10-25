import datetime


def timestamp():
    return datetime.datetime.now().timestamp()


def timestamp_isoformat(timezone=datetime.UTC):
    return datetime.datetime.now(timezone).isoformat()
