import click
import config
import pandas as pd
import urllib.request
from best3min import app, db
import exchange.angel as angel
from best3min.models.model import Options, LastRun, Balance, Indexes
from datetime import datetime, timedelta, date
import math
import json
import helper.date_ist as date_ist


@click.command(name='fetch_option_token')
def fetch_option_token():
    # if str(date.today()) in config.HOLIDAYS:
    #     exit()

    angel_obj = angel.get_angel_obj()
    timeframe = '3m'
    [nse_interval, nse_max_days_per_interval, is_custom_interval] = angel.get_angel_timeframe_details(timeframe)

    symbol_file = urllib.request.urlopen(
        'https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json')
    symbols = json.load(symbol_file)
    tocken_df = pd.DataFrame.from_dict(symbols)
    # tocken_df['expiry'] = pd.to_datetime(tocken_df['expiry'], format='%d%b%Y', errors='coerce')
    tocken_df['expiry'] = pd.to_datetime(tocken_df['expiry'])
    tocken_df = tocken_df.astype({'strike': float})
    tocken_df['strike'] = tocken_df['strike'] / 100
    tocken_df.sort_values(by='strike', inplace=True)

    df_option_index_data = tocken_df.loc[tocken_df['instrumenttype'] == 'OPTIDX']

    indexes = Indexes.query.filter_by(enabled=True).all()

    for index in indexes:
        print('Fetching options of index: ' + index.name)
        df_stock = angel.get_historical_data(angel_obj, index.token, timeframe, nse_interval, 750)

        index_ltp = round_to_nearest(df_stock.iloc[-1]['close'], index.option_sizing)
        print(index_ltp)

        index_options = df_option_index_data[df_option_index_data['name'] == index.name]

        for i, option_data in index_options.iterrows():
            option_exists = Options.query.filter_by(instrument_token=option_data.token).first()

            if not option_exists:
                if option_data.expiry <= last_wednesday_or_next_month():
                    option = Options(symbol=option_data.symbol, name=option_data['name'],
                                     instrument_token=int(option_data.token),
                                     exchange_token=0,
                                     segment='NFO', instrument_type=option_data.symbol[-2] + option_data.symbol[-1],
                                     lot_size=option_data.lotsize, strike=float(option_data.strike),
                                     expiry=option_data.expiry, exchange=index.exchange)

                    option.atm = False

                    if index_ltp == option.strike and option.instrument_type == 'CE':
                        option.atm = True

                    if index_ltp == option.strike and option.instrument_type == 'PE':
                        option.atm = True

                    db.session.add(option)
    db.session.commit()

    last_run = LastRun.query.filter_by(cron='ALL-OPTIONS').first()
    last_run.ran_date = datetime.now()

    profile = angel_obj.rmsLimit()['data']
    fund_available = float(profile['utilisedpayout'])
    balance = Balance(balance=fund_available, when='ALL-OPTIONS')

    db.session.add(balance)

    db.session.commit()
    print('Options list updated in DB')


@click.command(name='update_near_token')
def update_near_token():
    if str(date.today()) in config.HOLIDAYS:
        exit()

    angel_obj = angel.get_angel_obj()
    timeframe = '3m'
    [nse_interval, nse_max_days_per_interval, is_custom_interval] = angel.get_angel_timeframe_details(timeframe)

    indexes = Indexes.query.filter_by(enabled=True).all()

    current_datetime = datetime.today()

    for index in indexes:
        print('Fetching options of index: ' + index.name)
        df_stock = angel.get_historical_data(angel_obj, index.token, timeframe, nse_interval, 750)

        index_ltp = round_to_nearest(df_stock.iloc[-1]['close'], index.option_sizing)
        print(index_ltp)
        options = Options.query.filter_by(ws_remove=False, name=index.name).all()

        for option in options:
            option.atm = False

            if index_ltp == option.strike and option.instrument_type == 'CE':
                option.atm = True

            if index_ltp == option.strike and option.instrument_type == 'PE':
                option.atm = True

    last_run = LastRun.query.filter_by(cron='NEAR').first()
    last_run.ran_date = datetime.now()

    profile = angel_obj.rmsLimit()['data']
    fund_available = float(profile['utilisedpayout'])
    balance = Balance(balance=fund_available, when='FAR')

    db.session.add(balance)

    db.session.commit()
    print('Options list updated with NEAR in DB')


from datetime import datetime, timedelta


def get_last_wednesday(year, month):
    # Get the last day of the given month
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    last_day_of_month = next_month - timedelta(days=1)

    # Find the last Wednesday
    while last_day_of_month.weekday() != 2:  # 2 represents Wednesday
        last_day_of_month -= timedelta(days=1)

    return last_day_of_month


def last_wednesday_or_next_month():
    today = datetime.today()
    year, month = today.year, today.month

    # Get the last Wednesday of the current month
    last_wednesday = get_last_wednesday(year, month)

    # If today is after the last Wednesday, calculate for the next month
    if today > last_wednesday:
        if month == 12:  # Move to next year if December
            year += 1
            month = 1
        else:
            month += 1
        last_wednesday = get_last_wednesday(year, month)

    return last_wednesday


def next_weekday(weekday_str):
    weekdays = {
        'mon': 0,
        'tue': 1,
        'wed': 2,
        'thu': 3,
        'fri': 4,
        'sat': 5,
        'sun': 6
    }

    today = datetime.today()
    target_weekday = weekdays.get(weekday_str.lower()) + 1
    days_ahead = (
                         target_weekday - today.weekday() + 7) % 7  # Calculate days until next Wednesday (Thursday is represented as 3)

    if days_ahead == 0:  # If today is Thursday, move to the next week
        days_ahead = 7

    next_expiry_day = today + timedelta(days=days_ahead)
    return next_expiry_day


def round_to_nearest(number, multiple):
    return round(number / multiple) * multiple


app.cli.add_command(fetch_option_token)
app.cli.add_command(update_near_token)
