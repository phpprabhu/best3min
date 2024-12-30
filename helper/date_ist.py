from datetime import date, datetime, timedelta


def ist_time():
    current_utc_datetime = datetime.utcnow()
    delta = timedelta(hours=5, minutes=30)
    return current_utc_datetime + delta