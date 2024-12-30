import click
import config
import uuid
from best3min import app, db
import exchange.angel as angel
from best3min.models.model import Options, Orders, Balance, TradeSettings, DciEarnings, TradePnl, Loss, Indexes
import time
import alert.discord as discord
import math
import pandas as pd
from datetime import date, datetime, timedelta
from strategy.ssl import check_high_break, check_low_break
import helper.date_ist as date_ist
import helper.pnl as pnl
import random


def calculate_all_trade_charges(angel_obj, order_params):
    try:
        params = {
            "orders": order_params
        }

        charges = angel_obj.estimateCharges(params)
        return charges['data']['summary']['total_charges']
    except Exception as e:
        print(params)
        alert_msg = f"Estimation API failed"
        print(alert_msg)
        discord.send_alert('cascadeoptions', alert_msg)
        return 0


@click.command(name='check_entry')
def check_entry():
    # angel_obj = angel.get_angel_obj()
    # process_option_trade(angel_obj, index, ce_atm_strike, 'CE')

    # entry_price = 115.5
    # size = 75
    # target = 96110
    # exit_price = 166
    # tp_lots = calculate_lots(size, entry_price, target)
    # tp_price = calculate_tp_price(tp_lots, entry_price,
    #                               previous_loss=target, lot_size=size)
    # pnl = (tp_lots*size*exit_price) - (tp_lots*size*entry_price)
    # print(tp_lots, tp_price, pnl)
    # exit()
    current_datetime = date_ist.ist_time()
    print(current_datetime)

    if current_datetime.time() <= datetime.strptime("22:10", "%H:%M").time():
        index = Indexes.query.filter_by(enabled=True).first()
        in_trade_option = Options.query.filter_by(in_trade=True, name=index.name).filter(
            Options.instrument_type.in_(['PE', 'CE'])).first()
        if not in_trade_option:
            today = date.today()
            order_count = Orders.query.filter_by(order_type="MAIN", status='COMPLETE').filter(
                Orders.created >= datetime.combine(today, datetime.min.time())).count()
            if order_count >= 3:
                return
            print('Fetching options of index: ' + index.name)
            angel_obj = angel.get_angel_obj()
            df_index = angel.get_3min_olhcv(angel_obj, index)

            print(df_index)

            if check_high_break(df_index):
                print('CE Trade')
                atm_strike = round_to_nearest(df_index.iloc[-1]['close'], index.option_sizing)
                process_option_trade(angel_obj, index, atm_strike, 'CE')
                return

            if check_low_break(df_index):
                print('PE Trade')
                atm_strike = round_to_nearest(df_index.iloc[-1]['close'], index.option_sizing)
                process_option_trade(angel_obj, index, atm_strike, 'PE')


def process_option_trade(angel_obj, index, strike, option_type):
    in_trade_option = Options.query.filter_by(in_trade=True, name=index.name).filter(
        Options.instrument_type.in_(['PE', 'CE'])).first()

    if not in_trade_option:
        option = Options.query.filter_by(instrument_type=option_type, strike=strike, name=index.name).first()

        print(option.symbol)
        timeframe = '3m'
        [nse_interval, nse_max_days_per_interval, is_custom_interval] = angel.get_angel_timeframe_details(timeframe)
        olhcv = angel.get_historical_data(angel_obj, option.instrument_token, timeframe, nse_interval, 3, "NFO")

        profile = angel_obj.rmsLimit()['data']
        fund_available = float(profile['utilisedpayout'])

        trade_setting = TradeSettings.query.first()

        orders = Orders.query.filter_by(type=option_type, status='COMPLETE').all()

        total_loss_recovery = sum(order.loss_need_recovery for order in orders)
        total_fees_recovery = sum(order.fees_need_recovery for order in orders)

        # total_loss = (-1 * pnl) + trade_charge + trade_charge
        total_loss = total_loss_recovery + total_fees_recovery

        order_link_id = str(uuid.uuid4())
        option.in_trade = True
        option.active_side = 'BUY'
        option.order_link_id = order_link_id

        # Additional 2%
        total_loss = total_loss + (total_loss * 2 / 100)
        not_achieved_earning = DciEarnings.query.filter_by(status='NOT-ACHIEVED').order_by(DciEarnings.day).first()
        tp = not_achieved_earning.earnings

        partial_achieved_earning = DciEarnings.query.filter_by(status='PARTIAL').order_by(DciEarnings.day).first()
        if partial_achieved_earning:
            tp = tp + partial_achieved_earning.earnings - partial_achieved_earning.partial

        tp_lots = calculate_lots(option.lot_size, olhcv.iloc[-1]['close'], (tp + total_loss))
        approx_fees = 40 + ((tp_lots * option.lot_size * olhcv.iloc[-1]['close']) * 1 / 100)
        tp = tp + total_loss + approx_fees
        tp_lots = calculate_lots(option.lot_size, olhcv.iloc[-1]['close'], tp)

        if trade_setting.demo:
            order_id = generate_random_digit_number(7)
            order_detail = {'status': "complete", 'averageprice': olhcv.iloc[-1]['close']}

        else:
            # enter with buy
            order_id = place_option_order(angel_obj, option.symbol, option.instrument_token,
                                          'MARKET', 'BUY', tp_lots * option.lot_size,
                                          exchange=option.exchange)

            if order_id is None:
                alert_msg = f"Recover Buy order for '{option.symbol}({option.instrument_token})', but order failed, lot = {tp_lots}"
                print(alert_msg)
                discord.send_alert('cascadeoptions', alert_msg)
                return False

            time.sleep(3)

            order_detail = get_order_detail_with_retries(angel_obj, order_id)

            if order_detail is None:
                alert_msg = f"Buy Order created: '{order_id}, Link Id: {option.order_link_id} , but failed to retrieve, manually add it."
                print(alert_msg)
                discord.send_alert('cascadeoptions', alert_msg)

        if order_detail is not None and order_detail['status'] in ["complete"]:
            # Calculate fees
            trade_charge = calculate_trade_charge(angel_obj, option,
                                                  (tp_lots * option.lot_size),
                                                  order_detail['averageprice'], "BUY")

            order = create_order_entry(option, order_id, order_detail['averageprice'], tp_lots,
                                       trade_charge, "BUY", "MAIN", "COMPLETE",
                                       fund_available)

            tp_price = calculate_tp_price(tp_lots, order_detail['averageprice'],
                                          tp=tp, lot_size=option.lot_size)

            tp_order_id = create_tp_order(angel_obj, option, tp_price, tp_lots, 'SELL', trade_setting.demo)

            db.session.commit()

            alert_msg = f"Entering  the trade with buy '{option.symbol}' | Lot: {tp_lots}"
            print(alert_msg)
            discord.send_alert('cascadeoptions', alert_msg)


def create_tp_order(angel_obj, in_trade_option, price, lot, side, is_demo):
    if is_demo:
        tp_order_id = generate_random_digit_number(7)
        order_detail = {'price': price}
    else:
        tp_order_id = place_tp_option_order(angel_obj, in_trade_option.symbol, in_trade_option.instrument_token, 'LIMIT',
                                            'SELL', lot * in_trade_option.lot_size, price,
                                            exchange=in_trade_option.exchange)

        if tp_order_id is None:
            alert_msg = f"TP order creation failed for '{in_trade_option.symbol}({in_trade_option.instrument_token})', lot = {lot}, side={side} | price: {price} | order_link_id: {in_trade_option.order_link_id}"
            print(alert_msg)
            discord.send_alert('cascadeoptions', alert_msg)
            return False

        time.sleep(3)

        order_detail = get_order_detail_with_retries(angel_obj, tp_order_id)

    if order_detail is None:
        alert_msg = f"TP Sell Order created: '{tp_order_id}, Link Id: {in_trade_option.order_link_id} , but failed to retrieve, manually add it."
        print(alert_msg)
        discord.send_alert('cascadeoptions', alert_msg)

    trade_charge = calculate_trade_charge(angel_obj, in_trade_option, (lot * in_trade_option.lot_size),
                                          order_detail['price'], "SELL")

    if order_detail is not None:
        tp_order = Orders(
            symbol=in_trade_option.symbol,
            index=in_trade_option.name,
            token=in_trade_option.instrument_token,
            order_link_id=in_trade_option.order_link_id,
            exchange=in_trade_option.exchange,
            exchange_order_id=tp_order_id,
            price=order_detail['price'],
            lot=lot,
            is_gtt=False,
            quantity=lot * in_trade_option.lot_size,
            fees=trade_charge,
            fees_need_recovery=0,
            side=side,
            type=in_trade_option.instrument_type,
            order_type='TP',
            status='open',
            status_reason=''
        )
        db.session.add(tp_order)
        db.session.commit()
        alert_msg = f"Created LIMIT TP Order '{in_trade_option.symbol}({in_trade_option.instrument_token})' | Lot: {lot}"
        print(alert_msg)
        discord.send_alert('cascadeoptions', alert_msg)
        return tp_order_id
    else:
        alert_msg = f"FAILED LIMIT Order Get: TP order created '{in_trade_option.symbol}({in_trade_option.instrument_token})' | TP Order ID: {tp_order_id}, Lot: {lot} | TP price: {price} | order_link_id: {in_trade_option.order_link_id}"
        print(alert_msg)
        discord.send_alert('cascadeoptions', alert_msg)
        return None


def place_tp_option_order(angel_obj, symbol, token, order_type, side, quantity, price, exchange='NFO'):
    return angel.place_tp_option_order(angel_obj, order_type, symbol, token, side, quantity, price, exchange)


def calculate_lots(per_lot_size, entry_price, target_amount):
    target_price = entry_price + (entry_price * config.TARGET_PERCENTAGE / 100)

    price_difference = target_price - entry_price

    lots_needed = math.ceil(target_amount / price_difference / per_lot_size)

    return lots_needed


def place_option_order(angel_obj, symbol, token, order_type, side, quantity, exchange='NFO'):
    return angel.place_option_order(angel_obj, order_type, symbol, token, side, quantity, exchange)


def get_order_detail_with_retries(angel_obj, order_id, max_retries=3):
    for attempt in range(max_retries + 1):
        order_detail = angel.get_order_detail(angel_obj, order_id)
        if order_detail is not None:
            return order_detail
        if attempt < max_retries:
            angel_obj = angel.get_angel_obj()  # Fetch new angel_obj if more retries are allowed
    return None


def calculate_tp_price(lot, price, tp=0, lot_size=15):
    total_value = lot * lot_size * price
    final_amount = total_value + tp
    percentage_needed = (final_amount - total_value) / total_value * 100
    tp_price = price + (price * percentage_needed / 100)
    return tp_price


def calculate_trade_charge(angel_obj, in_trade_option, qty, price, transaction_type):
    try:
        params = {
            "orders": [
                {
                    "product_type": config.PRODUCT_TYPE,
                    "transaction_type": transaction_type,
                    "quantity": qty,
                    "price": price,
                    "exchange": in_trade_option.exchange,
                    "symbol_name": in_trade_option.name,
                    "token": str(in_trade_option.instrument_token)
                }
            ]
        }

        charges = angel_obj.estimateCharges(params)
        return charges['data']['summary']['total_charges']
    except Exception as e:
        print(params)
        alert_msg = f"Estimation API failed"
        print(alert_msg)
        discord.send_alert('cascadeoptions', alert_msg)
        return 0


def create_order_entry(in_trade_option, exchange_order_id, price, lot, trade_charge, side, type, status,
                       fund_available):
    order = Orders(
        symbol=in_trade_option.symbol,
        token=in_trade_option.instrument_token,
        order_link_id=in_trade_option.order_link_id,
        exchange=in_trade_option.exchange,
        index=in_trade_option.name,
        exchange_order_id=exchange_order_id,
        price=price,
        lot=lot,
        quantity=lot * in_trade_option.lot_size,
        fees=trade_charge,
        fees_need_recovery=trade_charge,
        type=in_trade_option.instrument_type,
        side=side,
        order_type=type,
        balance_before_trade=fund_available,
        status=status
    )
    db.session.add(order)
    db.session.commit()
    return order


@click.command(name='test-entry-process')
def test_entry_process():
    angel_obj = angel.get_angel_obj()
    orders = angel_obj.orderBook()['data']
    order_params = []
    if orders:
        for order in orders:
            if order['status'] == "complete":
                order_param = {
                    "product_type": config.PRODUCT_TYPE,
                    "transaction_type": order['transactiontype'],
                    "quantity": order['quantity'],
                    "price": order['averageprice'],
                    "exchange": order['exchange'],
                    "symbol_name": 'SENSEX',
                    "token": order['symboltoken']
                }
                order_params.append(order_param)

        total_fees = calculate_all_trade_charges(angel_obj, order_params)
        print(total_fees)

    positions = angel_obj.position()['data']
    overall_pnl = 0
    if positions:
        for position in positions:
            overall_pnl = overall_pnl + float(position['realised'])
        print(overall_pnl)
        overall_pnl = overall_pnl - total_fees
        print(overall_pnl)
        exit()

    angel_obj = angel.get_angel_obj()
    print(angel_obj.rmsLimit()['data'])
    profile = angel_obj.rmsLimit()['data']
    fund_available = float(profile['utilisedpayout'])
    print(fund_available)
    exit()
    # sl_order  = Orders.query.filter_by(order_link_id="0836bcd8-aa06-4d34-8062-548fbd0859ab").first()
    # option_type = 'PE'
    # calculate_and_store_pnl(angel_obj, sl_order, option_type)


def generate_random_digit_number(n):
    if n <= 0:
        raise ValueError("Number of digits must be greater than 0")
    lower_bound = 10**(n - 1)  # Smallest n-digit number
    upper_bound = 10**n - 1   # Largest n-digit number
    return random.randint(lower_bound, upper_bound)


def round_to_nearest(number, multiple):
    return round(number / multiple) * multiple


app.cli.add_command(check_entry)
app.cli.add_command(test_entry_process)
