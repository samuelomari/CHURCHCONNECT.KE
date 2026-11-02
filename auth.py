import jwt
import bcrypt
import os
import uuid
import json
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify, g
from database import get_db_connection

JWT_SECRET = os.environ.get('JWT_SECRET', 'churchconnect_secure_jwt_secret_key_2026_sda_ke')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRES_HOURS = 24 * 7

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False

def generate_token(user: dict) -> str:
    payload = {
        'sub': user['id'],
        'email': user['email'],
        'role': user['role'],
        'name': user['full_name'],
        'department_id': user.get('department_id'),
        'exp': datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRES_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def get_current_user():
    auth_header = request.headers.get('Authorization', '')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None

    token = auth_header.split(' ')[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get('sub')
        conn = get_db_connection()
        user = conn.execute(
            'SELECT id, email, full_name, phone, role, department_id, active FROM users WHERE id = ?',
            (user_id,)
        ).fetchone()
        conn.close()

        if user and user['active']:
            return dict(user)
    except Exception:
        return None
    return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Authentication required or session expired'}), 401
        g.user = user
        return f(*args, **kwargs)
    return decorated_function

def roles_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({'error': 'Authentication required'}), 401
            
            # Universal supervisory role
            if user['role'] == 'CHURCH_ADMIN':
                g.user = user
                return f(*args, **kwargs)

            if user['role'] not in allowed_roles:
                return jsonify({
                    'error': f"Access forbidden: Role '{user['role']}' does not have required permissions"
                }), 403

            g.user = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def create_audit_log(user_id, action, entity, entity_id=None, details=None, ip_address=None):
    try:
        conn = get_db_connection()
        log_id = str(uuid.uuid4())
        details_str = json.dumps(details) if isinstance(details, (dict, list)) else (details or '')
        conn.execute(
            '''INSERT INTO audit_logs (id, user_id, action, entity, entity_id, details, ip_address, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))''',
            (log_id, user_id, action, entity, entity_id, details_str, ip_address or request.remote_addr)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print("Audit log error:", e)

