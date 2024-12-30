
import click
from best3min import app, db
import exchange.angel as angel


@click.command(name='fund_check')
def fund_check():
    print("Fund Check")
    angel_obj = angel.get_angel_obj()

    print(angel_obj.rmsLimit()['data'])
    exit()
    profile = angel_obj.rmsLimit()['data']
    fund_available = float(profile['utilisedpayout'])
    print(angel_obj.position())
    print(angel_obj.holding())
    # order_id = angel.place_delivery_order(angel_obj, 'LIMIT', 'IDEA', 14366, 'BUY', 1, 7.05)

    # angel.cancel_order(angel_obj, 230103000560280)
    # print(angel.get_order_status(angel_obj, 230104000014457))
    # print(order_id)


app.cli.add_command(fund_check)
