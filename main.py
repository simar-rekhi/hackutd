from flask import Flask, render_template, jsonify, request, redirect, url_for, session
import os

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

@app.route('/')
def home():
    return render_template('Home.html')

@app.route('/index')
def index():
    return render_template('Home.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    return render_template('client/dashboard.html')

@app.route('/callback')
def callback():
    # Auth0 will redirect here after authentication
    return render_template('client/dashboard.html')

if __name__ == "__main__":
    app.run(debug=True)
 