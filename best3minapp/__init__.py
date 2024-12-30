from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'WyevSgnSW7'
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///best3min.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Use an application context to configure the engine
with app.app_context():
    engine = db.engine
    engine.pool.size = 5
    engine.pool.max_overflow = 10
    engine.connect_args = {'timeout': 10}


from best3minapp.frontend import routes
import command.create_db
import command.tokens
import command.entry
import command.process


@app.route('/')
def index():
    # Your Flask command logic goes here
    print("Executing Flask command")