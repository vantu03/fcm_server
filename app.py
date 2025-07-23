from flask import Flask, request, render_template, jsonify, redirect
from models import db, Token
from config import Config
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, messaging
import os
import tempfile

app = Flask(__name__)
CORS(app)
app.config.from_object(Config)
db.init_app(app)

# Biến trạng thái
firebase_initialized = False
firebase_app = None
firebase_json_path = os.path.join(tempfile.gettempdir(), 'firebase_temp.json')

# Khởi tạo database nếu chưa có
with app.app_context():
    db.create_all()

@app.route('/', methods=['GET', 'POST'])
def home():
    global firebase_initialized
    if not firebase_initialized:
        return render_template('init_firebase.html')

    tokens = [t.token for t in Token.query.all()]
    return render_template('home.html', tokens=tokens)

@app.route('/init_firebase', methods=['POST'])
def init_firebase():
    global firebase_initialized, firebase_app

    file = request.files.get('json_file')
    if not file:
        return "Thiếu file JSON", 400

    # Xóa file cũ nếu có
    if os.path.exists(firebase_json_path):
        os.remove(firebase_json_path)

    # Lưu file mới
    file.save(firebase_json_path)

    try:
        cred = credentials.Certificate(firebase_json_path)
        firebase_app = firebase_admin.initialize_app(cred)
        firebase_initialized = True
        return redirect('/')
    except Exception as e:
        return f"Lỗi khi khởi tạo Firebase: {e}", 500

@app.route('/reset_firebase', methods=['POST'])
def reset_firebase():
    global firebase_initialized, firebase_app

    try:
        if firebase_app:
            firebase_admin.delete_app(firebase_app)
            firebase_app = None

        if os.path.exists(firebase_json_path):
            os.remove(firebase_json_path)

        firebase_initialized = False
        return redirect('/')
    except Exception as e:
        return f"Lỗi khi reset Firebase: {e}", 500

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
            response = messaging.send(message)
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

    return f'Đã gửi thành công {success_count}/{len(tokens)} thông báo! ({error_count} lỗi)'


if __name__ == '__main__':
    app.run(debug=True)
