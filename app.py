from flask import Flask, render_template, request, redirect, send_file
import os

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/cc-remover')
def cc_remover():
    return render_template('cc_remover.html')

@app.route('/converter')
def converter():
    return render_template('converter.html')

@app.route('/profanity-checker')
def profanity_checker():
    return render_template('profanity_checker.html')

if __name__ == '__main__':
    app.run(debug=True)

