from best3minapp import db
from datetime import datetime


class Indexes(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(500), nullable=False)
    name = db.Column(db.String(500), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    exp_day = db.Column(db.String(3), nullable=False)
    topic = db.Column(db.String(20), nullable=False)
    option_sizing = db.Column(db.Integer, nullable=True)
    exchange = db.Column(db.String(5), nullable=False, default="NFO")
    lot_size = db.Column(db.Integer, default=0, nullable=False)
    token = db.Column(db.Integer, nullable=True)
    enabled = db.Column(db.Boolean, default=False)
    created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Balance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    balance = db.Column(db.Float, default=0, nullable=False)
    when = db.Column(db.String(50), nullable=False)     # FAR / ALL-OPTIONS / AFTER-NEW-ORDER /AFTER-SL
    updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class DciEarnings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Integer, default=0, nullable=False)
    date = db.Column(db.Date, nullable=False)
    earnings = db.Column(db.Float, default=0, nullable=False)
    partial = db.Column(db.Float, default=0, nullable=False)
    status = db.Column(db.String(50), default='NOT-ACHIEVED', nullable=False) # NOT-ACHIEVED / ACHIEVED / PARTIAL
    updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Options(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(1000), nullable=True)
    symbol = db.Column(db.String(500), nullable=False)
    segment = db.Column(db.String(50), nullable=False)
    instrument_type = db.Column(db.String(5), nullable=False)
    active_side = db.Column(db.String(5), nullable=True)
    instrument_token = db.Column(db.Integer, nullable=True)
    exchange_token = db.Column(db.Integer, nullable=True)
    exchange = db.Column(db.String(5), nullable=False, default="NFO")
    in_trade = db.Column(db.Boolean, default=False)
    pause_trade = db.Column(db.Boolean, default=False)
    lot_size = db.Column(db.Integer, default=0, nullable=True)
    strike = db.Column(db.Integer, default=0, nullable=True)
    expiry = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    enabled = db.Column(db.Boolean, default=True)
    ws_remove = db.Column(db.Boolean, default=False)
    atm = db.Column(db.Boolean, default=False)
    order_link_id = db.Column(db.String(100), nullable=True)
    created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class OptionCircuit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(1000), nullable=True)
    upper_circuit = db.Column(db.Integer, default=0, nullable=True)
    lower_circuit = db.Column(db.Integer, default=0, nullable=True)
    created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Orders(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(500), nullable=False)
    index = db.Column(db.String(200), nullable=True)
    token = db.Column(db.Integer, nullable=True)
    order_link_id = db.Column(db.String(100), nullable=True)
    exchange_order_id = db.Column(db.Integer, nullable=False)
    exchange = db.Column(db.String(5), nullable=False, default="NFO")
    is_gtt = db.Column(db.Boolean, default=False)
    recovery_level = db.Column(db.Float, default=0, nullable=False)
    price = db.Column(db.Float, default=0, nullable=False)
    trigger_price = db.Column(db.Float, default=0, nullable=False)
    lot = db.Column(db.Float, default=0, nullable=False)
    quantity = db.Column(db.Float, default=0, nullable=False)
    fees = db.Column(db.Float, default=0, nullable=False)
    fees_need_recovery = db.Column(db.Float, default=0, nullable=False)
    profit = db.Column(db.Float, default=0, nullable=False)
    loss = db.Column(db.Float, default=0, nullable=False)
    loss_need_recovery = db.Column(db.Float, default=0, nullable=False)
    filled_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    side = db.Column(db.String(4), nullable=False)  # BUY / SELL
    type = db.Column(db.String(2), nullable=False)  # PE / CE
    order_type = db.Column(db.String(15), nullable=True)  # TP / SL / MAIN
    balance_before_trade = db.Column(db.Float, default=0, nullable=False)
    balance_after_trade = db.Column(db.Float, default=0, nullable=False)
    is_demo = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(500), nullable=True)  # in-trade / rejected / open / complete / cancelled
    status_reason = db.Column(db.String(1000), nullable=True)
    created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class TradeSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tp_percentage = db.Column(db.Float, default=20, nullable=False)
    sl_percentage = db.Column(db.Float, default=10, nullable=False)
    risk_percentage = db.Column(db.Float, default=1, nullable=False)
    lot = db.Column(db.Integer, default=1, nullable=False)
    demo = db.Column(db.Integer, default=1, nullable=False)
    minimum_balance = db.Column(db.Integer, default=2000, nullable=False)


class TradePnl(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_link_id = db.Column(db.String(100), nullable=True)
    profit = db.Column(db.Float, default=0, nullable=False)
    loss = db.Column(db.Float, default=0, nullable=False)
    fees = db.Column(db.Float, default=0, nullable=False)
    loss_streak = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(25), nullable=False, default='ACHIEVED')  # ACHIEVED


class Loss(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ce_loss = db.Column(db.Float, default=0, nullable=False)
    pe_loss = db.Column(db.Float, default=0, nullable=False)


class LastRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cron = db.Column(db.String(500), nullable=True)  # ALL-OPTIONS / NEAR
    ran_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

