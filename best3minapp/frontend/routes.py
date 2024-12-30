from best3minapp import app, db
from flask import flash, render_template, url_for, redirect, request, jsonify

import json

@app.route('/')
@app.route('/home')
def home():
    return render_template('frontend/index.html', title="Home")
