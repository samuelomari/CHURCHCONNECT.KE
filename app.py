import os
import re
import sqlite3
import uuid
import json
import hashlib
import secrets
import smtplib
import ssl
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from flask import Flask, request, jsonify, render_template, g
from werkzeug.middleware.proxy_fix import ProxyFix
from database import get_db_connection, init_db, generate_verification_code
from auth import (
    hash_password, check_password, generate_token,
    set_auth_cookies, csrf_protect, AUTH_COOKIE, CSRF_COOKIE,
    is_login_rate_limited, clear_login_rate_limit,
    login_required, roles_required, create_audit_log
)

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    raise RuntimeError('SECRET_KEY must be configured; refusing to start with a default secret.')
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)

@app.before_request
def enforce_request_security():
    if not app.testing and os.environ.get('FORCE_HTTPS', 'true').lower() not in ('0', 'false', 'no'):
        if not request.is_secure:
            secure_url = request.url.replace('http://', 'https://', 1)
            return '', 308, {'Location': secure_url}

    if request.path.startswith('/api/') and request.method in ('POST', 'PUT', 'PATCH'):
        if request.mimetype != 'application/json':
            return jsonify({'error': 'Requests must use application/json.'}), 415
        if request.content_length and not isinstance(request.get_json(silent=True), dict):
            return jsonify({'error': 'A JSON object is required.'}), 400
    return csrf_protect()

@app.after_request
def add_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    response.headers.setdefault('Content-Security-Policy', "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; connect-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:")
    if request.is_secure:
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    return response

# Initialize DB on start
init_db()

# Strict Email Regex
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')

def validate_password_strength(pw: str) -> tuple[bool, str]:
    if not isinstance(pw, str) or len(pw) < 12:
        return False, "Password must be at least 12 characters long."
    if not re.search(r'[A-Z]', pw):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r'[a-z]', pw):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r'[0-9]', pw):
        return False, "Password must contain at least one numerical digit."
    return True, ""

# -------------------------------------------------------------
# Frontend Views & Public Digital Receipt Verification
# -------------------------------------------------------------
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'service': 'churchconnect-kenya'}), 200

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/verify-receipt/<receipt_ref>')
def verify_receipt(receipt_ref):
    conn = get_db_connection()
    envelope = conn.execute('''
        SELECT e.*, m.first_name, m.last_name, u.full_name as recorded_by_name
        FROM tithe_offering_envelopes e
        LEFT JOIN members m ON e.member_id = m.id
        LEFT JOIN users u ON e.recorded_by_id = u.id
        WHERE e.receipt_number = ? OR e.verification_code = ?
    ''', (receipt_ref, receipt_ref)).fetchone()

    if not envelope:
        conn.close()
        return jsonify({'valid': False, 'error': 'Receipt reference not found or invalid'}), 404

    items = conn.execute('''
        SELECT ei.amount, fc.name as fund_name, fc.fund_type
        FROM envelope_items ei
        JOIN fund_categories fc ON ei.fund_category_id = fc.id
        WHERE ei.envelope_id = ?
    ''', (envelope['id'],)).fetchall()
    conn.close()

    return jsonify({
        'valid': True,
        'status': envelope['status'],
        'receipt_number': envelope['receipt_number'],
        'verification_code': envelope['verification_code'],
        'transaction_date': envelope['transaction_date'],
        'payment_method': envelope['payment_method'],
        'payment_status': envelope['payment_status'],
        'donor': f"{envelope['first_name']} {envelope['last_name']}" if envelope['first_name'] else (envelope['donor_name'] or 'Church Contributor'),
        'total_amount': envelope['total_amount'],
        'allocations': [dict(it) for it in items],
        'church': 'Seventh-day Adventist Church (Kenya)',
        'authenticity_stamp': 'Digitally verified against ChurchConnect Kenya cryptographic ledger'
    })

# -------------------------------------------------------------
# Authentication & Registration
# -------------------------------------------------------------
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    email = data.get('email', '')
    password = data.get('password', '')
    full_name = data.get('full_name', '')
    phone = data.get('phone', '')
    member_number = data.get('member_number', '').strip()
    department_id = data.get('department_id')

    if not isinstance(email, str) or not isinstance(full_name, str) or not isinstance(phone, str) or not isinstance(password, str):
        return jsonify({'error': 'Email, full name, phone and password must be text.'}), 400
    email = email.strip().lower()
    full_name = full_name.strip()
    phone = phone.strip()
    if not email or not EMAIL_REGEX.fullmatch(email):
        return jsonify({'error': 'A valid email address is required (e.g., name@domain.ke).'}), 400

    is_valid_pw, pw_err = validate_password_strength(password)
    if not is_valid_pw:
        return jsonify({'error': pw_err}), 400

    if not full_name:
        return jsonify({'error': 'Full name is required.'}), 400

    conn = get_db_connection()
    existing = conn.execute('SELECT id FROM users WHERE LOWER(email) = ?', (email,)).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'An account with this email address is already registered. Please sign in.'}), 409

    member_id = 'mem-' + str(uuid.uuid4())[:8]
    names = full_name.split(' ', 1)
    first_name = names[0]
    last_name = names[1] if len(names) > 1 else 'Member'
    assigned_num = f"CCK-{datetime.now().year}-{uuid.uuid4().hex[:8].upper()}"
    valid_department = conn.execute('SELECT 1 FROM departments WHERE id = ?', (department_id,)).fetchone() if department_id else None
    department_id = department_id if valid_department else None

    conn.execute('''
        INSERT INTO members (id, member_number, first_name, last_name, phone, email, gender, status, department_id)
        VALUES (?, ?, ?, ?, ?, ?, 'MALE', 'ACTIVE', ?)
    ''', (member_id, assigned_num, first_name, last_name, phone or None, email, department_id))

    user_id = 'usr-' + str(uuid.uuid4())[:8]
    pw_hash = hash_password(password)

    conn.execute('''
        INSERT INTO users (id, email, password_hash, full_name, phone, role, member_id, department_id, active)
        VALUES (?, ?, ?, ?, ?, 'MEMBER', ?, ?, 1)
    ''', (user_id, email, pw_hash, full_name, phone or None, member_id, department_id or None))

    conn.commit()
    conn.close()

    create_audit_log(user_id, 'MEMBER_REGISTER', 'User', user_id, {'email': email, 'member_id': member_id})

    user_dict = {
        'id': user_id,
        'email': email,
        'full_name': full_name,
        'phone': phone,
        'role': 'MEMBER',
        'member_id': member_id,
        'department_id': department_id
    }
    token, csrf_token = generate_token(user_dict)
    response = jsonify({
        'message': 'Registration successful! Welcome to ChurchConnect Kenya.',
        'user': user_dict
    }), 201
    response = app.make_response(response)
    return set_auth_cookies(response, token, csrf_token)

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    response = jsonify({'message': 'Signed out'})
    secure = os.environ.get('COOKIE_SECURE', 'true').lower() not in ('0', 'false', 'no')
    response.delete_cookie(AUTH_COOKIE, path='/', secure=secure, httponly=True, samesite='Strict')
    response.delete_cookie(CSRF_COOKIE, path='/', secure=secure, httponly=False, samesite='Strict')
    return response

@app.route('/api/auth/password-reset/request', methods=['POST'])
def request_password_reset():
    data = request.get_json() or {}
    email = data.get('email')
    if not isinstance(email, str) or not EMAIL_REGEX.fullmatch(email.strip()):
        return jsonify({'error': 'A valid email address is required.'}), 400
    email = email.strip().lower()
    generic_response = {'message': 'If the account exists, password reset instructions will be sent.'}

    mail_settings = ('SMTP_HOST', 'SMTP_FROM', 'PUBLIC_BASE_URL')
    if not all(os.environ.get(key) for key in mail_settings):
        return jsonify(generic_response), 202

    conn = get_db_connection()
    user = conn.execute('SELECT id FROM users WHERE LOWER(email) = ? AND active = 1', (email,)).fetchone()
    if not user:
        conn.close()
        return jsonify(generic_response), 202

    raw_token = secrets.token_urlsafe(32)
    now = int(time.time())
    conn.execute('DELETE FROM password_reset_tokens WHERE user_id = ?', (user['id'],))
    conn.execute('''
        INSERT INTO password_reset_tokens (id, user_id, token_hash, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (str(uuid.uuid4()), user['id'], hashlib.sha256(raw_token.encode()).hexdigest(), now + 3600, now))
    conn.commit()
    conn.close()

    reset_url = f"{os.environ['PUBLIC_BASE_URL'].rstrip('/')}/?reset_token={raw_token}"
    message = EmailMessage()
    message['Subject'] = 'ChurchConnect password reset'
    message['From'] = os.environ['SMTP_FROM']
    message['To'] = email
    message.set_content(f'Use this one-time link within 60 minutes to reset your password:\n\n{reset_url}\n\nIf you did not request this, ignore this email.')
    try:
        smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        with smtplib.SMTP(os.environ['SMTP_HOST'], smtp_port, timeout=10) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if os.environ.get('SMTP_USER'):
                smtp.login(os.environ['SMTP_USER'], os.environ.get('SMTP_PASSWORD', ''))
            smtp.send_message(message)
    except Exception:
        conn = get_db_connection()
        conn.execute('DELETE FROM password_reset_tokens WHERE token_hash = ?', (hashlib.sha256(raw_token.encode()).hexdigest(),))
        conn.commit()
        conn.close()
    return jsonify(generic_response), 202

@app.route('/api/auth/password-reset/confirm', methods=['POST'])
def confirm_password_reset():
    data = request.get_json() or {}
    raw_token = data.get('token')
    password = data.get('password')
    if not isinstance(raw_token, str) or not isinstance(password, str):
        return jsonify({'error': 'A reset token and new password are required.'}), 400
    valid_password, password_error = validate_password_strength(password)
    if not valid_password:
        return jsonify({'error': password_error}), 400

    now = int(time.time())
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    conn = get_db_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        result = conn.execute('''
            UPDATE password_reset_tokens SET used_at = ?
            WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?
        ''', (now, token_hash, now))
        if result.rowcount != 1:
            conn.rollback()
            return jsonify({'error': 'Reset link is invalid or expired.'}), 400
        reset = conn.execute('SELECT user_id FROM password_reset_tokens WHERE token_hash = ?', (token_hash,)).fetchone()
        conn.execute('UPDATE users SET password_hash = ?, failed_attempts = 0, locked_until = NULL WHERE id = ?', (hash_password(password), reset['user_id']))
        conn.commit()
    finally:
        conn.close()
    return jsonify({'message': 'Password reset successfully. Please sign in.'})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email', '')
    password = data.get('password', '')

    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify({'error': 'Email and password must be text.'}), 400
    email = email.strip().lower()
    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400
    client_ip = request.remote_addr or 'unknown'
    if is_login_rate_limited(email, client_ip):
        return jsonify({'error': 'Too many sign-in attempts. Try again later.'}), 429

    conn = get_db_connection()
    user = conn.execute('''
        SELECT u.id, u.email, u.password_hash, u.full_name, u.phone, u.role, u.department_id,
               u.member_id, u.two_factor_enabled, u.failed_attempts, u.locked_until, u.active,
               d.name as department_name
        FROM users u
        LEFT JOIN departments d ON u.department_id = d.id
        WHERE LOWER(u.email) = ?
    ''', (email,)).fetchone()

    if not user:
        conn.close()
        return jsonify({'error': 'Invalid credentials or account does not exist'}), 401

    if not user['active']:
        conn.close()
        return jsonify({'error': 'Account has been deactivated. Please contact church leadership.'}), 403

    if user['locked_until']:
        locked_time = datetime.strptime(user['locked_until'], '%Y-%m-%d %H:%M:%S')
        if datetime.now() < locked_time:
            remaining_mins = int((locked_time - datetime.now()).total_seconds() / 60) + 1
            conn.close()
            return jsonify({'error': f'Account locked due to multiple failed login attempts. Try again in {remaining_mins} minute(s).'}), 429

    if not check_password(password, user['password_hash']):
        new_attempts = user['failed_attempts'] + 1
        locked_until_str = None
        if new_attempts >= 5:
            locked_until_dt = datetime.now() + timedelta(minutes=15)
            locked_until_str = locked_until_dt.strftime('%Y-%m-%d %H:%M:%S')

        conn.execute('UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?',
                     (new_attempts, locked_until_str, user['id']))
        conn.commit()
        conn.close()

        if new_attempts >= 5:
            return jsonify({'error': 'Account locked for 15 minutes due to 5 consecutive failed attempts.'}), 429
        return jsonify({'error': f'Invalid password. ({5 - new_attempts} attempts remaining before temporary lock)'}), 401

    conn.execute('UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?', (user['id'],))
    conn.commit()
    clear_login_rate_limit(email, client_ip)

    # Auto-generate member record if user has none
    member_id = user['member_id']
    if not member_id:
        member_id = 'mem-' + str(uuid.uuid4())[:8]
        names = user['full_name'].split(' ', 1)
        first_name = names[0]
        last_name = names[1] if len(names) > 1 else 'Member'
        year = datetime.now().year
        count = conn.execute('SELECT COUNT(*) as c FROM members').fetchone()['c']
        member_num = f"SDA-{year}-{str(count + 1).zfill(4)}"
        conn.execute('''
            INSERT INTO members (id, member_number, first_name, last_name, phone, email, gender, status)
            VALUES (?, ?, ?, ?, ?, ?, 'MALE', 'ACTIVE')
        ''', (member_id, member_num, first_name, last_name, user['phone'], user['email']))
        conn.execute('UPDATE users SET member_id = ? WHERE id = ?', (member_id, user['id']))
        conn.commit()

    conn.close()

    user_dict = dict(user)
    user_dict['member_id'] = member_id  # ensure auto-generated id is in token
    del user_dict['password_hash']
    del user_dict['failed_attempts']
    del user_dict['locked_until']

    token, csrf_token = generate_token(user_dict)
    create_audit_log(user['id'], 'LOGIN', 'User', user['id'], {'email': user['email'], 'role': user['role']})

    response = jsonify({
        'user': user_dict
    })
    return set_auth_cookies(response, token, csrf_token)

@app.route('/api/auth/me', methods=['GET'])
@login_required
def get_me():
    conn = get_db_connection()
    user = conn.execute('''
        SELECT u.id, u.email, u.full_name, u.phone, u.role, u.department_id, u.member_id,
               u.two_factor_enabled, u.active, d.name as department_name
        FROM users u
        LEFT JOIN departments d ON u.department_id = d.id
        WHERE u.id = ?
    ''', (g.user['id'],)).fetchone()
    conn.close()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    return jsonify(dict(user))

# -------------------------------------------------------------
# Church Accountability Centre & Metrics
# -------------------------------------------------------------
@app.route('/api/accountability/summary', methods=['GET'])
@login_required
@roles_required('PASTOR', 'FIRST_ELDER', 'HEAD_TREASURER', 'AUDITOR', 'AUTHORIZED_ELDER_READONLY', 'CHURCH_ADMIN')
def get_accountability_summary():
    conn = get_db_connection()

    # 1. Transactions recorded by officer
    trans_by_officer = conn.execute('''
        SELECT u.full_name, u.role, COUNT(e.id) as receipts_count, COALESCE(SUM(e.total_amount), 0) as total_collected
        FROM tithe_offering_envelopes e
        JOIN users u ON e.recorded_by_id = u.id
        WHERE e.status = 'CONFIRMED'
        GROUP BY u.id
    ''').fetchall()

    # 2. Reversals and corrections history
    reversals = conn.execute('''
        SELECT r.*, e.receipt_number, u.full_name as reversed_by_name
        FROM financial_reversals r
        JOIN tithe_offering_envelopes e ON r.envelope_id = e.id
        JOIN users u ON r.reversed_by_id = u.id
        ORDER BY r.created_at DESC LIMIT 10
    ''').fetchall()

    # 3. Budget warnings (> 80% utilization)
    depts = conn.execute('''
        SELECT name, code, budget_allocation, budget_spent,
               ROUND((budget_spent / budget_allocation) * 100, 1) as pct_used
        FROM departments
        WHERE budget_allocation > 0 AND (budget_spent / budget_allocation) >= 0.8
        ORDER BY pct_used DESC
    ''').fetchall()

    # 4. Expenditure Approvals Log
    decisions = conn.execute('''
        SELECT ad.*, v.voucher_number, v.title as voucher_title, v.amount, u.full_name as voter_name, u.role as voter_role
        FROM approval_decisions ad
        JOIN expenditure_vouchers v ON ad.voucher_id = v.id
        JOIN users u ON ad.user_id = u.id
        ORDER BY ad.created_at DESC LIMIT 10
    ''').fetchall()

    # 5. Pending Vouchers
    pending_vouchers = conn.execute('''
        SELECT v.*, d.name as department_name, req.full_name as requested_by_name
        FROM expenditure_vouchers v
        JOIN departments d ON v.department_id = d.id
        JOIN users req ON v.requested_by_id = req.id
        WHERE v.status IN ('SUBMITTED', 'TREASURER_REVIEWED', 'IN_COMMITTEE_REVIEW')
        ORDER BY v.created_at DESC
    ''').fetchall()

    conn.close()

    return jsonify({
        'transactions_by_officer': [dict(t) for t in trans_by_officer],
        'reversals_history': [dict(r) for r in reversals],
        'budget_warnings': [dict(d) for d in depts],
        'recent_approval_decisions': [dict(dec) for dec in decisions],
        'pending_vouchers': [dict(v) for v in pending_vouchers]
    })

# -------------------------------------------------------------
# Treasury: Envelopes, Receipts & Reversals
# -------------------------------------------------------------
@app.route('/api/finance/fund-categories', methods=['GET'])
@login_required
def get_fund_categories():
    conn = get_db_connection()
    categories = conn.execute('''
        SELECT * FROM fund_categories WHERE active = 1 ORDER BY fund_type ASC, name ASC
    ''').fetchall()
    conn.close()
    return jsonify([dict(c) for c in categories])

@app.route('/api/finance/envelopes', methods=['GET'])
@login_required
@roles_required('HEAD_TREASURER', 'ASSISTANT_TREASURER', 'PASTOR', 'FIRST_ELDER', 'AUDITOR', 'AUTHORIZED_ELDER_READONLY')
def get_envelopes():
    conn = get_db_connection()
    envelopes = conn.execute('''
        SELECT e.*, m.member_number, m.first_name, m.last_name, u.full_name as recorded_by_name
        FROM tithe_offering_envelopes e
        LEFT JOIN members m ON e.member_id = m.id
        LEFT JOIN users u ON e.recorded_by_id = u.id
        ORDER BY e.transaction_date DESC LIMIT 100
    ''').fetchall()

    result = []
    for env in envelopes:
        e_dict = dict(env)
        items = conn.execute('''
            SELECT ei.*, fc.name as fund_name, fc.code as fund_code, fc.fund_type
            FROM envelope_items ei
            JOIN fund_categories fc ON ei.fund_category_id = fc.id
            WHERE ei.envelope_id = ?
        ''', (e_dict['id'],)).fetchall()
        e_dict['items'] = [dict(it) for it in items]
        result.append(e_dict)

    conn.close()
    return jsonify(result)

@app.route('/api/finance/envelopes', methods=['POST'])
@login_required
@roles_required('HEAD_TREASURER', 'ASSISTANT_TREASURER', 'PASTOR', 'FIRST_ELDER')
def create_envelope():
    data = request.get_json() or {}
    items = data.get('items', [])
    member_id = data.get('member_id')
    donor_name = data.get('donor_name')
    donor_phone = data.get('donor_phone')
    payment_method = data.get('payment_method', 'CASH')
    mpesa_ref = data.get('mpesa_receipt_number')
    notes = data.get('notes')

    if not items:
        return jsonify({'error': 'At least one fund item is required in the envelope'}), 400

    total_amount = sum(float(i.get('amount', 0)) for i in items)
    if total_amount <= 0:
        return jsonify({'error': 'Envelope total must be greater than zero'}), 400

    conn = get_db_connection()
    year = datetime.now().year
    count = conn.execute('SELECT COUNT(*) as c FROM tithe_offering_envelopes').fetchone()['c']
    receipt_num = f"REC-{year}-{str(count + 1).zfill(5)}"
    envelope_id = 'env-' + str(uuid.uuid4())[:8]
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    v_code = generate_verification_code(receipt_num, total_amount, now_str)
    payment_status = 'VERIFIED_PROVIDER' if mpesa_ref else 'RECORDED'

    conn.execute('''
        INSERT INTO tithe_offering_envelopes (
            id, receipt_number, verification_code, member_id, donor_name, donor_phone,
            payment_method, payment_status, mpesa_receipt_number, transaction_date, total_amount,
            status, notes, recorded_by_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'CONFIRMED', ?, ?)
    ''', (envelope_id, receipt_num, v_code, member_id, donor_name, donor_phone, payment_method, payment_status, mpesa_ref, now_str, total_amount, notes, g.user['id']))

    for it in items:
        cat_id = it.get('fund_category_id')
        amt = float(it.get('amount', 0))
        if amt > 0:
            conn.execute('''
                INSERT INTO envelope_items (id, envelope_id, fund_category_id, amount)
                VALUES (?, ?, ?, ?)
            ''', (str(uuid.uuid4()), envelope_id, cat_id, amt))

    conn.commit()
    conn.close()

    create_audit_log(g.user['id'], 'RECORD_OFFERING_ENVELOPE', 'TitheOfferingEnvelope', envelope_id, {
        'receipt_number': receipt_num,
        'verification_code': v_code,
        'total_amount': total_amount,
        'payment_method': payment_method
    })

    return jsonify({
        'id': envelope_id,
        'receipt_number': receipt_num,
        'verification_code': v_code,
        'total_amount': total_amount,
        'payment_method': payment_method
    }), 201

# Reversal Transaction (Integrity: Never delete posted transactions)
@app.route('/api/finance/envelopes/<id>/reverse', methods=['POST'])
@login_required
@roles_required('HEAD_TREASURER', 'PASTOR', 'FIRST_ELDER')
def reverse_envelope(id):
    data = request.get_json() or {}
    reason = data.get('reason', '').strip()

    if not reason:
        return jsonify({'error': 'A detailed explanation reason is required to reverse a posted transaction'}), 400

    conn = get_db_connection()
    envelope = conn.execute('SELECT * FROM tithe_offering_envelopes WHERE id = ?', (id,)).fetchone()

    if not envelope:
        conn.close()
        return jsonify({'error': 'Envelope record not found'}), 404

    if envelope['status'] == 'REVERSED':
        conn.close()
        return jsonify({'error': 'Transaction has already been reversed'}), 400

    rev_id = 'rev-' + str(uuid.uuid4())[:8]
    conn.execute('''
        INSERT INTO financial_reversals (id, envelope_id, reversal_reason, reversed_by_id, original_amount)
        VALUES (?, ?, ?, ?, ?)
    ''', (rev_id, id, reason, g.user['id'], envelope['total_amount']))

    conn.execute("UPDATE tithe_offering_envelopes SET status = 'REVERSED', payment_status = 'REVERSED' WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    create_audit_log(g.user['id'], 'REVERSE_FINANCIAL_TRANSACTION', 'TitheOfferingEnvelope', id, {
        'receipt_number': envelope['receipt_number'],
        'reason': reason,
        'amount': envelope['total_amount']
    })

    return jsonify({'message': f"Receipt {envelope['receipt_number']} reversed with auditable trace.", 'reversal_id': rev_id})

# -------------------------------------------------------------
# Configurable Committee Approvals & Vouchers
# -------------------------------------------------------------
@app.route('/api/finance/approval-committees', methods=['GET'])
@login_required
def get_approval_committees():
    conn = get_db_connection()
    committees = conn.execute('SELECT * FROM approval_committees WHERE active = 1').fetchall()
    result = []
    for c in committees:
        c_dict = dict(c)
        mems = conn.execute('''
            SELECT cm.role_in_committee, u.id as user_id, u.full_name, u.role
            FROM approval_committee_members cm
            JOIN users u ON cm.user_id = u.id
            WHERE cm.committee_id = ?
        ''', (c['id'],)).fetchall()
        c_dict['members'] = [dict(m) for m in mems]
        result.append(c_dict)
    conn.close()
    return jsonify(result)

@app.route('/api/finance/vouchers', methods=['GET'])
@login_required
def get_vouchers():
    allowed_roles = {'HEAD_TREASURER', 'ASSISTANT_TREASURER', 'PASTOR', 'FIRST_ELDER', 'DEPARTMENT_LEADER', 'AUDITOR', 'AUTHORIZED_ELDER_READONLY'}
    if g.user['role'] not in allowed_roles and not (g.user['role'] == 'MEMBER' and g.user.get('department_id')):
        return jsonify({
            'error': f"Access forbidden: Role '{g.user['role']}' does not have required permissions"
        }), 403

    dept_id = request.args.get('department_id')
    status = request.args.get('status')

    restricted_dept = None
    if g.user['role'] in ('DEPARTMENT_LEADER', 'MEMBER'):
        restricted_dept = g.user.get('department_id')
        if not restricted_dept:
            return jsonify([])

    conn = get_db_connection()
    query = '''
        SELECT v.*, d.name as department_name, d.code as department_code, d.budget_allocation, d.budget_spent,
               req.full_name as requested_by_name,
               trev.full_name as treasurer_name,
               eld.full_name as elder_name
        FROM expenditure_vouchers v
        JOIN departments d ON v.department_id = d.id
        JOIN users req ON v.requested_by_id = req.id
        LEFT JOIN users trev ON v.treasurer_reviewed_by_id = trev.id
        LEFT JOIN users eld ON v.elder_approved_by_id = eld.id
        WHERE 1=1
    '''
    params = []

    target_dept = restricted_dept if restricted_dept else dept_id
    if target_dept:
        query += ' AND v.department_id = ?'
        params.append(target_dept)

    if status:
        query += ' AND v.status = ?'
        params.append(status)

    query += ' ORDER BY v.created_at DESC'
    vouchers = conn.execute(query, params).fetchall()

    result = []
    for v in vouchers:
        v_dict = dict(v)
        decisions = conn.execute('''
            SELECT ad.*, u.full_name as voter_name, u.role as voter_role
            FROM approval_decisions ad
            JOIN users u ON ad.user_id = u.id
            WHERE ad.voucher_id = ?
        ''', (v_dict['id'],)).fetchall()
        v_dict['committee_decisions'] = [dict(d) for d in decisions]
        result.append(v_dict)

    conn.close()
    return jsonify(result)

@app.route('/api/finance/vouchers', methods=['POST'])
@login_required
@roles_required('DEPARTMENT_LEADER', 'HEAD_TREASURER', 'PASTOR', 'FIRST_ELDER')
def create_voucher():
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    dept_id = data.get('department_id')
    amount = float(data.get('amount', 0))
    payee_name = data.get('payee_name', '').strip()
    payee_phone = data.get('payee_phone', '').strip()
    payment_method = data.get('payment_method', 'MPESA')

    if not title or not description or not dept_id or amount <= 0 or not payee_name:
        return jsonify({'error': 'Missing required voucher requisition fields'}), 400

    conn = get_db_connection()
    dept = conn.execute('SELECT * FROM departments WHERE id = ?', (dept_id,)).fetchone()
    if not dept:
        conn.close()
        return jsonify({'error': 'Department not found'}), 404

    remaining = dept['budget_allocation'] - dept['budget_spent']
    if amount > remaining:
        conn.close()
        return jsonify({
            'error': f"Insufficient department budget. Requested: KES {amount:,.2f}, Remaining: KES {max(0, remaining):,.2f}"
        }), 400

    year = datetime.now().year
    count = conn.execute('SELECT COUNT(*) as c FROM expenditure_vouchers').fetchone()['c']
    vou_num = f"VOU-{year}-{str(count + 1).zfill(4)}"
    vou_id = 'vou-' + str(uuid.uuid4())[:8]

    conn.execute('''
        INSERT INTO expenditure_vouchers (
            id, voucher_number, title, description, department_id, requested_by_id,
            amount, payee_name, payee_phone, payment_method, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SUBMITTED')
    ''', (vou_id, vou_num, title, description, dept_id, g.user['id'], amount, payee_name, payee_phone, payment_method))

    conn.commit()
    conn.close()

    create_audit_log(g.user['id'], 'SUBMIT_REQUISITION', 'ExpenditureVoucher', vou_id, {
        'voucher_number': vou_num,
        'amount': amount,
        'department': dept['name']
    })

    return jsonify({'id': vou_id, 'voucher_number': vou_num, 'amount': amount, 'status': 'SUBMITTED'}), 201

# Committee Vote & Separation of Duties (Prevents Self-Approval)
@app.route('/api/finance/vouchers/<id>/committee-vote', methods=['POST'])
@login_required
@roles_required('PASTOR', 'FIRST_ELDER', 'HEAD_TREASURER', 'AUDITOR')
def vote_committee_voucher(id):
    data = request.get_json() or {}
    decision = data.get('decision', 'APPROVE') # APPROVE, REJECT, REQUEST_REVISION
    notes = data.get('notes', '')

    conn = get_db_connection()
    voucher = conn.execute('SELECT * FROM expenditure_vouchers WHERE id = ?', (id,)).fetchone()
    if not voucher:
        conn.close()
        return jsonify({'error': 'Voucher not found'}), 404

    # Separation of Duties Rule: Requester cannot approve their own request!
    if voucher['requested_by_id'] == g.user['id']:
        conn.close()
        return jsonify({'error': 'Security Violation: You cannot review or approve your own expenditure requisition.'}), 403

    dec_id = 'dec-' + str(uuid.uuid4())[:8]
    conn.execute('''
        INSERT OR REPLACE INTO approval_decisions (id, voucher_id, user_id, decision, notes, created_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
    ''', (dec_id, id, g.user['id'], decision, notes))

    # Check quorum
    approvals_count = conn.execute('''
        SELECT COUNT(*) as c FROM approval_decisions WHERE voucher_id = ? AND decision = 'APPROVE'
    ''', (id,)).fetchone()['c']

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if decision == 'REJECT':
        conn.execute('''
            UPDATE expenditure_vouchers
            SET status = 'REJECTED', rejection_reason = ?, elder_approved_by_id = ?, elder_approved_at = ?
            WHERE id = ?
        ''', (notes or 'Rejected by Approval Committee', g.user['id'], now_str, id))
    elif approvals_count >= 2:
        # Quorum met -> Authorized
        conn.execute('''
            UPDATE expenditure_vouchers
            SET status = 'ELDER_APPROVED', elder_approved_by_id = ?, elder_approved_at = ?, elder_notes = ?
            WHERE id = ?
        ''', (g.user['id'], now_str, f"Committee quorum approved ({approvals_count} votes): {notes}", id))

    conn.commit()
    conn.close()

    create_audit_log(g.user['id'], 'COMMITTEE_APPROVAL_VOTE', 'ExpenditureVoucher', id, {
        'decision': decision,
        'notes': notes,
        'votes_count': approvals_count
    })

    return jsonify({
        'message': f"Vote '{decision}' recorded.",
        'voucher_status': 'ELDER_APPROVED' if approvals_count >= 2 else voucher['status']
    })

@app.route('/api/finance/vouchers/<id>/treasurer-review', methods=['POST'])
@login_required
@roles_required('HEAD_TREASURER', 'ASSISTANT_TREASURER')
def treasurer_review_voucher(id):
    data = request.get_json() or {}
    action = data.get('action', 'APPROVE')
    notes = data.get('notes', '')

    conn = get_db_connection()
    voucher = conn.execute('SELECT * FROM expenditure_vouchers WHERE id = ?', (id,)).fetchone()
    if not voucher:
        conn.close()
        return jsonify({'error': 'Voucher not found'}), 404

    # Separation of duties: Requester cannot approve their own request!
    if voucher['requested_by_id'] == g.user['id']:
        conn.close()
        return jsonify({'error': 'Security Violation: You cannot review your own expenditure requisition.'}), 403

    if voucher['status'] != 'SUBMITTED':
        conn.close()
        return jsonify({'error': f"Cannot review voucher in '{voucher['status']}' status"}), 400

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if action == 'REJECT':
        conn.execute('''
            UPDATE expenditure_vouchers
            SET status = 'REJECTED', rejection_reason = ?, treasurer_reviewed_by_id = ?, treasurer_reviewed_at = ?
            WHERE id = ?
        ''', (notes or 'Rejected by Treasurer', g.user['id'], now_str, id))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Voucher rejected', 'status': 'REJECTED'})

    conn.execute('''
        UPDATE expenditure_vouchers
        SET status = 'TREASURER_REVIEWED', treasurer_notes = ?, treasurer_reviewed_by_id = ?, treasurer_reviewed_at = ?
        WHERE id = ?
    ''', (notes, g.user['id'], now_str, id))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Voucher reviewed by Treasury, forwarded to Elders/Pastor', 'status': 'TREASURER_REVIEWED'})

@app.route('/api/finance/vouchers/<id>/elder-approve', methods=['POST'])
@login_required
@roles_required('PASTOR', 'FIRST_ELDER')
def elder_approve_voucher(id):
    data = request.get_json() or {}
    action = data.get('action', 'APPROVE')
    notes = data.get('notes', '')

    conn = get_db_connection()
    voucher = conn.execute('SELECT * FROM expenditure_vouchers WHERE id = ?', (id,)).fetchone()
    if not voucher:
        conn.close()
        return jsonify({'error': 'Voucher not found'}), 404

    # Separation of duties: Requester cannot approve their own request!
    if voucher['requested_by_id'] == g.user['id']:
        conn.close()
        return jsonify({'error': 'Security Violation: You cannot approve your own expenditure requisition.'}), 403

    if voucher['status'] not in ['TREASURER_REVIEWED', 'SUBMITTED']:
        conn.close()
        return jsonify({'error': 'Voucher must be reviewed before final authorization'}), 400

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if action == 'REJECT':
        conn.execute('''
            UPDATE expenditure_vouchers
            SET status = 'REJECTED', rejection_reason = ?, elder_approved_by_id = ?, elder_approved_at = ?
            WHERE id = ?
        ''', (notes or 'Rejected by Elder/Pastor', g.user['id'], now_str, id))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Voucher rejected', 'status': 'REJECTED'})

    conn.execute('''
        UPDATE expenditure_vouchers
        SET status = 'ELDER_APPROVED', elder_notes = ?, elder_approved_by_id = ?, elder_approved_at = ?
        WHERE id = ?
    ''', (notes, g.user['id'], now_str, id))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Voucher authorized by Elder/Pastor, ready for disbursement', 'status': 'ELDER_APPROVED'})

@app.route('/api/finance/vouchers/<id>/disburse', methods=['POST'])
@login_required
@roles_required('HEAD_TREASURER', 'ASSISTANT_TREASURER')
def disburse_voucher(id):
    data = request.get_json() or {}
    ref = data.get('payment_reference') or f"DISB-{int(datetime.now().timestamp())}"
    method = data.get('payment_method')

    conn = get_db_connection()
    voucher = conn.execute('SELECT * FROM expenditure_vouchers WHERE id = ?', (id,)).fetchone()
    if not voucher:
        conn.close()
        return jsonify({'error': 'Voucher not found'}), 404

    if voucher['status'] != 'ELDER_APPROVED':
        conn.close()
        return jsonify({'error': 'Voucher must have Elder/Pastor authorization before disbursement'}), 400

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn.execute('''
        UPDATE expenditure_vouchers
        SET status = 'PAID', payment_reference = ?, payment_method = COALESCE(?, payment_method), paid_at = ?
        WHERE id = ?
    ''', (ref, method, now_str, id))

    conn.execute('''
        UPDATE departments
        SET budget_spent = budget_spent + ?
        WHERE id = ?
    ''', (voucher['amount'], voucher['department_id']))

    conn.commit()
    conn.close()

    create_audit_log(g.user['id'], 'DISBURSE_VOUCHER_PAYMENT', 'ExpenditureVoucher', id, {
        'amount': voucher['amount'],
        'reference': ref,
        'payee': voucher['payee_name']
    })

    return jsonify({'message': 'Voucher successfully paid and budget updated', 'status': 'PAID', 'reference': ref})

# -------------------------------------------------------------
# Church Assets & Property Inventory
# -------------------------------------------------------------
@app.route('/api/assets', methods=['GET'])
@login_required
def get_assets():
    conn = get_db_connection()
    assets = conn.execute('''
        SELECT a.*, u.full_name as custodian_name
        FROM church_assets a
        LEFT JOIN users u ON a.custodian_id = u.id
        ORDER BY a.category ASC, a.name ASC
    ''').fetchall()
    conn.close()
    return jsonify([dict(a) for a in assets])

@app.route('/api/assets', methods=['POST'])
@login_required
@roles_required('CHURCH_CLERK', 'HEAD_TREASURER', 'PASTOR', 'FIRST_ELDER')
def create_asset():
    data = request.get_json() or {}
    tag = data.get('asset_tag', '').strip()
    name = data.get('name', '').strip()
    category = data.get('category', 'SANCTUARY')
    quantity = int(data.get('quantity', 1))
    location = data.get('location', 'Main Sanctuary')
    condition = data.get('condition', 'GOOD')
    cost = float(data.get('purchase_cost', 0.0))
    custodian_id = data.get('custodian_id')
    notes = data.get('notes', '').strip() or None

    if not tag or not name:
        return jsonify({'error': 'Asset tag and name are required'}), 400

    conn = get_db_connection()
    asset_id = 'ast-' + str(uuid.uuid4())[:8]
    conn.execute('''
        INSERT INTO church_assets (id, asset_tag, name, category, quantity, location, condition, custodian_id, purchase_cost, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (asset_id, tag, name, category, quantity, location, condition, custodian_id, cost, notes))
    conn.commit()
    conn.close()

    create_audit_log(g.user['id'], 'RECORD_CHURCH_ASSET', 'ChurchAsset', asset_id, {'tag': tag, 'name': name})
    return jsonify({'id': asset_id, 'asset_tag': tag, 'name': name}), 201

# -------------------------------------------------------------
# Meetings, Minutes & Resolutions
# -------------------------------------------------------------
@app.route('/api/meetings', methods=['GET'])
@login_required
def get_meetings():
    role = g.user['role']
    permanent_roles = ['PASTOR', 'FIRST_ELDER', 'CHURCH_CLERK', 'AUDITOR', 'AUTHORIZED_ELDER_READONLY', 'DEPARTMENT_LEADER']
    if role not in permanent_roles:
        conn = get_db_connection()
        grant = conn.execute('SELECT id FROM meeting_access_grants WHERE user_id = ?', (g.user['id'],)).fetchone()
        conn.close()
        if not grant:
            return jsonify({'error': 'Access denied. Contact the Pastor to request board minutes access.'}), 403
        conn = get_db_connection()
    else:
        conn = get_db_connection()
    meetings = conn.execute('''
        SELECT m.*, ch.full_name as chairperson_name, sec.full_name as secretary_name
        FROM meetings m
        LEFT JOIN users ch ON m.chairperson_id = ch.id
        LEFT JOIN users sec ON m.secretary_id = sec.id
        ORDER BY m.date DESC
    ''').fetchall()

    result = []
    for m in meetings:
        m_dict = dict(m)
        resolutions = conn.execute('''
            SELECT r.*, u.full_name as assigned_officer_name
            FROM resolutions r
            LEFT JOIN users u ON r.assigned_officer_id = u.id
            WHERE r.meeting_id = ?
        ''', (m_dict['id'],)).fetchall()
        m_dict['resolutions'] = [dict(r) for r in resolutions]
        result.append(m_dict)

    conn.close()
    return jsonify(result)

@app.route('/api/meetings', methods=['POST'])
@login_required
@roles_required('PASTOR', 'FIRST_ELDER', 'CHURCH_CLERK')
def create_meeting():
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    meeting_type = data.get('meeting_type', 'CHURCH_BOARD')
    date = data.get('date', '').strip()
    chairperson_id = data.get('chairperson_id')
    secretary_id = data.get('secretary_id')
    minutes_text = data.get('minutes_text', '').strip()
    resolutions = data.get('resolutions', [])

    if not title or not date or not minutes_text:
        return jsonify({'error': 'Title, date and minutes text are required'}), 400

    conn = get_db_connection()
    mtg_id = 'mtg-' + str(uuid.uuid4())[:8]
    conn.execute('''
        INSERT INTO meetings (id, title, meeting_type, date, chairperson_id, secretary_id, minutes_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (mtg_id, title, meeting_type, date, chairperson_id, secretary_id, minutes_text))

    for r in resolutions:
        res_num = r.get('resolution_number', '').strip()
        res_title = r.get('title', '').strip()
        res_desc = r.get('description', '').strip()
        if not res_num or not res_title or not res_desc:
            continue
        conn.execute('''
            INSERT INTO resolutions (id, meeting_id, resolution_number, title, description, assigned_officer_id, due_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (str(uuid.uuid4()), mtg_id, res_num, res_title, res_desc,
              r.get('assigned_officer_id'), r.get('due_date')))

    conn.commit()
    conn.close()

    create_audit_log(g.user['id'], 'RECORD_BOARD_MINUTES', 'Meeting', mtg_id, {'title': title, 'date': date})
    return jsonify({'id': mtg_id, 'title': title}), 201

@app.route('/api/meetings/access-grants', methods=['GET'])
@login_required
@roles_required('PASTOR')
def get_meeting_access_grants():
    conn = get_db_connection()
    grants = conn.execute('''
        SELECT g.id, g.user_id, g.created_at, u.full_name, u.role, u.email,
               gb.full_name as granted_by_name
        FROM meeting_access_grants g
        JOIN users u ON g.user_id = u.id
        JOIN users gb ON g.granted_by_id = gb.id
        ORDER BY u.full_name ASC
    ''').fetchall()
    conn.close()
    return jsonify([dict(g) for g in grants])

@app.route('/api/meetings/access-grants', methods=['POST'])
@login_required
@roles_required('PASTOR')
def grant_meeting_access():
    data = request.get_json() or {}
    user_id = data.get('user_id', '').strip()
    if not user_id:
        return jsonify({'error': 'user_id is required'}), 400

    conn = get_db_connection()
    user = conn.execute('SELECT id, full_name, role FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'User not found'}), 404

    # Roles that already have permanent access don't need a grant
    permanent_roles = ['PASTOR', 'FIRST_ELDER', 'CHURCH_CLERK', 'AUDITOR', 'AUTHORIZED_ELDER_READONLY', 'DEPARTMENT_LEADER']
    if user['role'] in permanent_roles:
        conn.close()
        return jsonify({'error': f"{user['full_name']} already has permanent access via their {user['role']} role"}), 400

    grant_id = 'mag-' + str(uuid.uuid4())[:8]
    try:
        conn.execute('INSERT INTO meeting_access_grants (id, user_id, granted_by_id) VALUES (?, ?, ?)',
                     (grant_id, user_id, g.user['id']))
        conn.commit()
    except Exception:
        conn.close()
        return jsonify({'error': 'Access already granted to this user'}), 409
    conn.close()

    create_audit_log(g.user['id'], 'GRANT_MEETING_ACCESS', 'MeetingAccessGrant', grant_id,
                     {'user': user['full_name'], 'role': user['role']})
    return jsonify({'message': f"Board minutes access granted to {user['full_name']}"}), 201

@app.route('/api/meetings/access-grants/<user_id>', methods=['DELETE'])
@login_required
@roles_required('PASTOR')
def revoke_meeting_access(user_id):
    conn = get_db_connection()
    grant = conn.execute('SELECT g.id, u.full_name FROM meeting_access_grants g JOIN users u ON g.user_id = u.id WHERE g.user_id = ?', (user_id,)).fetchone()
    if not grant:
        conn.close()
        return jsonify({'error': 'No access grant found for this user'}), 404

    conn.execute('DELETE FROM meeting_access_grants WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

    create_audit_log(g.user['id'], 'REVOKE_MEETING_ACCESS', 'MeetingAccessGrant', grant['id'],
                     {'user': grant['full_name']})
    return jsonify({'message': f"Board minutes access revoked for {grant['full_name']}"})

# -------------------------------------------------------------
# Database Disaster Recovery / Availability Backup
# -------------------------------------------------------------
@app.route('/api/admin/backup', methods=['GET'])
@login_required
@roles_required('CHURCH_ADMIN', 'PASTOR', 'FIRST_ELDER')
def download_backup():
    conn = get_db_connection()
    tables = ['users', 'departments', 'members', 'fund_categories', 'tithe_offering_envelopes', 'envelope_items', 'expenditure_vouchers', 'church_assets', 'meetings', 'resolutions', 'announcements', 'events', 'attendance', 'audit_logs']
    backup = {}
    for t in tables:
        rows = conn.execute(f"SELECT * FROM {t}").fetchall()
        backup[t] = [dict(r) for r in rows]
    conn.close()

    create_audit_log(g.user['id'], 'DISASTER_RECOVERY_BACKUP_EXPORT', 'Database', None, {'timestamp': datetime.now().isoformat()})
    return jsonify({
        'backup_version': '1.1',
        'generated_at': datetime.now().isoformat(),
        'church': 'Seventh-day Adventist Church (Kenya)',
        'data': backup
    })

# -------------------------------------------------------------
# Include Existing Routes (Announcements, My Giving, Members, Departments, M-Pesa, Events, Attendance, Reports, Dashboard, Audit)
# -------------------------------------------------------------
@app.route('/api/announcements', methods=['GET'])
@login_required
def get_announcements():
    conn = get_db_connection()
    query = '''
        SELECT a.*, u.full_name as author_name, u.role as author_role
        FROM announcements a
        JOIN users u ON a.author_id = u.id
        WHERE 1=1
    '''
    params = []
    if g.user['role'] == 'MEMBER':
        query += " AND a.target_audience IN ('ALL', 'MEMBERS_ONLY')"
    query += ' ORDER BY a.is_pinned DESC, a.created_at DESC'
    announcements = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(a) for a in announcements])

@app.route('/api/announcements', methods=['POST'])
@login_required
@roles_required('PASTOR', 'FIRST_ELDER', 'CHURCH_CLERK', 'DEPARTMENT_LEADER', 'HEAD_TREASURER')
def create_announcement():
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()
    category = data.get('category', 'GENERAL')
    target = data.get('target_audience', 'ALL')
    pinned = 1 if data.get('is_pinned') else 0

    if not title or not content:
        return jsonify({'error': 'Title and content are required'}), 400

    ann_id = 'ann-' + str(uuid.uuid4())[:8]
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO announcements (id, title, content, category, target_audience, author_id, is_pinned)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (ann_id, title, content, category, target, g.user['id'], pinned))
    conn.commit()
    conn.close()

    create_audit_log(g.user['id'], 'CREATE_ANNOUNCEMENT', 'Announcement', ann_id, {'title': title})
    return jsonify({'id': ann_id, 'title': title}), 201

@app.route('/api/finance/my-giving', methods=['GET'])
@login_required
def get_my_giving():
    conn = get_db_connection()
    member_id = g.user.get('member_id')
    user_email = g.user.get('email')
    user_phone = g.user.get('phone')

    member = None
    if member_id:
        member = conn.execute('SELECT * FROM members WHERE id = ?', (member_id,)).fetchone()
    if not member and user_email:
        member = conn.execute('SELECT * FROM members WHERE LOWER(email) = ?', (user_email.lower(),)).fetchone()
    if not member and user_phone:
        member = conn.execute('SELECT * FROM members WHERE phone = ?', (user_phone,)).fetchone()

    if not member:
        conn.close()
        return jsonify({'member': None, 'envelopes': [], 'totals': {'tithe': 0.0, 'total_giving': 0.0}})

    envelopes = conn.execute('''
        SELECT e.*
        FROM tithe_offering_envelopes e
        WHERE e.member_id = ?
        ORDER BY e.transaction_date DESC
    ''', (member['id'],)).fetchall()

    result_envelopes = []
    total_tithe = 0.0
    total_giving = 0.0

    for env in envelopes:
        e_dict = dict(env)
        items = conn.execute('''
            SELECT ei.*, fc.name as fund_name, fc.code as fund_code
            FROM envelope_items ei
            JOIN fund_categories fc ON ei.fund_category_id = fc.id
            WHERE ei.envelope_id = ?
        ''', (e_dict['id'],)).fetchall()
        e_dict['items'] = [dict(it) for it in items]

        for it in items:
            amt = float(it['amount'])
            total_giving += amt
            if it['fund_code'] == 'TITHE':
                total_tithe += amt

        result_envelopes.append(e_dict)

    conn.close()
    return jsonify({
        'member': {
            'member_number': member['member_number'],
            'name': f"{member['first_name']} {member['last_name']}",
            'baptism_date': member['baptism_date'],
            'baptism_church': member['baptism_church']
        },
        'envelopes': result_envelopes,
        'totals': {'total_tithe': total_tithe, 'total_giving': total_giving}
    })

@app.route('/api/members', methods=['GET'])
@login_required
def get_members():
    is_officer = g.user['role'] in ['CHURCH_ADMIN', 'PASTOR', 'FIRST_ELDER', 'CHURCH_CLERK', 'HEAD_TREASURER', 'ASSISTANT_TREASURER', 'DEPARTMENT_LEADER', 'AUDITOR', 'AUTHORIZED_ELDER_READONLY']
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '').strip()
    department_id = request.args.get('department_id', '').strip()

    conn = get_db_connection()
    if g.user['role'] == 'DEPARTMENT_LEADER':
        scoped_dept = g.user.get('department_id')
        if not scoped_dept:
            conn.close()
            return jsonify([])

        query = '''
            SELECT m.*, d.name as department_name, d.code as department_code
            FROM members m
            LEFT JOIN departments d ON m.department_id = d.id
            WHERE m.department_id = ?
        '''
        params = [scoped_dept]
        if status:
            query += ' AND m.status = ?'
            params.append(status)
        if department_id and department_id != scoped_dept:
            query += ' AND m.department_id = ?'
            params.append(department_id)
        if search:
            query += ' AND (m.first_name LIKE ? OR m.last_name LIKE ? OR m.member_number LIKE ? OR m.phone LIKE ?)'
            like = f'%{search}%'
            params.extend([like, like, like, like])
        query += ' ORDER BY m.last_name ASC, m.first_name ASC'
        members = conn.execute(query, params).fetchall()
        conn.close()
        return jsonify([dict(m) for m in members])

    if is_officer:
        query = '''
            SELECT m.*, d.name as department_name, d.code as department_code
            FROM members m
            LEFT JOIN departments d ON m.department_id = d.id
            WHERE 1=1
        '''
        params = []
        if status:
            query += ' AND m.status = ?'
            params.append(status)
        if department_id:
            query += ' AND m.department_id = ?'
            params.append(department_id)
        if search:
            query += ' AND (m.first_name LIKE ? OR m.last_name LIKE ? OR m.member_number LIKE ? OR m.phone LIKE ?)'
            like = f'%{search}%'
            params.extend([like, like, like, like])
        query += ' ORDER BY m.last_name ASC, m.first_name ASC'
        members = conn.execute(query, params).fetchall()
        conn.close()
        return jsonify([dict(m) for m in members])
    else:
        member_id = g.user.get('member_id')
        if not member_id:
            conn.close()
            return jsonify([])
        query = '''
            SELECT m.id, m.member_number, m.first_name, m.last_name, m.gender, m.status, d.name as department_name
            FROM members m
            LEFT JOIN departments d ON m.department_id = d.id
            WHERE m.id = ? AND m.status = 'ACTIVE'
            ORDER BY m.last_name ASC, m.first_name ASC
        '''
        members = conn.execute(query, (member_id,)).fetchall()
        conn.close()
        return jsonify([dict(m) for m in members])

@app.route('/api/members', methods=['POST'])
@login_required
@roles_required('CHURCH_CLERK', 'PASTOR', 'FIRST_ELDER')
def create_member():
    data = request.get_json() or {}
    member_num = data.get('member_number', '').strip()
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    phone = data.get('phone', '').strip()
    email = data.get('email', '').strip()
    gender = data.get('gender', 'MALE')
    bap_date = data.get('baptism_date')
    bap_church = data.get('baptism_church')
    status = data.get('status', 'ACTIVE')
    dept_id = data.get('department_id')
    residence = data.get('residence', '')

    if not member_num or not first_name or not last_name:
        return jsonify({'error': 'Member number, first name and last name are required'}), 400

    conn = get_db_connection()
    exists = conn.execute('SELECT id FROM members WHERE member_number = ?', (member_num,)).fetchone()
    if exists:
        conn.close()
        return jsonify({'error': f'Member number {member_num} is already registered'}), 409

    member_id = 'mem-' + str(uuid.uuid4())[:8]
    conn.execute('''
        INSERT INTO members (id, member_number, first_name, last_name, phone, email, gender, baptism_date, baptism_church, status, department_id, residence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (member_id, member_num, first_name, last_name, phone, email, gender, bap_date, bap_church, status, dept_id, residence))
    conn.commit()
    conn.close()

    create_audit_log(g.user['id'], 'CREATE_MEMBER', 'Member', member_id, {'member_number': member_num, 'name': f'{first_name} {last_name}'})
    return jsonify({'id': member_id, 'member_number': member_num}), 201

@app.route('/api/departments', methods=['GET'])
@login_required
def get_departments():
    is_officer = g.user['role'] in ['CHURCH_ADMIN', 'PASTOR', 'FIRST_ELDER', 'HEAD_TREASURER', 'ASSISTANT_TREASURER', 'DEPARTMENT_LEADER', 'AUDITOR', 'AUTHORIZED_ELDER_READONLY']
    conn = get_db_connection()
    departments = conn.execute('''
        SELECT d.*, u.full_name as leader_name, u.email as leader_email, u.phone as leader_phone,
               (SELECT COUNT(*) FROM members WHERE department_id = d.id) as member_count,
               (SELECT COUNT(*) FROM expenditure_vouchers WHERE department_id = d.id) as voucher_count
        FROM departments d
        LEFT JOIN users u ON d.leader_id = u.id
        ORDER BY d.name ASC
    ''').fetchall()
    conn.close()

    result = []
    for d in departments:
        d_dict = dict(d)
        if is_officer:
            d_dict['budget_remaining'] = max(0.0, d_dict['budget_allocation'] - d_dict['budget_spent'])
        else:
            del d_dict['budget_allocation']
            del d_dict['budget_spent']
            d_dict.pop('leader_email', None)
            d_dict.pop('leader_phone', None)
        result.append(d_dict)
    return jsonify(result)

@app.route('/api/departments/<dept_id>', methods=['PATCH'])
@login_required
@roles_required('CHURCH_CLERK', 'PASTOR', 'FIRST_ELDER')
def update_department(dept_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400
    if not data or not set(data).issubset({'name', 'code', 'description', 'leader_id'}):
        return jsonify({'error': 'Provide department details or a leader assignment to update.'}), 400

    conn = get_db_connection()
    current = conn.execute(
        '''
        SELECT d.id, d.name, d.code, d.description, d.leader_id, u.full_name AS leader_name
        FROM departments d
        LEFT JOIN users u ON d.leader_id = u.id
        WHERE d.id = ?
        ''',
        (dept_id,)
    ).fetchone()
    if not current:
        conn.close()
        return jsonify({'error': 'Department not found'}), 404

    name = data.get('name', current['name'])
    code = data.get('code', current['code'])
    description = data.get('description', current['description'])
    leader_id = data.get('leader_id', current['leader_id'])
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 100:
        conn.close()
        return jsonify({'error': 'Department name must be between 2 and 100 characters.'}), 400
    if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_-]{2,10}', code.strip()):
        conn.close()
        return jsonify({'error': 'Department code must be 2 to 10 letters, numbers, underscores, or hyphens.'}), 400
    if description is not None and not isinstance(description, str):
        conn.close()
        return jsonify({'error': 'Department description must be text.'}), 400
    if description is not None and len(description.strip()) > 500:
        conn.close()
        return jsonify({'error': 'Department description must be 500 characters or fewer.'}), 400
    if leader_id is not None and not isinstance(leader_id, str):
        conn.close()
        return jsonify({'error': 'Department leader selection is invalid.'}), 400

    name = name.strip()
    code = code.strip().upper()
    description = description.strip() if description is not None else None
    description = description or None
    leader_id = leader_id.strip() if leader_id else None
    if 'leader_id' in data and not leader_id:
        leader_id = None

    try:
        conn.execute('BEGIN IMMEDIATE')
        duplicate = conn.execute(
            'SELECT 1 FROM departments WHERE id != ? AND (LOWER(name) = LOWER(?) OR code = ?)',
            (dept_id, name, code)
        ).fetchone()
        if duplicate:
            conn.rollback()
            return jsonify({'error': 'A department with that name or code already exists.'}), 409

        new_leader = None
        if leader_id and leader_id != current['leader_id']:
            new_leader = conn.execute('''
                SELECT id, full_name, role, member_id, department_id FROM users
                WHERE id = ? AND active = 1
                  AND (
                      role = 'DEPARTMENT_LEADER'
                      OR (role = 'MEMBER' AND member_id IS NOT NULL)
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM departments d
                      WHERE d.leader_id = users.id AND d.id != ?
                  )
            ''', (leader_id, dept_id)).fetchone()
            if not new_leader:
                conn.rollback()
                return jsonify({'error': 'Select an active member who is not leading another department.'}), 400

        previous_leader = None
        if current['leader_id'] and current['leader_id'] != leader_id:
            previous_leader = conn.execute(
                'SELECT id, full_name, role, department_id FROM users WHERE id = ?',
                (current['leader_id'],)
            ).fetchone()
            if previous_leader:
                conn.execute('''
                    UPDATE users
                    SET role = 'MEMBER'
                    WHERE id = ?
                ''', (previous_leader['id'],))

        conn.execute('''
            UPDATE departments
            SET name = ?, code = ?, description = ?, leader_id = ?
            WHERE id = ?
        ''', (name, code, description, leader_id, dept_id))
        if new_leader:
            conn.execute(
                "UPDATE users SET role = 'DEPARTMENT_LEADER', department_id = ? WHERE id = ?",
                (dept_id, new_leader['id'])
            )
            if new_leader['member_id']:
                conn.execute(
                    'UPDATE members SET department_id = ? WHERE id = ?',
                    (dept_id, new_leader['member_id'])
                )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        return jsonify({'error': 'A department with that name or code already exists.'}), 409
    finally:
        conn.close()

    create_audit_log(g.user['id'], 'UPDATE_DEPARTMENT', 'Department', dept_id, {
        'name': name,
        'code': code,
        'previous_leader_id': current['leader_id'],
        'leader_id': leader_id
    })
    if previous_leader:
        create_audit_log(g.user['id'], 'REMOVE_DEPARTMENT_LEADER', 'User', previous_leader['id'], {
            'department_id': dept_id,
            'department_name': name
        })
    if new_leader:
        create_audit_log(g.user['id'], 'ASSIGN_DEPARTMENT_LEADER', 'User', new_leader['id'], {
            'department_id': dept_id,
            'department_name': name,
            'old_role': new_leader['role'],
            'new_role': 'DEPARTMENT_LEADER'
        })

    result = dict(current)
    result.update({
        'name': name,
        'code': code,
        'description': description,
        'leader_id': leader_id,
        'leader_name': (
            new_leader['full_name'] if new_leader
            else current['leader_name'] if leader_id == current['leader_id']
            else None
        )
    })
    return jsonify(result)

@app.route('/api/departments/leader-candidates', methods=['GET'])
@login_required
@roles_required('CHURCH_CLERK', 'PASTOR', 'FIRST_ELDER')
def get_department_leader_candidates():
    department_id = request.args.get('department_id', '').strip()
    conn = get_db_connection()
    if department_id and not conn.execute(
        'SELECT 1 FROM departments WHERE id = ?', (department_id,)
    ).fetchone():
        conn.close()
        return jsonify({'error': 'Department not found'}), 404

    available_leader = '''
        NOT EXISTS (
            SELECT 1 FROM departments d
            WHERE d.leader_id = u.id
    '''
    params = []
    if department_id:
        available_leader += ' AND d.id != ?'
        params.append(department_id)
    available_leader += ')'
    candidates = conn.execute(f'''
        SELECT u.id, u.full_name, u.email, u.role
        FROM users u
        WHERE u.active = 1
          AND (
              u.role = 'DEPARTMENT_LEADER'
              OR (u.role = 'MEMBER' AND u.member_id IS NOT NULL)
          )
          AND {available_leader}
        ORDER BY u.full_name ASC
    ''', params).fetchall()
    conn.close()
    return jsonify([dict(candidate) for candidate in candidates])

@app.route('/api/departments', methods=['POST'])
@login_required
@roles_required('CHURCH_CLERK', 'PASTOR', 'FIRST_ELDER')
def create_department():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400

    name = data.get('name')
    code = data.get('code')
    description = data.get('description')
    leader_id = data.get('leader_id')

    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 100:
        return jsonify({'error': 'Department name must be between 2 and 100 characters.'}), 400
    if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_-]{2,10}', code.strip()):
        return jsonify({'error': 'Department code must be 2 to 10 letters, numbers, underscores, or hyphens.'}), 400
    if description is not None and not isinstance(description, str):
        return jsonify({'error': 'Department description must be text.'}), 400
    if description is not None and len(description.strip()) > 500:
        return jsonify({'error': 'Department description must be 500 characters or fewer.'}), 400
    if not isinstance(leader_id, str) or not leader_id.strip():
        return jsonify({'error': 'Select a department leader.'}), 400

    name = name.strip()
    code = code.strip().upper()
    description = description.strip() if description is not None else None
    description = description or None
    leader_id = leader_id.strip()
    department_id = 'dept-' + str(uuid.uuid4())[:8]

    conn = get_db_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        existing = conn.execute(
            'SELECT id FROM departments WHERE LOWER(name) = LOWER(?) OR code = ?',
            (name, code)
        ).fetchone()
        if existing:
            conn.rollback()
            return jsonify({'error': 'A department with that name or code already exists.'}), 409

        leader = conn.execute('''
            SELECT id, full_name, role, member_id, department_id FROM users
            WHERE id = ? AND active = 1
              AND (
                  role = 'DEPARTMENT_LEADER'
                  OR (role = 'MEMBER' AND member_id IS NOT NULL)
              )
              AND NOT EXISTS (
                  SELECT 1 FROM departments d WHERE d.leader_id = users.id
              )
        ''', (leader_id,)).fetchone()
        if not leader:
            conn.rollback()
            return jsonify({'error': 'Select an active member who is not already leading a department.'}), 400

        conn.execute('''
            INSERT INTO departments (id, name, code, description, leader_id, budget_allocation, budget_spent)
            VALUES (?, ?, ?, ?, ?, 0, 0)
        ''', (department_id, name, code, description, leader_id))
        conn.execute('''
            UPDATE users SET role = 'DEPARTMENT_LEADER', department_id = ?
            WHERE id = ?
        ''', (department_id, leader_id))
        if leader['member_id']:
            conn.execute(
                'UPDATE members SET department_id = ? WHERE id = ?',
                (department_id, leader['member_id'])
            )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        return jsonify({'error': 'A department with that name or code already exists.'}), 409
    finally:
        conn.close()

    create_audit_log(g.user['id'], 'CREATE_DEPARTMENT', 'Department', department_id, {
        'name': name,
        'code': code,
        'leader_id': leader_id,
        'leader_name': leader['full_name']
    })
    create_audit_log(g.user['id'], 'ASSIGN_DEPARTMENT_LEADER', 'User', leader_id, {
        'department_id': department_id,
        'department_name': name,
        'old_role': leader['role'],
        'old_department_id': leader['department_id'],
        'new_role': 'DEPARTMENT_LEADER'
    })

    return jsonify({
        'id': department_id,
        'name': name,
        'code': code,
        'description': description,
        'leader_id': leader_id,
        'leader_name': leader['full_name'],
        'budget_allocation': 0,
        'budget_spent': 0
    }), 201

@app.route('/api/mpesa/simulate', methods=['POST'])
@login_required
def simulate_mpesa():
    data = request.get_json() or {}
    phone = data.get('phone', '254712345678')
    amount = float(data.get('amount', 1000.0))
    account_ref = data.get('account_reference', 'TITHE')
    donor_name = data.get('donor_name') or 'M-Pesa Contributor'
    fund_code = data.get('fund_code', 'TITHE')

    conn = get_db_connection()
    test_receipt = f"QA{int(datetime.now().timestamp() * 10) % 90000000 + 10000000}"
    tx_id = 'tx-' + str(uuid.uuid4())[:8]

    conn.execute('''
        INSERT INTO payment_transactions (id, provider, reference, amount, account_ref, phone, status)
        VALUES (?, 'MPESA', ?, ?, ?, ?, 'CONFIRMED')
    ''', (tx_id, test_receipt, amount, account_ref, phone))

    fund = conn.execute('SELECT * FROM fund_categories WHERE code = ?', (fund_code,)).fetchone()
    if not fund:
        fund = conn.execute('SELECT * FROM fund_categories LIMIT 1').fetchone()

    member = None
    if g.user.get('member_id'):
        member = conn.execute('SELECT * FROM members WHERE id = ?', (g.user['member_id'],)).fetchone()
    if not member:
        member = conn.execute('SELECT * FROM members WHERE member_number = ? OR phone = ?', (account_ref, phone)).fetchone()

    year = datetime.now().year
    count = conn.execute('SELECT COUNT(*) as c FROM tithe_offering_envelopes').fetchone()['c']
    rec_num = f"REC-{year}-{str(count + 1).zfill(5)}"
    env_id = 'env-' + str(uuid.uuid4())[:8]
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    v_code = generate_verification_code(rec_num, amount, now_str)

    recorded_name = f"{member['first_name']} {member['last_name']}" if member else (donor_name or g.user['full_name'])
    member_id = member['id'] if member else None

    recorder = conn.execute("SELECT id FROM users WHERE role IN ('HEAD_TREASURER', 'CHURCH_ADMIN') LIMIT 1").fetchone()
    recorder_id = recorder['id'] if recorder else g.user['id']

    conn.execute('''
        INSERT INTO tithe_offering_envelopes (
            id, receipt_number, verification_code, member_id, donor_name, donor_phone, payment_method,
            payment_status, mpesa_receipt_number, total_amount, status, notes, recorded_by_id
        ) VALUES (?, ?, ?, ?, ?, ?, 'MPESA', 'VERIFIED_PROVIDER', ?, ?, 'CONFIRMED', ?, ?)
    ''', (env_id, rec_num, v_code, member_id, recorded_name, phone, test_receipt, amount, f"Safaricom M-Pesa Inflow (Ref: {account_ref})", recorder_id))

    conn.execute('''
        INSERT INTO envelope_items (id, envelope_id, fund_category_id, amount)
        VALUES (?, ?, ?, ?)
    ''', (str(uuid.uuid4()), env_id, fund['id'], amount))

    conn.execute("UPDATE payment_transactions SET reconciled_with_envelope_id = ? WHERE id = ?", (env_id, tx_id))
    conn.commit()
    conn.close()

    create_audit_log(g.user['id'], 'SIMULATE_MPESA_GIVING', 'PaymentTransaction', tx_id, {
        'receipt': test_receipt,
        'amount': amount,
        'church_receipt': rec_num
    })

    return jsonify({
        'success': True,
        'mpesa_receipt': test_receipt,
        'church_receipt': rec_num,
        'verification_code': v_code,
        'amount': amount,
        'donor': recorded_name,
        'message': f"M-Pesa KES {amount:,.2f} recorded and digital receipt {rec_num} created"
    })

@app.route('/api/events', methods=['GET'])
@login_required
def get_events():
    department_id = request.args.get('department_id', '').strip()
    search = request.args.get('search', '').strip()
    when = request.args.get('when', 'all').strip().lower()
    conditions = []
    params = []
    if department_id:
        conditions.append('e.department_id = ?')
        params.append(department_id)
    if g.user['role'] == 'MEMBER':
        conditions.append('e.is_public = 1')
    if search:
        conditions.append('(e.title LIKE ? OR e.location LIKE ? OR d.name LIKE ?)')
        pattern = f'%{search}%'
        params.extend([pattern, pattern, pattern])
    if when == 'upcoming':
        conditions.append("datetime(e.start_date) >= datetime('now', 'localtime')")
    elif when == 'past':
        conditions.append("datetime(e.start_date) < datetime('now', 'localtime')")
    elif when != 'all':
        return jsonify({'error': 'when must be upcoming, past, or all.'}), 400

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ''
    conn = get_db_connection()
    events = conn.execute(f'''
        SELECT e.*, d.name as department_name, u.full_name as coordinator_name
        FROM events e
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN users u ON e.coordinator_id = u.id
        {where_clause}
        ORDER BY e.start_date ASC
    ''', params).fetchall()
    conn.close()
    return jsonify([dict(e) for e in events])

@app.route('/api/events', methods=['POST'])
@login_required
@roles_required('PASTOR', 'FIRST_ELDER', 'CHURCH_CLERK', 'DEPARTMENT_LEADER')
def create_event():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400
    title = data.get('title')
    description = data.get('description')
    location = data.get('location')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    dept_id = data.get('department_id')

    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
        return jsonify({'error': 'Event title is required and must be 120 characters or fewer.'}), 400
    if not isinstance(location, str) or not location.strip() or len(location.strip()) > 160:
        return jsonify({'error': 'Event location is required and must be 160 characters or fewer.'}), 400
    if description is not None and not isinstance(description, str):
        return jsonify({'error': 'Event description must be text.'}), 400
    if description is not None and len(description.strip()) > 1000:
        return jsonify({'error': 'Event description must be 1000 characters or fewer.'}), 400
    if not isinstance(start_date, str) or not isinstance(end_date, str):
        return jsonify({'error': 'Valid start and end dates are required.'}), 400
    try:
        start_value = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end_value = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    except ValueError:
        return jsonify({'error': 'Start and end dates must be valid ISO date/time values.'}), 400
    if (start_value.utcoffset() is not None) != (end_value.utcoffset() is not None):
        return jsonify({'error': 'Start and end dates must use the same time zone format.'}), 400
    if start_value.utcoffset() is not None:
        start_value = start_value.astimezone().replace(tzinfo=None)
        end_value = end_value.astimezone().replace(tzinfo=None)
    if end_value < start_value:
        return jsonify({'error': 'Event end date must be on or after its start date.'}), 400
    if dept_id is not None and (not isinstance(dept_id, str) or not dept_id.strip()):
        return jsonify({'error': 'Department selection is invalid.'}), 400
    dept_id = dept_id.strip() if dept_id else None
    if g.user['role'] == 'DEPARTMENT_LEADER' and dept_id and dept_id != g.user.get('department_id'):
        return jsonify({'error': 'Department leaders may only schedule events for their own department.'}), 403

    title = title.strip()
    location = location.strip()
    description = description.strip() if description else None
    normalized_start = start_value.strftime('%Y-%m-%d %H:%M:%S')
    normalized_end = end_value.strftime('%Y-%m-%d %H:%M:%S')

    conn = get_db_connection()
    if dept_id and not conn.execute('SELECT 1 FROM departments WHERE id = ?', (dept_id,)).fetchone():
        conn.close()
        return jsonify({'error': 'Department not found.'}), 404
    evt_id = 'evt-' + str(uuid.uuid4())[:8]
    conn.execute('''
        INSERT INTO events (id, title, description, department_id, coordinator_id, location, start_date, end_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (evt_id, title, description, dept_id, g.user['id'], location, normalized_start, normalized_end))
    conn.commit()
    conn.close()

    create_audit_log(g.user['id'], 'CREATE_EVENT', 'Event', evt_id, {
        'title': title,
        'department_id': dept_id,
        'start_date': normalized_start,
        'end_date': normalized_end
    })
    return jsonify({'id': evt_id, 'title': title}), 201

@app.route('/api/attendance', methods=['GET'])
@login_required
def get_attendance():
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    service_type = request.args.get('service_type', '').strip()
    event_id = request.args.get('event_id', '').strip()
    conditions = []
    params = []
    for label, value in (('date_from', date_from), ('date_to', date_to)):
        if value:
            try:
                parsed_date = datetime.strptime(value, '%Y-%m-%d')
            except ValueError:
                return jsonify({'error': f'{label} must use YYYY-MM-DD format.'}), 400
            if parsed_date.strftime('%Y-%m-%d') != value:
                return jsonify({'error': f'{label} must use YYYY-MM-DD format.'}), 400
    if date_from and date_to and date_from > date_to:
        return jsonify({'error': 'date_from must be on or before date_to.'}), 400
    if date_from:
        conditions.append('a.date >= ?')
        params.append(date_from)
    if date_to:
        conditions.append('a.date <= ?')
        params.append(date_to)
    if service_type:
        conditions.append('a.service_type = ?')
        params.append(service_type)
    if event_id:
        conditions.append('a.event_id = ?')
        params.append(event_id)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ''
    conn = get_db_connection()
    records = conn.execute(f'''
        SELECT a.*, u.full_name as recorded_by_name, e.title as event_title
        FROM attendance a
        LEFT JOIN users u ON a.recorded_by_id = u.id
        LEFT JOIN events e ON a.event_id = e.id
        {where_clause}
        ORDER BY a.date DESC LIMIT 50
    ''', params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in records])

@app.route('/api/attendance', methods=['POST'])
@login_required
@roles_required('CHURCH_CLERK', 'PASTOR', 'FIRST_ELDER')
def record_attendance():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400
    service_type = data.get('service_type', 'DIVINE_SERVICE')
    date_val = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    event_id = data.get('event_id') or None
    allowed_services = ['DIVINE_SERVICE', 'SABBATH_SCHOOL', 'YOUTH_SERVICE', 'MIDWEEK_PRAYER', 'SPECIAL_EVENT']
    if not isinstance(service_type, str) or service_type not in allowed_services:
        return jsonify({'error': 'Select a valid service type.'}), 400
    if not isinstance(date_val, str):
        return jsonify({'error': 'Attendance date must use YYYY-MM-DD format.'}), 400
    try:
        parsed_date = datetime.strptime(date_val, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Attendance date must use YYYY-MM-DD format.'}), 400
    if parsed_date.strftime('%Y-%m-%d') != date_val:
        return jsonify({'error': 'Attendance date must use YYYY-MM-DD format.'}), 400
    count_values = (data.get('adult_count', 0), data.get('children_count', 0), data.get('visitors_count', 0))
    if any(isinstance(value, bool) for value in count_values):
        return jsonify({'error': 'Attendance counts must be whole numbers.'}), 400
    try:
        adults, children, visitors = (int(value) for value in count_values)
    except (TypeError, ValueError):
        return jsonify({'error': 'Attendance counts must be whole numbers.'}), 400
    if any(count < 0 for count in (adults, children, visitors)):
        return jsonify({'error': 'Attendance counts cannot be negative.'}), 400
    notes = data.get('notes')
    if notes is not None and not isinstance(notes, str):
        return jsonify({'error': 'Attendance notes must be text.'}), 400
    if notes and len(notes) > 500:
        return jsonify({'error': 'Attendance notes must be 500 characters or fewer.'}), 400
    if event_id is not None and not isinstance(event_id, str):
        return jsonify({'error': 'Event selection is invalid.'}), 400
    total = adults + children + visitors

    conn = get_db_connection()
    if event_id:
        event = conn.execute(
            "SELECT 1 FROM events WHERE id = ? AND date(?) BETWEEN date(start_date) AND date(end_date)",
            (event_id, date_val)
        ).fetchone()
        if not event:
            event_exists = conn.execute('SELECT 1 FROM events WHERE id = ?', (event_id,)).fetchone()
            conn.close()
            if not event_exists:
                return jsonify({'error': 'Event not found.'}), 404
            return jsonify({'error': 'Attendance date must fall within the linked event dates.'}), 400
    att_id = str(uuid.uuid4())
    conn.execute('''
        INSERT INTO attendance (id, event_id, service_type, date, adult_count, children_count, visitors_count, total_count, notes, recorded_by_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (att_id, event_id, service_type, date_val, adults, children, visitors, total, notes, g.user['id']))
    conn.commit()
    conn.close()

    create_audit_log(g.user['id'], 'RECORD_ATTENDANCE', 'Attendance', att_id, {
        'service': service_type,
        'event_id': event_id,
        'total': total
    })
    return jsonify({'id': att_id, 'total_count': total, 'date': date_val}), 201

@app.route('/api/finance/reports/sda-monthly', methods=['GET'])
@login_required
@roles_required('PASTOR', 'FIRST_ELDER', 'HEAD_TREASURER', 'ASSISTANT_TREASURER', 'AUDITOR', 'AUTHORIZED_ELDER_READONLY')
def get_sda_monthly_report():
    conn = get_db_connection()
    items = conn.execute('''
        SELECT ei.amount, fc.name as fund_name, fc.code as fund_code, fc.fund_type, fc.is_remitted_to_conference
        FROM envelope_items ei
        JOIN tithe_offering_envelopes e ON ei.envelope_id = e.id
        JOIN fund_categories fc ON ei.fund_category_id = fc.id
        WHERE e.status = 'CONFIRMED'
    ''').fetchall()

    total_tithe = 0.0
    total_trust_funds = 0.0
    total_local_church_funds = 0.0
    fund_breakdown = {}

    for it in items:
        code = it['fund_code']
        amt = float(it['amount'])
        if code not in fund_breakdown:
            fund_breakdown[code] = {'name': it['fund_name'], 'type': it['fund_type'], 'remitted': bool(it['is_remitted_to_conference']), 'total': 0.0}
        fund_breakdown[code]['total'] += amt
        if code == 'TITHE': total_tithe += amt
        if it['fund_type'] == 'CONFERENCE_TRUST': total_trust_funds += amt
        else: total_local_church_funds += amt

    vouchers = conn.execute('''
        SELECT v.*, d.name as department_name FROM expenditure_vouchers v
        JOIN departments d ON v.department_id = d.id WHERE v.status = 'PAID' ORDER BY v.paid_at DESC
    ''').fetchall()

    total_expenditure = sum(float(v['amount']) for v in vouchers)
    conn.close()

    return jsonify({
        'conference_trust': {
            'total_tithe': total_tithe,
            'total_trust_funds': total_trust_funds,
            'remittance_due_to_conference': total_trust_funds,
            'status': 'READY_FOR_REMITTANCE'
        },
        'local_church': {
            'total_local_funds_collected': total_local_church_funds,
            'total_expenditure_paid': total_expenditure,
            'net_operating_surplus': total_local_church_funds - total_expenditure
        },
        'breakdown': list(fund_breakdown.values()),
        'disbursements': [dict(v) for v in vouchers]
    })

@app.route('/api/dashboard/overview', methods=['GET'])
@login_required
def get_dashboard_overview():
    is_officer = g.user['role'] in ['CHURCH_ADMIN', 'PASTOR', 'FIRST_ELDER', 'HEAD_TREASURER', 'ASSISTANT_TREASURER', 'DEPARTMENT_LEADER', 'AUDITOR', 'AUTHORIZED_ELDER_READONLY']
    conn = get_db_connection()

    total_members = conn.execute("SELECT COUNT(*) as c FROM members WHERE status = 'ACTIVE'").fetchone()['c']
    total_depts = conn.execute("SELECT COUNT(*) as c FROM departments").fetchone()['c']

    upcoming_events = conn.execute('SELECT title, location, start_date FROM events ORDER BY start_date ASC LIMIT 4').fetchall()
    recent_announcements = conn.execute('''
        SELECT a.id, a.title, a.content, a.category, a.is_pinned, a.created_at, u.full_name as author_name
        FROM announcements a JOIN users u ON a.author_id = u.id
        WHERE a.target_audience IN ('ALL', 'MEMBERS_ONLY')
        ORDER BY a.is_pinned DESC, a.created_at DESC LIMIT 3
    ''').fetchall()

    if not is_officer:
        member_id = g.user.get('member_id')
        user_phone = g.user.get('phone')
        my_giving_total = 0.0
        my_tithe_total = 0.0

        if member_id or user_phone:
            my_items = conn.execute('''
                SELECT ei.amount, fc.code as fund_code
                FROM envelope_items ei
                JOIN tithe_offering_envelopes e ON ei.envelope_id = e.id
                JOIN fund_categories fc ON ei.fund_category_id = fc.id
                WHERE e.member_id = ? AND e.status = 'CONFIRMED'
            ''', (member_id or '',)).fetchall()

            for it in my_items:
                my_giving_total += float(it['amount'])
                if it['fund_code'] == 'TITHE':
                    my_tithe_total += float(it['amount'])

        conn.close()
        return jsonify({
            'is_member_view': True,
            'summary': {
                'total_members': total_members,
                'total_departments': total_depts,
                'my_total_giving': my_giving_total,
                'my_total_tithe': my_tithe_total,
            },
            'announcements': [dict(a) for a in recent_announcements],
            'upcoming_events': [dict(ev) for ev in upcoming_events]
        })

    # OFFICER VIEW
    total_tithe = conn.execute('''
        SELECT COALESCE(SUM(ei.amount), 0) as s
        FROM envelope_items ei JOIN fund_categories fc ON ei.fund_category_id = fc.id
        JOIN tithe_offering_envelopes e ON ei.envelope_id = e.id
        WHERE fc.code = 'TITHE' AND e.status = 'CONFIRMED'
    ''').fetchone()['s']

    total_local = conn.execute('''
        SELECT COALESCE(SUM(ei.amount), 0) as s
        FROM envelope_items ei JOIN fund_categories fc ON ei.fund_category_id = fc.id
        JOIN tithe_offering_envelopes e ON ei.envelope_id = e.id
        WHERE fc.fund_type = 'LOCAL_CHURCH' AND e.status = 'CONFIRMED'
    ''').fetchone()['s']

    total_spent = conn.execute("SELECT COALESCE(SUM(amount), 0) as s FROM expenditure_vouchers WHERE status = 'PAID'").fetchone()['s']
    pending_treasurer = conn.execute("SELECT COUNT(*) as c FROM expenditure_vouchers WHERE status = 'SUBMITTED'").fetchone()['c']
    pending_elder = conn.execute("SELECT COUNT(*) as c FROM expenditure_vouchers WHERE status = 'TREASURER_REVIEWED'").fetchone()['c']

    funds = conn.execute('''
        SELECT fc.name, fc.fund_type, COALESCE(SUM(ei.amount), 0) as total
        FROM fund_categories fc LEFT JOIN envelope_items ei ON fc.id = ei.fund_category_id
        GROUP BY fc.id HAVING total > 0 ORDER BY total DESC
    ''').fetchall()

    recent_envelopes = conn.execute('''
        SELECT e.receipt_number, e.total_amount, e.payment_method, e.transaction_date,
               COALESCE(m.first_name || ' ' || m.last_name, e.donor_name) as donor
        FROM tithe_offering_envelopes e LEFT JOIN members m ON e.member_id = m.id
        ORDER BY e.transaction_date DESC LIMIT 5
    ''').fetchall()

    conn.close()

    return jsonify({
        'is_member_view': False,
        'summary': {
            'total_members': total_members,
            'total_departments': total_depts,
            'total_tithe': float(total_tithe),
            'total_local_church': float(total_local),
            'total_expenditure': float(total_spent),
            'net_local_reserve': float(total_local - total_spent),
            'pending_treasurer': pending_treasurer,
            'pending_elder': pending_elder
        },
        'fund_distribution': [dict(f) for f in funds],
        'recent_envelopes': [dict(e) for e in recent_envelopes],
        'upcoming_events': [dict(ev) for ev in upcoming_events],
        'announcements': [dict(a) for a in recent_announcements]
    })

@app.route('/api/finance/members/<member_id>/contributions', methods=['GET'])
@login_required
@roles_required('HEAD_TREASURER', 'ASSISTANT_TREASURER', 'PASTOR', 'FIRST_ELDER', 'AUDITOR', 'AUTHORIZED_ELDER_READONLY')
def get_member_contributions(member_id):
    conn = get_db_connection()
    member = conn.execute('SELECT * FROM members WHERE id = ?', (member_id,)).fetchone()
    if not member:
        conn.close()
        return jsonify({'error': 'Member not found'}), 404

    envelopes = conn.execute('''
        SELECT e.*
        FROM tithe_offering_envelopes e
        WHERE e.member_id = ? AND e.status = 'CONFIRMED'
        ORDER BY e.transaction_date DESC
    ''', (member_id,)).fetchall()

    result_envelopes = []
    totals_by_fund = {}
    grand_total = 0.0

    for env in envelopes:
        e_dict = dict(env)
        items = conn.execute('''
            SELECT ei.amount, fc.name as fund_name, fc.code as fund_code, fc.fund_type
            FROM envelope_items ei
            JOIN fund_categories fc ON ei.fund_category_id = fc.id
            WHERE ei.envelope_id = ?
        ''', (e_dict['id'],)).fetchall()
        e_dict['items'] = [dict(it) for it in items]
        for it in items:
            amt = float(it['amount'])
            grand_total += amt
            code = it['fund_code']
            if code not in totals_by_fund:
                totals_by_fund[code] = {'fund_name': it['fund_name'], 'fund_type': it['fund_type'], 'total': 0.0}
            totals_by_fund[code]['total'] += amt
        result_envelopes.append(e_dict)

    conn.close()
    return jsonify({
        'member': {
            'id': member['id'],
            'member_number': member['member_number'],
            'name': f"{member['first_name']} {member['last_name']}",
            'phone': member['phone'],
            'email': member['email']
        },
        'envelopes': result_envelopes,
        'totals_by_fund': list(totals_by_fund.values()),
        'grand_total': grand_total
    })

@app.route('/api/officers', methods=['GET'])
@login_required
def get_officers():
    conn = get_db_connection()
    officers = conn.execute('''
        SELECT id, full_name, role FROM users
        WHERE role != 'MEMBER' AND active = 1
        ORDER BY full_name ASC
    ''').fetchall()
    conn.close()
    return jsonify([dict(o) for o in officers])

@app.route('/api/users', methods=['GET'])
@login_required
@roles_required('PASTOR')
def get_all_users():
    conn = get_db_connection()
    users = conn.execute('''
        SELECT u.id, u.email, u.full_name, u.role, u.phone, u.active, u.member_id,
               m.member_number
        FROM users u
        LEFT JOIN members m ON u.member_id = m.id
        WHERE u.id != ?
        ORDER BY u.full_name ASC
    ''', (g.user['id'],)).fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])

@app.route('/api/users/<user_id>/role', methods=['PATCH'])
@login_required
@roles_required('PASTOR')
def assign_user_role(user_id):
    data = request.get_json() or {}
    new_role = data.get('role', '').strip()

    allowed_roles = ['MEMBER', 'FIRST_ELDER', 'HEAD_TREASURER', 'ASSISTANT_TREASURER',
                     'CHURCH_CLERK', 'DEPARTMENT_LEADER', 'AUDITOR', 'AUTHORIZED_ELDER_READONLY']
    if new_role not in allowed_roles:
        return jsonify({'error': 'Invalid role specified'}), 400

    conn = get_db_connection()
    user = conn.execute('SELECT id, full_name, role FROM users WHERE id = ? AND id != ?',
                        (user_id, g.user['id'])).fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'User not found'}), 404

    conn.execute('UPDATE users SET role = ? WHERE id = ?', (new_role, user_id))
    conn.commit()
    conn.close()

    create_audit_log(g.user['id'], 'ASSIGN_ROLE', 'User', user_id, {
        'target_user': user['full_name'],
        'old_role': user['role'],
        'new_role': new_role
    })
    return jsonify({'message': f"Role updated to {new_role} for {user['full_name']}", 'role': new_role})

@app.route('/api/audit-logs', methods=['GET'])
@login_required
@roles_required('PASTOR', 'FIRST_ELDER', 'HEAD_TREASURER', 'AUDITOR', 'CHURCH_ADMIN', 'AUTHORIZED_ELDER_READONLY')
def get_audit_logs():
    conn = get_db_connection()
    logs = conn.execute('''
        SELECT a.*, u.full_name as user_name, u.role as user_role, u.email as user_email
        FROM audit_logs a LEFT JOIN users u ON a.user_id = u.id
        ORDER BY a.created_at DESC LIMIT 100
    ''').fetchall()
    conn.close()
    return jsonify([dict(l) for l in logs])

# -------------------------------------------------------------
# Church Documents
# -------------------------------------------------------------
@app.route('/api/documents', methods=['GET'])
@login_required
def get_documents():
    conn = get_db_connection()
    query = '''
        SELECT d.*, u.full_name as uploaded_by_name
        FROM church_documents d
        LEFT JOIN users u ON d.uploaded_by_id = u.id
        WHERE 1=1
    '''
    if g.user['role'] == 'MEMBER':
        query += " AND d.audience = 'ALL'"
    query += ' ORDER BY d.created_at DESC'
    docs = conn.execute(query).fetchall()
    conn.close()
    return jsonify([dict(d) for d in docs])

@app.route('/api/documents', methods=['POST'])
@login_required
@roles_required('PASTOR', 'FIRST_ELDER', 'CHURCH_CLERK', 'HEAD_TREASURER', 'AUDITOR')
def create_document():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400
    title = data.get('title')
    category = data.get('category', 'GENERAL')
    description = data.get('description', '')
    file_content = data.get('file_content')
    audience = data.get('audience', 'OFFICERS')

    if not all(isinstance(value, str) for value in (title, category, description, file_content, audience)):
        return jsonify({'error': 'Document fields must be text.'}), 400
    title, category, description, audience = (value.strip() for value in (title, category, description, audience))
    if not title or not file_content.strip():
        return jsonify({'error': 'Title and content are required'}), 400
    if len(title) > 160 or len(description) > 1000 or len(file_content.encode('utf-8')) > 1_000_000:
        return jsonify({'error': 'Document title, description, or content exceeds the allowed size.'}), 413
    if category not in {'POLICY', 'MINUTES', 'CIRCULAR', 'FINANCIAL', 'GENERAL'} or audience not in {'ALL', 'OFFICERS'}:
        return jsonify({'error': 'Invalid document category or audience.'}), 400

    doc_id = 'doc-' + str(uuid.uuid4())[:8]
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO church_documents (id, title, category, description, file_content, audience, uploaded_by_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (doc_id, title, category, description, file_content, audience, g.user['id']))
    conn.commit()
    conn.close()
    create_audit_log(g.user['id'], 'UPLOAD_DOCUMENT', 'ChurchDocument', doc_id, {'title': title, 'category': category})
    return jsonify({'id': doc_id, 'title': title}), 201

@app.route('/api/documents/<doc_id>', methods=['DELETE'])
@login_required
@roles_required('PASTOR', 'CHURCH_CLERK')
def delete_document(doc_id):
    conn = get_db_connection()
    doc = conn.execute('SELECT * FROM church_documents WHERE id = ?', (doc_id,)).fetchone()
    if not doc:
        conn.close()
        return jsonify({'error': 'Document not found'}), 404
    conn.execute('DELETE FROM church_documents WHERE id = ?', (doc_id,))
    conn.commit()
    conn.close()
    create_audit_log(g.user['id'], 'DELETE_DOCUMENT', 'ChurchDocument', doc_id, {'title': doc['title']})
    return jsonify({'message': 'Document deleted'})

# -------------------------------------------------------------
# Departmental Activities
# -------------------------------------------------------------
@app.route('/api/departments/<dept_id>/activities', methods=['GET'])
@login_required
def get_dept_activities(dept_id):
    conn = get_db_connection()
    if not conn.execute('SELECT 1 FROM departments WHERE id = ?', (dept_id,)).fetchone():
        conn.close()
        return jsonify({'error': 'Department not found'}), 404
    activities = conn.execute('''
        SELECT a.*, u.full_name as recorded_by_name, d.name as department_name
        FROM departmental_activities a
        JOIN departments d ON a.department_id = d.id
        LEFT JOIN users u ON a.recorded_by_id = u.id
        WHERE a.department_id = ?
        ORDER BY a.activity_date DESC
    ''', (dept_id,)).fetchall()
    conn.close()
    return jsonify([dict(a) for a in activities])

@app.route('/api/departments/<dept_id>/activities', methods=['POST'])
@login_required
@roles_required('PASTOR', 'FIRST_ELDER', 'CHURCH_CLERK', 'DEPARTMENT_LEADER')
def create_dept_activity(dept_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400
    title = data.get('title')
    description = data.get('description', '')
    activity_date = data.get('activity_date', datetime.now().strftime('%Y-%m-%d'))
    outcome = data.get('outcome', '')
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
        return jsonify({'error': 'Activity title is required and must be 120 characters or fewer.'}), 400
    if not isinstance(description, str) or len(description) > 1000:
        return jsonify({'error': 'Activity description must be text of 1000 characters or fewer.'}), 400
    if not isinstance(outcome, str) or len(outcome) > 1000:
        return jsonify({'error': 'Activity outcome must be text of 1000 characters or fewer.'}), 400
    if not isinstance(activity_date, str):
        return jsonify({'error': 'Activity date must use YYYY-MM-DD format.'}), 400
    try:
        parsed_date = datetime.strptime(activity_date, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Activity date must use YYYY-MM-DD format.'}), 400
    if parsed_date.strftime('%Y-%m-%d') != activity_date:
        return jsonify({'error': 'Activity date must use YYYY-MM-DD format.'}), 400
    participants_value = data.get('participants_count', 0)
    if isinstance(participants_value, bool):
        return jsonify({'error': 'Participant count must be a whole number.'}), 400
    try:
        participants = int(participants_value)
    except (TypeError, ValueError):
        return jsonify({'error': 'Participant count must be a whole number.'}), 400
    if participants < 0:
        return jsonify({'error': 'Participant count cannot be negative.'}), 400

    conn = get_db_connection()
    dept = conn.execute('SELECT id, name, leader_id FROM departments WHERE id = ?', (dept_id,)).fetchone()
    if not dept:
        conn.close()
        return jsonify({'error': 'Department not found'}), 404
    if g.user['role'] == 'DEPARTMENT_LEADER' and (
        dept['leader_id'] != g.user['id'] or g.user.get('department_id') != dept_id
    ):
        conn.close()
        return jsonify({'error': 'Department leaders may only record activities for their own department.'}), 403

    title = title.strip()
    description = description.strip() or None
    outcome = outcome.strip() or None
    act_id = 'act-' + str(uuid.uuid4())[:8]
    conn.execute('''
        INSERT INTO departmental_activities (id, department_id, title, description, activity_date, participants_count, outcome, recorded_by_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (act_id, dept_id, title, description, activity_date, participants, outcome, g.user['id']))
    conn.commit()
    conn.close()
    create_audit_log(g.user['id'], 'RECORD_DEPT_ACTIVITY', 'DepartmentalActivity', act_id,
                     {'department': dept['name'], 'title': title, 'date': activity_date})
    return jsonify({'id': act_id, 'title': title}), 201

# -------------------------------------------------------------
# Member Status Management
# -------------------------------------------------------------
@app.route('/api/members/<member_id>/status', methods=['PATCH'])
@login_required
@roles_required('PASTOR', 'FIRST_ELDER', 'CHURCH_CLERK')
def update_member_status(member_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400
    new_status = data.get('status')
    reason = data.get('reason', '')

    valid_statuses = ['ACTIVE', 'INACTIVE', 'TRANSFERRED', 'DECEASED', 'DISFELLOWSHIPPED']
    if not isinstance(new_status, str) or new_status not in valid_statuses:
        return jsonify({'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}), 400
    if not isinstance(reason, str) or len(reason) > 500:
        return jsonify({'error': 'Status change reason must be text of 500 characters or fewer.'}), 400

    conn = get_db_connection()
    member = conn.execute('SELECT * FROM members WHERE id = ?', (member_id,)).fetchone()
    if not member:
        conn.close()
        return jsonify({'error': 'Member not found'}), 404

    if member['status'] == new_status:
        conn.close()
        return jsonify({'message': 'Member already has that status.', 'status': new_status})

    reason = reason.strip()
    hist_id = 'msh-' + str(uuid.uuid4())[:8]
    conn.execute('''
        INSERT INTO member_status_history (id, member_id, old_status, new_status, reason, changed_by_id)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (hist_id, member_id, member['status'], new_status, reason, g.user['id']))
    conn.execute('UPDATE members SET status = ? WHERE id = ?', (new_status, member_id))
    conn.commit()
    conn.close()
    create_audit_log(g.user['id'], 'UPDATE_MEMBER_STATUS', 'Member', member_id,
                     {'name': f"{member['first_name']} {member['last_name']}", 'old': member['status'], 'new': new_status, 'reason': reason})
    return jsonify({'message': f"Member status updated to {new_status}", 'status': new_status})

@app.route('/api/members/<member_id>/status-history', methods=['GET'])
@login_required
@roles_required('PASTOR', 'FIRST_ELDER', 'CHURCH_CLERK', 'AUDITOR')
def get_member_status_history(member_id):
    conn = get_db_connection()
    if not conn.execute('SELECT 1 FROM members WHERE id = ?', (member_id,)).fetchone():
        conn.close()
        return jsonify({'error': 'Member not found'}), 404
    history = conn.execute('''
        SELECT h.*, u.full_name as changed_by_name
        FROM member_status_history h
        LEFT JOIN users u ON h.changed_by_id = u.id
        WHERE h.member_id = ?
        ORDER BY h.created_at DESC
    ''', (member_id,)).fetchall()
    conn.close()
    return jsonify([dict(h) for h in history])

# -------------------------------------------------------------
# Notifications
# -------------------------------------------------------------
@app.route('/api/notifications', methods=['GET'])
@login_required
def get_notifications():
    conn = get_db_connection()
    notes = conn.execute('''
        SELECT * FROM notifications WHERE user_id = ?
        ORDER BY created_at DESC LIMIT 30
    ''', (g.user['id'],)).fetchall()
    unread = conn.execute('SELECT COUNT(*) as c FROM notifications WHERE user_id = ? AND is_read = 0', (g.user['id'],)).fetchone()['c']
    conn.close()
    return jsonify({'notifications': [dict(n) for n in notes], 'unread_count': unread})

@app.route('/api/notifications/mark-read', methods=['POST'])
@login_required
def mark_notifications_read():
    conn = get_db_connection()
    conn.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (g.user['id'],))
    conn.commit()
    conn.close()
    return jsonify({'message': 'All notifications marked as read'})

# -------------------------------------------------------------
# Annual Financial Report
# -------------------------------------------------------------
@app.route('/api/finance/reports/annual', methods=['GET'])
@login_required
@roles_required('PASTOR', 'FIRST_ELDER', 'HEAD_TREASURER', 'ASSISTANT_TREASURER', 'AUDITOR', 'AUTHORIZED_ELDER_READONLY')
def get_annual_report():
    year = request.args.get('year', datetime.now().year)
    conn = get_db_connection()

    monthly_giving = conn.execute('''
        SELECT strftime('%m', e.transaction_date) as month,
               fc.fund_type,
               COALESCE(SUM(ei.amount), 0) as total
        FROM envelope_items ei
        JOIN tithe_offering_envelopes e ON ei.envelope_id = e.id
        JOIN fund_categories fc ON ei.fund_category_id = fc.id
        WHERE strftime('%Y', e.transaction_date) = ? AND e.status = 'CONFIRMED'
        GROUP BY month, fc.fund_type
        ORDER BY month ASC
    ''', (str(year),)).fetchall()

    monthly_expenditure = conn.execute('''
        SELECT strftime('%m', paid_at) as month, COALESCE(SUM(amount), 0) as total
        FROM expenditure_vouchers
        WHERE strftime('%Y', paid_at) = ? AND status = 'PAID'
        GROUP BY month ORDER BY month ASC
    ''', (str(year),)).fetchall()

    top_funds = conn.execute('''
        SELECT fc.name, fc.code, fc.fund_type, COALESCE(SUM(ei.amount), 0) as total
        FROM fund_categories fc
        LEFT JOIN envelope_items ei ON fc.id = ei.fund_category_id
        LEFT JOIN tithe_offering_envelopes e ON ei.envelope_id = e.id
        WHERE (e.status = 'CONFIRMED' OR e.id IS NULL)
          AND (strftime('%Y', e.transaction_date) = ? OR e.id IS NULL)
        GROUP BY fc.id ORDER BY total DESC
    ''', (str(year),)).fetchall()

    dept_expenditure = conn.execute('''
        SELECT d.name, d.code, COALESCE(SUM(v.amount), 0) as total_spent
        FROM departments d
        LEFT JOIN expenditure_vouchers v ON d.id = v.department_id
        WHERE v.status = 'PAID' AND strftime('%Y', v.paid_at) = ?
        GROUP BY d.id ORDER BY total_spent DESC
    ''', (str(year),)).fetchall()

    totals = conn.execute('''
        SELECT
            COALESCE(SUM(CASE WHEN fc.fund_type = 'CONFERENCE_TRUST' THEN ei.amount ELSE 0 END), 0) as conference_total,
            COALESCE(SUM(CASE WHEN fc.fund_type = 'LOCAL_CHURCH' THEN ei.amount ELSE 0 END), 0) as local_total,
            COALESCE(SUM(ei.amount), 0) as grand_total
        FROM envelope_items ei
        JOIN tithe_offering_envelopes e ON ei.envelope_id = e.id
        JOIN fund_categories fc ON ei.fund_category_id = fc.id
        WHERE strftime('%Y', e.transaction_date) = ? AND e.status = 'CONFIRMED'
    ''', (str(year),)).fetchone()

    total_paid = conn.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM expenditure_vouchers WHERE status='PAID' AND strftime('%Y', paid_at) = ?",
        (str(year),)).fetchone()['s']

    conn.close()
    return jsonify({
        'year': year,
        'totals': dict(totals),
        'total_expenditure': float(total_paid),
        'net_surplus': float(totals['local_total']) - float(total_paid),
        'monthly_giving': [dict(m) for m in monthly_giving],
        'monthly_expenditure': [dict(m) for m in monthly_expenditure],
        'fund_breakdown': [dict(f) for f in top_funds],
        'department_expenditure': [dict(d) for d in dept_expenditure]
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() in ('1', 'true', 'yes')
    app.run(host='0.0.0.0', port=port, debug=debug)
