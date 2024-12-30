import pandas_ta as ta
import pandas as pd
import numpy as np
import helper.date_ist as date_ist

ssl_length = 200


def attach_indicators(df):
    df = df[:-1]  # Removed latest candle
    ema_high = ta.ema(df['high'], ssl_length)
    ema_low = ta.ema(df['low'], ssl_length)

    df = pd.concat([df, ema_high, ema_low], axis=1)

    keys = ['open', 'high', 'low', 'close', 'volume', 'timestamp', 'EMA_HIGH', 'EMA_LOW']
    df.columns = keys

    df = df[df['EMA_LOW'].notna()]
    df = df[df['EMA_HIGH'].notna()]

    df["hlv"] = np.where(
        df["close"] > df["EMA_HIGH"], 1, np.where(df["close"] < df["EMA_LOW"], -1, np.NAN)
    )
    df["hlv"] = df["hlv"].ffill()

    return df


def check_high_break(df):
    if df.iloc[-1]['high'] > df.iloc[0]['high']:
        print("The last row's 'high' is greater than the first row's 'high'.")
        return True
    return False


def check_low_break(df):
    if df.iloc[-1]['low'] < df.iloc[0]['low']:
        print("The last row's 'low' is lesser than the first row's 'low'.")
        return True
    return False


def check_ssl_long(df):
    df = attach_indicators(df)
    current = df.iloc[-1]
    previous = df.iloc[-2]

    # Long
    if current['hlv'] > 0 > previous['hlv']:
        print(date_ist.ist_time().strftime('%d-%m-%Y %H:%M:%S') + ": Got Long Signal")
        return True

    print(date_ist.ist_time().strftime('%d-%m-%Y %H:%M:%S') + ": No - Long Signal")
    return False


def check_ssl_short(df):
    df = attach_indicators(df)
    current = df.iloc[-1]
    previous = df.iloc[-2]

    if current['hlv'] < 0 < previous['hlv']:
        print(date_ist.ist_time().strftime('%d-%m-%Y %H:%M:%S') + ": Got Short Signal")
        return True

    print(date_ist.ist_time().strftime('%d-%m-%Y %H:%M:%S') + ": No - Short Signal")
    return False
