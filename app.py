# app.py
from flask import Flask, request, render_template, jsonify
from models import db, Token
from config import Config
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, messaging
import os
import json
from dotenv import load_dotenv

# Load từ .env file
load_dotenv()

# Lấy biến môi trường
firebase_cred_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')

app = Flask(__name__)
CORS(app)
app.config.from_object(Config)
db.init_app(app)

# Khởi tạo firebase_admin với file JSON key
cred = credentials.Certificate(json.loads(firebase_cred_json))
firebase_admin.initialize_app(cred)

# Khởi tạo database
with app.app_context():
    db.create_all()

@app.route('/')
def home():
    tokens = [t.token for t in Token.query.all()]
    return render_template('home.html', tokens=tokens)

@app.route('/api/save_token', methods=['POST'])
def api_save_token():
    token = request.json.get('token')
    if not token:
        return jsonify({'success': False, 'message': 'Missing token'}), 400

    if not Token.query.filter_by(token=token).first():
        db.session.add(Token(token=token))
        db.session.commit()
    return jsonify({'success': True}), 200

@app.route('/send', methods=['POST'])
def send():
    title = request.form['title']
    body = request.form['body']
    tokens = [t.token for t in Token.query.all()]

    if not tokens:
        return 'No tokens found!'

    # Gửi từng token bằng messaging.send()
    success_count = 0
    for token in tokens:
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            token=token,
        )
        try:
            response = messaging.send(message)
            print("✅ Sent to:", token, "|", response)
            success_count += 1
        except Exception as e:
            print("❌ Failed to send to:", token, "|", e)

    return f'Đã gửi thành công {success_count}/{len(tokens)} thông báo!'

if __name__ == '__main__':
    app.run(debug=True)
