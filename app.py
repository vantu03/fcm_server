# app.py
from flask import Flask, request, render_template, jsonify, redirect
from flask_cors import CORS
from models import db, Token, FirebaseCredential
from config import Config
from lichICTU import LichSinhVienICTU
import firebase_admin
from firebase_admin import credentials, messaging
import json

app = Flask(__name__)
CORS(app)
app.config.from_object(Config)
db.init_app(app)

firebase_apps = {}

with app.app_context():
    db.create_all()

def init_firebase_if_needed(server_name):
    if server_name in firebase_apps:
        return firebase_apps[server_name]

    cred_obj = FirebaseCredential.query.filter_by(server_name=server_name).first()
    if not cred_obj:
        raise Exception(f"Không tìm thấy cấu hình Firebase cho server '{server_name}'")

    try:
        cred_dict = json.loads(cred_obj.json_data)
        app_instance = firebase_admin.initialize_app(
            credentials.Certificate(cred_dict),
            name=server_name
        )
        firebase_apps[server_name] = app_instance
        return app_instance
    except Exception as e:
        raise Exception(f"Lỗi khi khởi tạo Firebase cho server '{server_name}': {e}")

@app.route('/', methods=['GET'])
def home():
    firebase_credentials = FirebaseCredential.query.all()
    tokens = [t.token for t in Token.query.all()]
    return render_template('home.html', tokens=tokens, firebase_credentials=firebase_credentials)

@app.route('/upload_firebase', methods=['POST'])
def upload_firebase():
    file = request.files.get('json_file')
    server_name = request.form.get('server_name')

    if not file or not server_name:
        return "Thiếu file hoặc tên server", 400

    content = file.read().decode('utf-8')

    existing = FirebaseCredential.query.filter_by(server_name=server_name).first()
    if existing:
        existing.json_data = content
    else:
        db.session.add(FirebaseCredential(server_name=server_name, json_data=content))

    db.session.commit()
    return jsonify({'success': True})


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
    server_name = request.form.get('server')
    title = request.form.get('title')
    body = request.form.get('body')

    try:
        app_instance = init_firebase_if_needed(server_name)
    except Exception as e:
        return str(e), 500

    tokens = Token.query.all()
    if not tokens:
        return 'No tokens found!'

    success_count = 0
    error_count = 0
    for t in tokens:
        token = t.token
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            token=token,
        )
        try:
            response = messaging.send(message, app=app_instance)
            print("✅ Sent to:", token, "|", response)
            success_count += 1
        except firebase_admin.exceptions.FirebaseError as e:
            print("❌ Firebase error to:", token, "|", e)
            if isinstance(e, messaging.UnregisteredError) or \
               isinstance(e, messaging.InvalidArgumentError):
                print("⚠️ Token invalid. Deleting:", token)
                db.session.delete(t)
                db.session.commit()
            error_count += 1
        except Exception as e:
            print("❌ Unknown error to:", token, "|", e)
            error_count += 1

    return f'\u0110\u00e3 g\u1eedi th\u00e0nh c\u00f4ng {success_count}/{len(tokens)} th\u00f4ng b\u00e1o! ({error_count} l\u1ed7i)'

@app.route('/lichhoc/', methods=['GET'])
def lichhoc_api():
    tk = request.args.get('username')
    mk = request.args.get('password')

    if not tk or not mk:
        return jsonify({'status': 'error', 'message': 'Thiếu tài khoản hoặc mật khẩu'}), 400

    lich = LichSinhVienICTU(tk, mk)
    data = lich.get_schedule()
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True)
