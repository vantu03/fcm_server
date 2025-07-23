# models.py
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Token(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(255), unique=True, nullable=False)

    def __repr__(self):
        return f"<Token {self.token}>"

class FirebaseCredential(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    server_name = db.Column(db.String(50), unique=True, nullable=False)
    json_data = db.Column(db.Text, nullable=False)
