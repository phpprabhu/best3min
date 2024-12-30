from datetime import datetime, timedelta
from SmartApi import SmartConnect
import config
import pandas as pd
import time as timeobj
import sys
import pyotp
import alert.discord as discord
import requests
import json
import math
import dill as pickle
import os
import functools
import time
import helper.date_ist as date_ist


def retry_on_none(max_retries):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries = max_retries
            while retries > 0:
                result = func(*args, **kwargs)
                if result is not None:
                    return result
                else:
                    time.sleep(3)
                    retries -= 1
                    if retries == 0:
                        print(f"Failed after maximum retries in function {func.__name__}.")
                        return None  # Or raise an exception or take any other action
                    else:
                        print(f"Retrying... {retries} attempts left in function {func.__name__}.")
        return wrapper
    return decorator


def get_angel_timeframe_details(timeframe):
    interval = {'3m': 'THREE_MINUTE', '5m': 'FIVE_MINUTE', '10m': 'TEN_MINUTE', '15m': 'FIFTEEN_MINUTE',
                '30m': 'THIRTY_MINUTE', '1h': 'ONE_HOUR', '1d': 'ONE_DAY'}
    max_days_per_interval = {'3m': 90, '5m': 90, '10m': 90, '15m': 180, '30m': 180, '1h': 365, '1d': 2000}

    nse_interval = "ONE_HOUR"
    nse_max_days_per_interval = 365
    is_custom_interval = True
    if timeframe in interval:
        nse_interval = interval[timeframe]
        nse_max_days_per_interval = max_days_per_interval[timeframe]
        is_custom_interval = False

    return [nse_interval, nse_max_days_per_interval, is_custom_interval]


def get_angel_obj():
    angle_file = 'angel_jwt.txt'
    if os.path.exists(angle_file) and os.stat(angle_file).st_size > 0:
        with open('angel_jwt.txt', 'r') as file:
            obj = SmartConnect(api_key=config.SMART_API_KEY)
            jwt_token = file.read()
            obj.setAccessToken(jwt_token[7:])

            response = obj.ltpData("NSE", "SBIN-EQ", "3045")

            if response['message'] == 'Invalid Token':
                return save_return_angel_obj()
            return obj
    else:
        return save_return_angel_obj()


def save_return_angel_obj():
    obj = SmartConnect(api_key=config.SMART_API_KEY)
    data = obj.generateSession(config.ANGEL_BROKING_USERNAME, config.ANGEL_BROKING_MPIN,
                               pyotp.TOTP(config.OPT_token).now())
    refresh_token = data['data']['refreshToken']
    jwt_token = data['data']['jwtToken']

    # fetch the feedtoken
    feedToken = obj.getfeedToken()

    user_profile = obj.getProfile(refresh_token)
    # obj.generateToken(refreshToken)
    with open("angel_refresh.txt", "w") as f:
        f.write(refresh_token)
    with open("angel_jwt.txt", "w") as f:
        f.write(jwt_token)
    return [obj, user_profile]


@retry_on_none(3)
def get_historical_data(angel_obj, token, timeframe, nse_interval, nse_max_days_per_interval, exchange="NSE"):
    OHLC_AGG = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }

    from_date = (datetime.today() - timedelta(days=nse_max_days_per_interval)).strftime("%Y-%m-%d %H:%M")

    try:
        to_date = datetime.utcnow() + timedelta(minutes=330)

        historicParam = {
            "exchange": exchange,
            "symboltoken": token,
            "interval": nse_interval,
            "fromdate": from_date,
            "todate": to_date.strftime("%Y-%m-%d %H:%M")
        }

        print(f"Getting data for [{token}]")

        bars = angel_obj.getCandleData(historicParam)['data']
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        if timeframe == '4h':
            df['timestamp'] = df['timestamp'].astype('datetime64[ns]') + timedelta(hours=5, minutes=30)
            output = df.set_index('timestamp').resample('4H', offset='75m', origin='epoch').agg(OHLC_AGG)
            df = output[output['open'].notna()]

        if timeframe == '2h':
            df['timestamp'] = df['timestamp'].astype('datetime64[ns]') + timedelta(hours=5, minutes=30)
            output = df.set_index('timestamp').resample('2H', offset='75m', origin='epoch').agg(OHLC_AGG)
            df = output[output['open'].notna()]

        return df

    except Exception as e:
        timeobj.sleep(2)
        print(repr(e))
        print("Unexpected error:", sys.exc_info()[0])
        print('Angel Broking timed out.............')


@retry_on_none(3)
def place_option_order(angel_obj, order_type, symbol, token, side, quantity, exchange='NFO'):
    try:
        orderparams = {
            "variety": config.ORDER_VARIETY,
            "tradingsymbol": symbol,
            "symboltoken": token,
            "transactiontype": side,  # BUY / SELL
            "exchange": exchange,  # NSE / BSE
            "ordertype": order_type,  # MARKET / LIMIT
            "producttype": config.PRODUCT_TYPE,
            "duration": "DAY",
            "quantity": quantity
        }

        print(orderparams)

        order_id = angel_obj.placeOrder(orderparams)
        print("The order id is: {}".format(order_id))
        return order_id
    except Exception as e:
        print(e)
        alert_msg = symbol + ": {}, | Order placement failed".format(side)
        print(alert_msg)
        discord.send_alert('cascadeoptions', alert_msg)
        return None


@retry_on_none(3)
def place_tp_option_order(angel_obj, order_type, symbol, token, side, quantity, tp_price, exchange='NFO'):
    try:
        orderparams = {
            "variety": config.ORDER_VARIETY,
            "tradingsymbol": symbol,
            "symboltoken": token,
            "transactiontype": side,  # BUY / SELL
            "exchange": exchange,  # NSE / BSE
            "ordertype": order_type,  # MARKET / LIMIT
            "producttype": config.PRODUCT_TYPE,
            "duration": "DAY",
            "quantity": quantity,
            "price": round_nearest(tp_price, 0.05),
        }

        print(orderparams)

        order_id = angel_obj.placeOrder(orderparams)
        print("The order id is: {}".format(order_id))
        return order_id
    except Exception as e:
        print(e)
        alert_msg = symbol + ": {}, price: {} | Order placement failed".format(side, str(tp_price))
        print(alert_msg)
        discord.send_alert('cascadeoptions', alert_msg)
        return None


@retry_on_none(3)
def place_sl_option_order(angel_obj, order_type, symbol, token, side, quantity, sl_price, exchange='NFO'):
    try:
        orderparams = {
            "variety": "STOPLOSS",
            "tradingsymbol": symbol,
            "symboltoken": token,
            "transactiontype": side,  # BUY / SELL
            "exchange": exchange,  # NSE / BSE
            "ordertype": order_type,  # MARKET / LIMIT
            "producttype": config.PRODUCT_TYPE,
            "duration": "DAY",
            "squareoff": "0",
            "quantity": quantity,
            "stoploss": round_nearest(sl_price, 0.05),
            "triggerprice": round_nearest(sl_price, 0.05) + 0.3,
            "price": round_nearest(sl_price, 0.05),
        }
        print(orderparams)

        order_id = angel_obj.placeOrder(orderparams)
        print("The SL order id is: {}".format(order_id))
        return order_id
    except Exception as e:
        print(e)
        alert_msg = symbol + ": {}, price: {} | SL Order placement failed".format(side, str(sl_price))
        print(alert_msg)
        discord.send_alert('cascadeoptions', alert_msg)
        return None


@retry_on_none(3)
def place_gtt_order(angel_obj, symbol, token, side, quantity, price, exchange='NFO'):
    try:
        order_params = {
            'variety': 'NORMAL',
            "tradingsymbol": symbol,
            "symboltoken": token,
            "transactiontype": side,  # BUY / SELL
            "exchange": exchange,  # NSE / BSE
            "producttype": config.PRODUCT_TYPE,
            "price": round_nearest(price, 0.05),
            "triggerprice": round_nearest(price, 0.05) - 0.3,
            "qty": quantity,
            "disclosedqty": quantity,
            'squareoff': 0,
            'stoploss': 0,
            "timeperiod": 1,
            "duration": "DAY"
        }
        print(order_params)
        rule_id = angel_obj.gttCreateRule(order_params)
        print("The GTT order id is: {}".format(rule_id))
        return rule_id
    except Exception as e:
        print(e)
        alert_msg = symbol + ": {}, price: {} | GTT Order placement failed".format(side, str(price))
        print(alert_msg)
        discord.send_alert('cascadeoptions', alert_msg)
        return None


@retry_on_none(3)
def get_gtt_order(angel_obj, rule_id):
    try:
        response = angel_obj.gttDetails(rule_id)

        # response = {'status': True, 'message': 'SUCCESS', 'errorcode': '', 'data': {'orderid': '220330000443149'}}
        print("The gtt order detail response is: {}".format(response))
        return response['data']
    except Exception as e:
        print("GTT Order detail failed: {}".format(str(e)))
        return None


def cancel_gtt_order(angel_obj, rule_id, token):
    try:
        rule_params = {
            "id": rule_id,
            "symboltoken": token,
            "exchange": "NFO"
        }
        response = angel_obj.gttCancelRule(rule_params)
        print(response)
        # response = {'status': True, 'message': 'SUCCESS', 'errorcode': '', 'data': {'orderid': '220330000443149'}}
        print("The cancel gtt order response is: {}".format(response))
        return True
    except Exception as e:
        print("GTT Order Cancel failed: {}".format(str(e)))
        return False


def cancel_order(angel_obj, order_id, order_type="NORMAL"):
    try:
        response = angel_obj.cancelOrder(order_id, order_type)
        # response = {'status': True, 'message': 'SUCCESS', 'errorcode': '', 'data': {'orderid': '220330000443149'}}
        print("The cancel order response is: {}".format(response))
        return True
    except Exception as e:
        print("Order Cancel failed: {}".format(str(e)))
        return False


def get_order_detail(angel_obj, order_id):
    try:
        response = angel_obj.orderBook()
        # response = {'status': True, 'message': 'SUCCESS', 'errorcode': '', 'data': [{'variety': 'NORMAL', 'ordertype': 'LIMIT', 'producttype': 'DELIVERY', 'duration': 'DAY', 'price': 495.0, 'triggerprice': 0.0, 'quantity': '1', 'disclosedquantity': '0', 'squareoff': 0.0, 'stoploss': 0.0, 'trailingstoploss': 0.0, 'tradingsymbol': 'SBIN-EQ', 'transactiontype': 'BUY', 'exchange': 'NSE', 'symboltoken': '3045', 'ordertag': '', 'instrumenttype': '', 'strikeprice': -1.0, 'optiontype': '', 'expirydate': '', 'lotsize': '1', 'cancelsize': '0', 'averageprice': 0.0, 'filledshares': '0', 'unfilledshares': '1', 'orderid': '220330000471853', 'text': '', 'status': 'open', 'orderstatus': 'open', 'updatetime': '30-Mar-2022 11:16:21', 'exchtime': '30-Mar-2022 11:16:21', 'exchorderupdatetime': '30-Mar-2022 11:16:21', 'fillid': '', 'filltime': '', 'parentorderid': ''}, {'variety': 'NORMAL', 'ordertype': 'LIMIT', 'producttype': 'DELIVERY', 'duration': 'DAY', 'price': 494.0, 'triggerprice': 0.0, 'quantity': '1', 'disclosedquantity': '0', 'squareoff': 0.0, 'stoploss': 0.0, 'trailingstoploss': 0.0, 'tradingsymbol': 'SBIN-EQ', 'transactiontype': 'BUY', 'exchange': 'NSE', 'symboltoken': '3045', 'ordertag': '', 'instrumenttype': '', 'strikeprice': -1.0, 'optiontype': '', 'expirydate': '', 'lotsize': '1', 'cancelsize': '1', 'averageprice': 0.0, 'filledshares': '0', 'unfilledshares': '1', 'orderid': '220330000443149', 'text': '', 'status': 'cancelled', 'orderstatus': 'cancelled', 'updatetime': '30-Mar-2022 11:12:15', 'exchtime': '30-Mar-2022 11:12:15', 'exchorderupdatetime': '30-Mar-2022 11:12:15', 'fillid': '', 'filltime': '', 'parentorderid': ''}]}
        if response['data']:
            for order in response['data']:
                if not order['orderid']:
                    continue
                print(order['orderid'], order_id)
                if int(order['orderid']) != int(order_id):
                    continue

                return order
        else:
            return None
    except Exception as e:
        print("Order Book failed on order detail: {}".format(str(e)))
        return None


@retry_on_none(3)
def get_child_orders(angel_obj, parent_order_id):
    try:
        timeobj.sleep(2)
        response = angel_obj.orderBook()
        child_orders = []
        # response = {'status': True, 'message': 'SUCCESS', 'errorcode': '', 'data': [{'variety': 'NORMAL', 'ordertype': 'LIMIT', 'producttype': 'DELIVERY', 'duration': 'DAY', 'price': 495.0, 'triggerprice': 0.0, 'quantity': '1', 'disclosedquantity': '0', 'squareoff': 0.0, 'stoploss': 0.0, 'trailingstoploss': 0.0, 'tradingsymbol': 'SBIN-EQ', 'transactiontype': 'BUY', 'exchange': 'NSE', 'symboltoken': '3045', 'ordertag': '', 'instrumenttype': '', 'strikeprice': -1.0, 'optiontype': '', 'expirydate': '', 'lotsize': '1', 'cancelsize': '0', 'averageprice': 0.0, 'filledshares': '0', 'unfilledshares': '1', 'orderid': '220330000471853', 'text': '', 'status': 'open', 'orderstatus': 'open', 'updatetime': '30-Mar-2022 11:16:21', 'exchtime': '30-Mar-2022 11:16:21', 'exchorderupdatetime': '30-Mar-2022 11:16:21', 'fillid': '', 'filltime': '', 'parentorderid': ''}, {'variety': 'NORMAL', 'ordertype': 'LIMIT', 'producttype': 'DELIVERY', 'duration': 'DAY', 'price': 494.0, 'triggerprice': 0.0, 'quantity': '1', 'disclosedquantity': '0', 'squareoff': 0.0, 'stoploss': 0.0, 'trailingstoploss': 0.0, 'tradingsymbol': 'SBIN-EQ', 'transactiontype': 'BUY', 'exchange': 'NSE', 'symboltoken': '3045', 'ordertag': '', 'instrumenttype': '', 'strikeprice': -1.0, 'optiontype': '', 'expirydate': '', 'lotsize': '1', 'cancelsize': '1', 'averageprice': 0.0, 'filledshares': '0', 'unfilledshares': '1', 'orderid': '220330000443149', 'text': '', 'status': 'cancelled', 'orderstatus': 'cancelled', 'updatetime': '30-Mar-2022 11:12:15', 'exchtime': '30-Mar-2022 11:12:15', 'exchorderupdatetime': '30-Mar-2022 11:12:15', 'fillid': '', 'filltime': '', 'parentorderid': ''}]}
        if response['data']:
            for order in response['data']:
                if order['parentorderid'] != '' and int(order['parentorderid']) == int(parent_order_id):
                    child_orders.append(order)

            return child_orders
        else:
            return None
    except Exception as e:
        print("Order Book failed: {}".format(str(e)))
        return None


@retry_on_none(3)
def get_order_status(angel_obj, order_id):
    try:
        response = angel_obj.orderBook()
        # response = {'status': True, 'message': 'SUCCESS', 'errorcode': '', 'data': [{'variety': 'NORMAL', 'ordertype': 'LIMIT', 'producttype': 'DELIVERY', 'duration': 'DAY', 'price': 495.0, 'triggerprice': 0.0, 'quantity': '1', 'disclosedquantity': '0', 'squareoff': 0.0, 'stoploss': 0.0, 'trailingstoploss': 0.0, 'tradingsymbol': 'SBIN-EQ', 'transactiontype': 'BUY', 'exchange': 'NSE', 'symboltoken': '3045', 'ordertag': '', 'instrumenttype': '', 'strikeprice': -1.0, 'optiontype': '', 'expirydate': '', 'lotsize': '1', 'cancelsize': '0', 'averageprice': 0.0, 'filledshares': '0', 'unfilledshares': '1', 'orderid': '220330000471853', 'text': '', 'status': 'open', 'orderstatus': 'open', 'updatetime': '30-Mar-2022 11:16:21', 'exchtime': '30-Mar-2022 11:16:21', 'exchorderupdatetime': '30-Mar-2022 11:16:21', 'fillid': '', 'filltime': '', 'parentorderid': ''}, {'variety': 'NORMAL', 'ordertype': 'LIMIT', 'producttype': 'DELIVERY', 'duration': 'DAY', 'price': 494.0, 'triggerprice': 0.0, 'quantity': '1', 'disclosedquantity': '0', 'squareoff': 0.0, 'stoploss': 0.0, 'trailingstoploss': 0.0, 'tradingsymbol': 'SBIN-EQ', 'transactiontype': 'BUY', 'exchange': 'NSE', 'symboltoken': '3045', 'ordertag': '', 'instrumenttype': '', 'strikeprice': -1.0, 'optiontype': '', 'expirydate': '', 'lotsize': '1', 'cancelsize': '1', 'averageprice': 0.0, 'filledshares': '0', 'unfilledshares': '1', 'orderid': '220330000443149', 'text': '', 'status': 'cancelled', 'orderstatus': 'cancelled', 'updatetime': '30-Mar-2022 11:12:15', 'exchtime': '30-Mar-2022 11:12:15', 'exchorderupdatetime': '30-Mar-2022 11:12:15', 'fillid': '', 'filltime': '', 'parentorderid': ''}]}
        if response['data']:
            for order in response['data']:
                if order['orderid'] != str(order_id):
                    continue

                return order['status']
        else:
            return None
    except Exception as e:
        print("Order Book failed: {}".format(str(e)))
        return None


def get_3min_olhcv(angel_obj, index):
    timeframe = '3m'
    [nse_interval, nse_max_days_per_interval, is_custom_interval] = get_angel_timeframe_details(timeframe)
    df_index = get_historical_data(angel_obj, index.token, timeframe, nse_interval, 750)
    df_index['timestamp'] = pd.to_datetime(df_index['timestamp'])
    # Remove the delta for current date
    today = (pd.Timestamp.now() - pd.Timedelta(days=2)).date()
    filtered_df = df_index[df_index['timestamp'].dt.date == today]
    # Remove the first 2 rows
    filtered_df = filtered_df.iloc[2:].reset_index(drop=True)
    return filtered_df


def round_down(x, a):
    return math.floor(x / a) * a


def round_nearest(x, a):
    return round(x / a) * a

