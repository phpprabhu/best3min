import click
import config
import schedule
from best3min import app, db
import exchange.angel as angel
from best3min.models.model import Indexes, Options, Orders, OptionCircuit, LastRun, Balance, TradeSettings, \
    TradePnl, Loss, DciEarnings
import time
from datetime import datetime, timedelta, date
import alert.discord as discord
import math
import shutil
import os
import helper.date_ist as date_ist
import random
import helper.pnl as pnl
from strategy.ssl import check_ssl_long, check_ssl_short

retries = 0


@click.command(name='check_exit')
def check_exit():
    if str(date.today()) in config.HOLIDAYS:
        return False

    current_datetime = date_ist.ist_time()

    if current_datetime.weekday() < 5 and datetime.strptime("09:15",
                                                            "%H:%M").time() <= current_datetime.time() <= datetime.strptime(
            "15:30", "%H:%M").time():
        print('processing orders')
        process_option_orders()
    else:
        print("Market Closed")
        if datetime.strptime("15:31", "%H:%M").time() == current_datetime.time():
            print('EXITING processing orders - Market closed')
            archive_log_directory()
            os.makedirs('log', exist_ok=True)
            exit()


def archive_log_directory():
    if os.path.exists('log'):
        os.makedirs('archive', exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d")
        archive_dir = f"archive/log-{timestamp}"
        if not os.path.exists(archive_dir):
            shutil.move('log', archive_dir)
            print(f"Log directory moved to {archive_dir}")
    else:
        print("Log directory does not exist.")


def process_option_orders():
    global retries
    max_retries = 5
    try:
        process_option_order('CE')
        process_option_order('PE')
        retries = 0
    except Exception as e:
        print(e)
        if "ConnectionTimeout" in str(e) or "Max retries exceeded" in str(e):
            retries += 1
            if retries >= max_retries:
                discord.send_alert('cascadeoptions', 'Connection issue: Max retries exceeded')
        else:
            retries = 0
            discord.send_alert('cascadeoptions', 'Order check process stopped: ' + str(e))


@click.command(name='test-process')
def test_process():
    angel_obj = angel.get_angel_obj()
    print(angel_obj.rmsLimit()['data'])
    profile = angel_obj.rmsLimit()['data']
    fund_available = float(profile['utilisedpayout'])
    print(fund_available)
    exit()
    # sl_order  = Orders.query.filter_by(order_link_id="0836bcd8-aa06-4d34-8062-548fbd0859ab").first()
    # option_type = 'PE'
    # calculate_and_store_pnl(angel_obj, sl_order, option_type)


def process_option_order(option_type):
    in_trade_option = Options.query.filter_by(in_trade=True, instrument_type=option_type).first()

    if in_trade_option:
        angel_obj = angel.get_angel_obj()
        olhcv = angel.get_option_olhcv(in_trade_option.exchange, in_trade_option.instrument_token)
        if in_trade_option.active_side == "BUY":
            tp_order = get_tp_order(in_trade_option, option_type)
            if tp_order is None:
                discord.send_alert('cascadeoptions',
                                   f"There is {option_type} trade without TP order | {in_trade_option.symbol}({in_trade_option.instrument_token}) | order_ink_id: {in_trade_option.order_link_id}")
            else:
                if handle_tp_order(angel_obj, in_trade_option, tp_order, olhcv):
                    return False

            if olhcv.iloc[-1]['low'] < olhcv.iloc[0]['low']:
                if tp_order.is_demo:
                    if tp_order is not None:
                        tp_order.status = "CANCELLED"
                        db.session.commit()
                    discord.send_alert('cascadeoptions',
                                       f"Cancelled TP order | {in_trade_option.symbol}({in_trade_option.instrument_token}) | order_ink_id: {in_trade_option.order_link_id}")

                    order_id = generate_random_digit_number(7)
                    profile = angel_obj.rmsLimit()['data']
                    fund_available = float(profile['utilisedpayout'])

                    buy_exit_order = create_order_entry(in_trade_option, order_id, olhcv.iloc[-1]['close'],
                                                        tp_order.lot,
                                                        0, "SELL", "EXIT", "COMPLETE",
                                                        fund_available)
                    loss_recovered = calculate_buy_trade_pnl(in_trade_option, buy_exit_order)

                    if loss_recovered > 0:
                        mark_recover_fees_and_loss(profit=loss_recovered)

                    in_trade_option.in_trade = False
                    in_trade_option.active_side = None
                    db.session.commit()
                else:
                    tp_order = cancel_tp_order(angel_obj, in_trade_option, option_type)
                    discord.send_alert('cascadeoptions',
                                       f"Cancelled TP gtt order | {in_trade_option.symbol}({in_trade_option.instrument_token}) | order_ink_id: {in_trade_option.order_link_id}")

                    # Enter Close BUY trade
                    order_id = place_option_order(angel_obj, in_trade_option.symbol, in_trade_option.instrument_token,
                                                  'MARKET', 'SELL', tp_order.lot * in_trade_option.lot_size,
                                                  exchange=in_trade_option.exchange)

                    if order_id is None:
                        alert_msg = f"Got signal for '{in_trade_option.symbol}({in_trade_option.instrument_token})', but order failed, lot = {tp_order.lot}"
                        print(alert_msg)
                        discord.send_alert('cascadeoptions', alert_msg)
                        return False

                    time.sleep(3)
                    profile = angel_obj.rmsLimit()['data']
                    fund_available = float(profile['utilisedpayout'])

                    order_detail = get_order_detail_with_retries(angel_obj, order_id)

                    if order_detail is None:
                        alert_msg = f"Exit Buy Order created: '{order_id}, Link Id: {in_trade_option.order_link_id}, but failed to retrieve, manually add it."
                        print(alert_msg)
                        discord.send_alert('cascadeoptions', alert_msg)

                    if order_detail is not None and order_detail['status'] in ["complete"]:
                        # Calculate fees
                        trade_charge = calculate_trade_charge(angel_obj, in_trade_option,
                                                              (tp_order.lot * in_trade_option.lot_size),
                                                              order_detail['averageprice'], "SELL")

                        buy_exit_order = create_order_entry(in_trade_option, order_id, order_detail['averageprice'], tp_order.lot,
                                                   trade_charge, "SELL", "EXIT", "COMPLETE",
                                                   fund_available)
                        loss_recovered = calculate_buy_trade_pnl(in_trade_option, buy_exit_order)

                        if loss_recovered > 0:
                            mark_recover_fees_and_loss(profit=loss_recovered)


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


def calculate_sell_trade_pnl(in_trade_option, exit_order):
    enter_order = Orders.query.filter_by(
        order_link_id=in_trade_option.order_link_id,
        type=in_trade_option.instrument_type,
        status='COMPLETE'
    ).filter(
        Orders.order_type.in_(["MAIN"])
    ).order_by(
        Orders.created.desc()
    ).first()

    pnl = (enter_order.quantity * enter_order.price) - (exit_order.quantity * exit_order.price) - enter_order.fees_need_recovery - exit_order.fees_need_recovery
    pnl_without_fee = (exit_order.quantity * exit_order.price) - (enter_order.quantity * enter_order.price)

    if pnl > 0:
        exit_order.profit = pnl
        exit_order.fees_need_recovery = 0
        enter_order.fees_need_recovery = 0
    else:
        if pnl_without_fee <= 0:
            exit_order.loss_need_recovery = -1 * pnl_without_fee
            exit_order.loss = -1 * pnl_without_fee
        else:
            exit_order.loss_need_recovery = 0
            exit_order.loss = 0

    db.session.commit()
    return pnl


def calculate_buy_trade_pnl(in_trade_option, exit_order):
    enter_order = Orders.query.filter_by(
        order_link_id=in_trade_option.order_link_id,
        type=in_trade_option.instrument_type,
        status='COMPLETE'
    ).filter(
        Orders.order_type.in_(["MAIN"])
    ).order_by(
        Orders.created.desc()
    ).first()

    pnl = (exit_order.quantity * exit_order.price) - (enter_order.quantity * enter_order.price) - enter_order.fees_need_recovery - exit_order.fees_need_recovery
    pnl_without_fee = (exit_order.quantity * exit_order.price) - (enter_order.quantity * enter_order.price)

    if pnl > 0:
        exit_order.profit = pnl
        exit_order.fees_need_recovery = 0
        enter_order.fees_need_recovery = 0
    else:
        if pnl_without_fee <= 0:
            exit_order.loss_need_recovery = -1 * pnl_without_fee
            exit_order.loss = -1 * pnl_without_fee
        else:
            exit_order.loss_need_recovery = 0
            exit_order.loss = 0

    db.session.commit()
    return pnl


def calculate_pnl(in_trade_option):
    all_orders = Orders.query.filter_by(order_link_id=in_trade_option.order_link_id,
                                        type=in_trade_option.instrument_type, status='COMPLETE').all()
    pnl = 0
    for order in all_orders:
        if order.side == "BUY":
            pnl -= (order.quantity * order.price) + order.fees
        else:
            pnl += (order.quantity * order.price) - order.fees
    return pnl


def calculate_lots(per_lot_size, entry_price, target_amount):
    target_price = entry_price + (entry_price * config.TARGET_PERCENTAGE / 100)

    price_difference = target_price - entry_price

    lots_needed = math.ceil(target_amount / price_difference / per_lot_size)

    return lots_needed


def cancel_tp_order(angel_obj, in_trade_option, option_type):
    # Cancel TP GTT order
    tp_order = Orders.query.filter_by(type=option_type, order_link_id=in_trade_option.order_link_id,
                                      side='SELL', order_type='TP', status='open').first()
    if tp_order is not None:
        tp_cancel_order = angel.cancel_order(angel_obj, tp_order.exchange_order_id)
        tp_order.status = "CANCELLED"
        db.session.commit()
        time.sleep(3)

    return tp_order


def handle_tp_order(angel_obj, in_trade_option, tp_order, olhcv):
    if tp_order.is_demo:
        if olhcv.iloc[-1]['high'] > tp_order.price:
            tp_order.status = 'COMPLETE'
            in_trade_option.in_trade = False
            in_trade_option.active_side = None
            db.session.commit()

            profit = get_tp_profit(tp_order)
            mark_recover_fees_and_loss(profit)

            discord.send_alert('cascadeoptions', f"Achieved: '{tp_order.symbol}' | Lot: {tp_order.lot}")
            return True
    else:
        tp_order_detail = get_order_detail_with_retries(angel_obj, tp_order.exchange_order_id)

        if tp_order_detail is None:
            discord.send_alert('cascadeoptions',
                               f"TP order get failing for '{tp_order.symbol}({tp_order.token})', exchange order id = {tp_order.exchange_order_id} | lot = {tp_order.lot} | TP price: {tp_order.price} | order_link_id: {tp_order.order_link_id}")
            return False

        if tp_order_detail['status'] == "complete":
            tp_order.status = 'COMPLETE'
            in_trade_option.in_trade = False
            in_trade_option.active_side = None
            db.session.commit()

            # Calculate fees
            # trade_charge = calculate_trade_charge(angel_obj, in_trade_option, tp_order.quantity,
            #                                       tp_order_detail['averageprice'], "SELL")

            discord.send_alert('cascadeoptions', f"Loss recovered: '{tp_order.symbol}' | Lot: {tp_order.lot}")

            # tp_order.fees = trade_charge
            tp_order.fees_need_recovery = tp_order.fees
            db.session.commit()

            profit = get_tp_profit(tp_order)

            mark_recover_fees_and_loss(profit)

            return True
    return False


def get_tp_profit(tp_order):
    main_order = Orders.query.filter_by(order_link_id=tp_order.order_link_id, type=tp_order.type, order_type='MAIN', status='COMPLETE').order_by(
        Orders.created.desc()).first()
    profit = (tp_order.quantity * tp_order.price) - (main_order.quantity * main_order.price)
    return profit if profit > 0 else 0


def mark_recover_fees_and_loss(profit=0):
    if profit > 0:
        all_exit_orders = Orders.query.filter_by(status='COMPLETE').order_by(
            Orders.created.asc()).all()

        for order in all_exit_orders:
            profit = profit - order.fees_need_recovery
            if profit >= 0:
                order.fees_need_recovery = 0
            else:
                order.fees_need_recovery = profit * -1
                break

            profit = profit - order.loss_need_recovery
            if profit >= 0:
                order.loss_need_recovery = 0
            else:
                order.loss_need_recovery = profit * -1
                break

        db.session.commit()


def get_tp_order(in_trade_option, option_type):
    return Orders.query.filter_by(type=option_type, order_link_id=in_trade_option.order_link_id,
                                  order_type='TP', status='open').first()


def calculate_tp_price(lot, price, previous_loss=0, lot_size=15):
    total_value = lot * lot_size * price
    final_amount = total_value + previous_loss
    percentage_needed = (final_amount - total_value) / total_value * 100
    tp_price = price + (price * percentage_needed / 100)
    return tp_price


def place_option_order(angel_obj, symbol, token, order_type, side, quantity, exchange='NFO'):
    return angel.place_option_order(angel_obj, order_type, symbol, token, side, quantity, exchange)


def place_tp_option_order(angel_obj, symbol, token, order_type, side, quantity, price, exchange='NFO'):
    return angel.place_tp_option_order(angel_obj, order_type, symbol, token, side, quantity, price, exchange)


def create_tp_order(angel_obj, in_trade_option, price, lot, side):
    tp_order_id = place_tp_option_order(angel_obj, in_trade_option.symbol, in_trade_option.instrument_token, 'LIMIT', 'SELL', lot * in_trade_option.lot_size, price,
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


def get_order_detail_with_retries(angel_obj, order_id, max_retries=3):
    for attempt in range(max_retries + 1):
        order_detail = angel.get_order_detail(angel_obj, order_id)
        if order_detail is not None:
            return order_detail
        if attempt < max_retries:
            angel_obj = angel.get_angel_obj()  # Fetch new angel_obj if more retries are allowed
    return None


def generate_random_digit_number(n):
    if n <= 0:
        raise ValueError("Number of digits must be greater than 0")
    lower_bound = 10**(n - 1)  # Smallest n-digit number
    upper_bound = 10**n - 1   # Largest n-digit number
    return random.randint(lower_bound, upper_bound)


app.cli.add_command(check_exit)
app.cli.add_command(test_process)
