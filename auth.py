import jwt
import bcrypt
import os
import uuid
import json
import secrets
import hmac
import hashlib
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify, g
from database import get_db_connection

JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET:
    raise RuntimeError('JWT_SECRET must be configured; refusing to start with a default secret.')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRES_HOURS = 24 * 7
AUTH_COOKIE = 'cc_access'
CSRF_COOKIE = 'cc_csrf'
LOGIN_LIMIT = 10
LOGIN_WINDOW_SECONDS = 15 * 60

def _login_limit_key(email: str, ip_address: str) -> str:
    value = f'{ip_address}\0{email.lower()}'
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def is_login_rate_limited(email: str, ip_address: str) -> bool:
    key_hash = _login_limit_key(email, ip_address)
    now = int(time.time())
    conn = get_db_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT attempts, window_started_at FROM auth_login_limits WHERE key_hash = ?', (key_hash,)).fetchone()
        if not row or now - row['window_started_at'] >= LOGIN_WINDOW_SECONDS:
            conn.execute(
                'INSERT INTO auth_login_limits (key_hash, attempts, window_started_at) VALUES (?, 1, ?) '
                'ON CONFLICT(key_hash) DO UPDATE SET attempts = 1, window_started_at = excluded.window_started_at',
                (key_hash, now)
            )
            conn.commit()
            return False
        if row['attempts'] >= LOGIN_LIMIT:
            conn.commit()
            return True
        conn.execute('UPDATE auth_login_limits SET attempts = attempts + 1 WHERE key_hash = ?', (key_hash,))
        conn.commit()
        return False
    finally:
        conn.close()

def clear_login_rate_limit(email: str, ip_address: str) -> None:
    conn = get_db_connection()
    conn.execute('DELETE FROM auth_login_limits WHERE key_hash = ?', (_login_limit_key(email, ip_address),))
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False

def generate_token(user: dict) -> tuple[str, str]:
    csrf_token = secrets.token_urlsafe(32)
    payload = {
        'sub': user['id'],
        'email': user['email'],
        'role': user['role'],
        'name': user['full_name'],
        'department_id': user.get('department_id'),
        'csrf': csrf_token,
        'exp': datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRES_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM), csrf_token

def set_auth_cookies(response, token: str, csrf_token: str):
    max_age = JWT_EXPIRES_HOURS * 60 * 60
    secure = os.environ.get('COOKIE_SECURE', 'true').lower() not in ('0', 'false', 'no')
    response.set_cookie(
        AUTH_COOKIE, token, max_age=max_age, httponly=True, secure=secure,
        samesite='Strict', path='/'
    )
    response.set_cookie(
        CSRF_COOKIE, csrf_token, max_age=max_age, httponly=False, secure=secure,
        samesite='Strict', path='/'
    )
    return response

def get_current_user():
    auth_header = request.headers.get('Authorization', '')
    token = auth_header.split(' ', 1)[1] if auth_header.startswith('Bearer ') else request.cookies.get(AUTH_COOKIE)
    if not token:
        return None

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get('sub')
        conn = get_db_connection()
        user = conn.execute(
            'SELECT id, email, full_name, phone, role, department_id, member_id, active FROM users WHERE id = ?',
            (user_id,)
        ).fetchone()
        conn.close()

        if user and user['active']:
            return dict(user)
    except Exception:
        return None
    return None

def csrf_protect():
    if request.method in ('GET', 'HEAD', 'OPTIONS') or request.headers.get('Authorization', '').startswith('Bearer '):
        return None
    if request.endpoint in ('login', 'register', 'request_password_reset', 'confirm_password_reset'):
        return None

    token = request.cookies.get(AUTH_COOKIE)
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return jsonify({'error': 'Authentication required or session expired'}), 401

    cookie_token = request.cookies.get(CSRF_COOKIE, '')
    header_token = request.headers.get('X-CSRF-Token', '')
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token) or not hmac.compare_digest(payload.get('csrf', ''), cookie_token):
        return jsonify({'error': 'CSRF validation failed'}), 403
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

