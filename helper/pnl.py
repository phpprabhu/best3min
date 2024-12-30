import click
import config
import schedule
from best3minapp import app, db
import exchange.angel as angel
from best3minapp.models.model import Indexes, Options, Orders, OptionCircuit, LastRun, Balance, TradeSettings, TradePnl, Loss, DciEarnings
import time
from datetime import datetime, timedelta, date
import alert.discord as discord
import math
import shutil
import os
import helper.date_ist as date_ist


def calculate_and_store_pnl(angel_obj, order, option_type):
    profile = angel_obj.rmsLimit()['data']
    fund_available = float(profile['utilisedpayout'])
    discord.send_alert('cascadeoptions', f"Fund Available: {fund_available}")
    main_order = Orders.query.filter_by(type=option_type, order_link_id=order.order_link_id,
                                        order_type="MAIN", status='COMPLETE').first()
    main_order.balance_after_trade = fund_available
    pnl = main_order.balance_after_trade - main_order.balance_before_trade
    profit, loss = (pnl, 0) if pnl > 0 else (0, -pnl)
    discord.send_alert('cascadeoptions', f"Profit: {profit} | Loss: {loss}")

    status = 'ACHIEVED' if profit > 0 else 'NOT-ACHIEVED'

    loss_streak = 0
    last_trade_pnl = TradePnl.query.order_by(TradePnl.id.desc()).first()
    if last_trade_pnl:
        loss_streak = last_trade_pnl.loss_streak + 1 if last_trade_pnl.loss > 0 and loss > 0 else 0

    total_loss = Loss.query.first()
    if loss > 0:
        total_loss.total_loss += loss
        discord.send_alert('cascadeoptions', f"Total Loss: {total_loss.total_loss}")
    else:
        earning = profit - total_loss.total_loss
        total_loss.total_loss = max(0, total_loss.total_loss - profit)

        not_achieved_earnings = DciEarnings.query.filter_by(status='NOT-ACHIEVED').order_by(DciEarnings.day).all()

        for not_achieved_earning in not_achieved_earnings:
            remaining_earning = earning + not_achieved_earning.partial - not_achieved_earning.earnings
            if remaining_earning >= 0:
                print('achieved')
                not_achieved_earning.status = 'ACHIEVED'
                discord.send_alert('cascadeoptions', f"Achieved Day: {not_achieved_earning.day}")
                earning = remaining_earning
                continue
            else:
                print('partial')
                not_achieved_earning.partial = earning
                discord.send_alert('cascadeoptions', f"Remaining Earning: {not_achieved_earning.partial}")
                break

    trade_pnl = TradePnl(order_link_id=order.order_link_id, profit=profit, loss=loss, loss_streak=loss_streak, status=status)
    db.session.add(trade_pnl)
    db.session.commit()