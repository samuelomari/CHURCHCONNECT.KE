import os
import unittest
import json
import tempfile

# Set environment before importing app
tmp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
os.environ['DATABASE_FILE'] = tmp_db.name
os.environ['SECRET_KEY'] = 'test_secret_key'
os.environ['JWT_SECRET'] = 'test_jwt_secret'

from app import app
from database import get_db_connection, init_db
from seed import seed_database

class ChurchConnectTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_database()
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(tmp_db.name)
        except Exception:
            pass

    def get_token(self, email, password='password123'):
        res = self.client.post('/api/auth/login', json={
            'email': email,
            'password': password
        })
        data = res.get_json()
        return data.get('token')

    def test_01_login_success_and_failure(self):
        token = self.get_token('pastor@churchconnect.ke')
        self.assertIsNotNone(token)

        res = self.client.post('/api/auth/login', json={
            'email': 'pastor@churchconnect.ke',
            'password': 'wrongpassword'
        })
        self.assertEqual(res.status_code, 401)

    def test_02_member_registration_validation(self):
        # 1. Invalid email format
        res_bad_email = self.client.post('/api/auth/register', json={
            'email': 'not-an-email',
            'password': 'Password123',
            'full_name': 'Test User',
            'phone': '254700112233'
        })
        self.assertEqual(res_bad_email.status_code, 400)
        self.assertIn('valid email', res_bad_email.get_json()['error'])

        # 2. Weak password (missing uppercase/digit or too short)
        res_weak_pw = self.client.post('/api/auth/register', json={
            'email': 'valid.member@test.ke',
            'password': 'short',
            'full_name': 'Test User',
            'phone': '254700112233'
        })
        self.assertEqual(res_weak_pw.status_code, 400)
        self.assertIn('Password must be at least 8 characters', res_weak_pw.get_json()['error'])

        # 3. Successful registration
        res_success = self.client.post('/api/auth/register', json={
            'email': 'new.member@sda.ke',
            'password': 'SecurePassword123',
            'full_name': 'Linet Kemunto',
            'phone': '254700998877',
            'member_number': 'SDA-2026-099'
        })
        self.assertEqual(res_success.status_code, 201)
        data = res_success.get_json()
        self.assertIn('token', data)
        self.assertEqual(data['user']['role'], 'MEMBER')

    def test_03_member_non_confidential_access_and_security_blocking(self):
        # Login as registered member John Kariuki
        member_token = self.get_token('john.k@gmail.com')
        headers = {'Authorization': f'Bearer {member_token}'}

        # 1. Allowed non-confidential: announcements
        res_ann = self.client.get('/api/announcements', headers=headers)
        self.assertEqual(res_ann.status_code, 200)
        self.assertIsInstance(res_ann.get_json(), list)

        # 2. Allowed non-confidential: events
        res_evt = self.client.get('/api/events', headers=headers)
        self.assertEqual(res_evt.status_code, 200)

        # 3. Allowed: personal giving history
        res_giving = self.client.get('/api/finance/my-giving', headers=headers)
        self.assertEqual(res_giving.status_code, 200)
        giving_data = res_giving.get_json()
        self.assertIn('envelopes', giving_data)

        # 4. BLOCKED: Confidential church-wide envelopes (Treasury only) -> 403 Forbidden
        res_env = self.client.get('/api/finance/envelopes', headers=headers)
        self.assertEqual(res_env.status_code, 403)

        # 5. BLOCKED: Confidential vouchers approval list -> 403 Forbidden
        res_vch = self.client.get('/api/finance/vouchers', headers=headers)
        self.assertEqual(res_vch.status_code, 403)

        # 6. BLOCKED: System audit logs -> 403 Forbidden
        res_audit = self.client.get('/api/audit-logs', headers=headers)
        self.assertEqual(res_audit.status_code, 403)

        # 7. BLOCKED: SDA Monthly Report -> 403 Forbidden
        res_rep = self.client.get('/api/finance/reports/sda-monthly', headers=headers)
        self.assertEqual(res_rep.status_code, 403)

    def test_04_record_tithe_offering_envelope(self):
        treasurer_token = self.get_token('treasurer@churchconnect.ke')
        headers = {'Authorization': f'Bearer {treasurer_token}'}

        payload = {
            'member_id': 'mem-001',
            'donor_name': 'John Kariuki',
            'payment_method': 'CASH',
            'items': [
                {'fund_category_id': 'fund-tithe', 'amount': 12000.0},
                {'fund_category_id': 'fund-budget', 'amount': 3000.0}
            ]
        }
        res = self.client.post('/api/finance/envelopes', headers=headers, json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data['receipt_number'].startswith('REC-'))
        self.assertEqual(data['total_amount'], 15000.0)

    def test_05_dual_approval_voucher_workflow(self):
        youth_token = self.get_token('youth.leader@churchconnect.ke')
        treasurer_token = self.get_token('treasurer@churchconnect.ke')
        elder_token = self.get_token('elder.samuel@churchconnect.ke')

        # 1. Youth Leader submits requisition
        res_vch = self.client.post('/api/finance/vouchers', headers={'Authorization': f'Bearer {youth_token}'}, json={
            'department_id': 'dept-ay',
            'title': 'Pathfinder Camping Supplies',
            'description': 'Tents and first aid kits',
            'amount': 5000.0,
            'payee_name': 'Scout Supplies Ltd',
            'payment_method': 'MPESA'
        })
        self.assertEqual(res_vch.status_code, 201)
        vch_id = res_vch.get_json()['id']

        # 2. Treasurer reviews voucher (Step 1)
        res_rev = self.client.post(f'/api/finance/vouchers/{vch_id}/treasurer-review', headers={'Authorization': f'Bearer {treasurer_token}'}, json={
            'action': 'APPROVE',
            'notes': 'Budget available.'
        })
        self.assertEqual(res_rev.status_code, 200)
        self.assertEqual(res_rev.get_json()['status'], 'TREASURER_REVIEWED')

        # 3. First Elder authorizes voucher (Step 2)
        res_app = self.client.post(f'/api/finance/vouchers/{vch_id}/elder-approve', headers={'Authorization': f'Bearer {elder_token}'}, json={
            'action': 'APPROVE',
            'notes': 'Board approved.'
        })
        self.assertEqual(res_app.status_code, 200)
        self.assertEqual(res_app.get_json()['status'], 'ELDER_APPROVED')

        # 4. Treasurer disburses payment
        res_disb = self.client.post(f'/api/finance/vouchers/{vch_id}/disburse', headers={'Authorization': f'Bearer {treasurer_token}'}, json={
            'payment_method': 'MPESA',
            'payment_reference': 'MP-B2C-998877'
        })
        self.assertEqual(res_disb.status_code, 200)
        self.assertEqual(res_disb.get_json()['status'], 'PAID')

    def test_06_budget_overspend_prevention(self):
        youth_token = self.get_token('youth.leader@churchconnect.ke')
        res = self.client.post('/api/finance/vouchers', headers={'Authorization': f'Bearer {youth_token}'}, json={
            'department_id': 'dept-ay',
            'title': 'Extravagant Bus Purchase',
            'description': 'Beyond budget',
            'amount': 5000000.0,
            'payee_name': 'Auto Dealers',
            'payment_method': 'BANK_TRANSFER'
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('Insufficient department budget', res.get_json()['error'])

    def test_07_mpesa_daraja_simulation(self):
        elder_token = self.get_token('elder.samuel@churchconnect.ke')
        res = self.client.post('/api/mpesa/simulate', headers={'Authorization': f'Bearer {elder_token}'}, json={
            'phone': '254710111222',
            'amount': 4500.0,
            'account_reference': 'SDA-2023-001',
            'donor_name': 'John Kariuki',
            'fund_code': 'TITHE'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertTrue(data['mpesa_receipt'].startswith('QA'))
        self.assertTrue(data['church_receipt'].startswith('REC-'))

    def test_08_brute_force_lockout_protection(self):
        # Create a test account to test brute force lockout
        self.client.post('/api/auth/register', json={
            'email': 'lockout.target@churchconnect.ke',
            'password': 'CorrectPassword123',
            'full_name': 'Lockout Target',
            'phone': '254700000009'
        })

        # Send 5 incorrect password attempts
        for i in range(5):
            res = self.client.post('/api/auth/login', json={
                'email': 'lockout.target@churchconnect.ke',
                'password': f'WrongAttempt{i}'
            })

        # The 5th attempt or subsequent attempt must result in 429 Account Locked
        res_locked = self.client.post('/api/auth/login', json={
            'email': 'lockout.target@churchconnect.ke',
            'password': 'CorrectPassword123'
        })
        self.assertEqual(res_locked.status_code, 429)
        self.assertIn('Account locked', res_locked.get_json()['error'])

    def test_09_clerk_creates_department_and_assigns_leader(self):
        member_token = self.get_token('john.k@gmail.com')
        denied = self.client.post('/api/departments', headers={
            'Authorization': f'Bearer {member_token}'
        }, json={
            'name': 'Community Outreach',
            'code': 'OUTREACH',
            'leader_id': 'usr-member-john'
        })
        self.assertEqual(denied.status_code, 403)

        clerk_token = self.get_token('clerk@churchconnect.ke')
        headers = {'Authorization': f'Bearer {clerk_token}'}
        candidates = self.client.get('/api/departments/leader-candidates', headers=headers)
        self.assertEqual(candidates.status_code, 200)
        self.assertIn('usr-member-john', [user['id'] for user in candidates.get_json()])

        created = self.client.post('/api/departments', headers=headers, json={
            'name': 'Community Outreach',
            'code': 'outreach',
            'description': 'Local service and community outreach',
            'leader_id': 'usr-member-john'
        })
        self.assertEqual(created.status_code, 201)
        department = created.get_json()
        self.assertEqual(department['code'], 'OUTREACH')
        self.assertEqual(department['leader_id'], 'usr-member-john')
        self.assertEqual(department['leader_name'], 'John Kariuki')

        leader_login = self.client.post('/api/auth/login', json={
            'email': 'john.k@gmail.com',
            'password': 'password123'
        })
        leader = leader_login.get_json()['user']
        self.assertEqual(leader['role'], 'DEPARTMENT_LEADER')
        self.assertEqual(leader['department_id'], department['id'])

        conn = get_db_connection()
        member = conn.execute(
            'SELECT department_id FROM members WHERE id = ?',
            ('mem-001',)
        ).fetchone()
        conn.close()
        self.assertEqual(member['department_id'], department['id'])

        updated_candidates = self.client.get('/api/departments/leader-candidates', headers=headers)
        self.assertNotIn('usr-member-john', [user['id'] for user in updated_candidates.get_json()])

        reused_leader = self.client.post('/api/departments', headers=headers, json={
            'name': 'Another Outreach Department',
            'code': 'OUTREACH2',
            'leader_id': 'usr-member-john'
        })
        self.assertEqual(reused_leader.status_code, 400)

        duplicate = self.client.post('/api/departments', headers=headers, json={
            'name': 'Another Department',
            'code': 'OUTREACH',
            'leader_id': 'usr-member-john'
        })
        self.assertEqual(duplicate.status_code, 409)

    def test_10_clerk_can_update_department_and_reassign_leader(self):
        registration = self.client.post('/api/auth/register', json={
            'email': 'new.leader@churchconnect.ke',
            'password': 'SecurePassword123',
            'full_name': 'New Department Leader',
            'phone': '254700000011'
        })
        self.assertEqual(registration.status_code, 201)
        leader_id = registration.get_json()['user']['id']
        clerk_token = self.get_token('clerk@churchconnect.ke')
        headers = {'Authorization': f'Bearer {clerk_token}'}

        updated = self.client.patch('/api/departments/dept-ay', headers=headers, json={
            'description': 'Youth ministry and community service',
            'leader_id': leader_id
        })
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()['leader_id'], leader_id)
        self.assertEqual(updated.get_json()['leader_name'], 'New Department Leader')

        new_leader = self.client.post('/api/auth/login', json={
            'email': 'new.leader@churchconnect.ke',
            'password': 'SecurePassword123'
        }).get_json()['user']
        self.assertEqual(new_leader['role'], 'DEPARTMENT_LEADER')
        self.assertEqual(new_leader['department_id'], 'dept-ay')

        previous_leader = self.client.post('/api/auth/login', json={
            'email': 'youth.leader@churchconnect.ke',
            'password': 'password123'
        }).get_json()['user']
        self.assertEqual(previous_leader['role'], 'MEMBER')

    def test_11_department_activity_tracking_and_leader_scope(self):
        clerk_token = self.get_token('clerk@churchconnect.ke')
        response = self.client.post('/api/departments/dept-ay/activities', headers={
            'Authorization': f'Bearer {clerk_token}'
        }, json={
            'title': 'Youth Community Service',
            'description': 'Clean-up and food distribution',
            'activity_date': '2026-10-25',
            'participants_count': 18,
            'outcome': 'Three streets served'
        })
        self.assertEqual(response.status_code, 201)
        activities = self.client.get('/api/departments/dept-ay/activities', headers={
            'Authorization': f'Bearer {clerk_token}'
        })
        self.assertEqual(activities.status_code, 200)
        self.assertEqual(activities.get_json()[0]['title'], 'Youth Community Service')
        self.assertEqual(activities.get_json()[0]['participants_count'], 18)

        leader_token = self.get_token('youth.leader@churchconnect.ke')
        denied = self.client.post('/api/departments/dept-wm/activities', headers={
            'Authorization': f'Bearer {leader_token}'
        }, json={'title': 'Out of scope activity'})
        self.assertEqual(denied.status_code, 403)

        invalid_count = self.client.post('/api/departments/dept-ay/activities', headers={
            'Authorization': f'Bearer {clerk_token}'
        }, json={'title': 'Invalid participants', 'participants_count': -1})
        self.assertEqual(invalid_count.status_code, 400)

    def test_12_member_filters_and_status_history(self):
        clerk_token = self.get_token('clerk@churchconnect.ke')
        headers = {'Authorization': f'Bearer {clerk_token}'}
        changed = self.client.patch('/api/members/mem-002/status', headers=headers, json={
            'status': 'TRANSFERRED',
            'reason': 'Transferred to another congregation'
        })
        self.assertEqual(changed.status_code, 200)

        filtered = self.client.get('/api/members?search=Esther&status=TRANSFERRED&department_id=dept-wm', headers=headers)
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual([member['id'] for member in filtered.get_json()], ['mem-002'])
        history = self.client.get('/api/members/mem-002/status-history', headers=headers)
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.get_json()[0]['new_status'], 'TRANSFERRED')
        self.assertEqual(history.get_json()[0]['reason'], 'Transferred to another congregation')

    def test_13_event_attendance_linkage_and_validation(self):
        clerk_token = self.get_token('clerk@churchconnect.ke')
        headers = {'Authorization': f'Bearer {clerk_token}'}
        event = self.client.post('/api/events', headers=headers, json={
            'title': 'Community Health Sabbath',
            'description': 'Health screening and wellness education',
            'location': 'Church Hall',
            'start_date': '2026-11-07T09:00',
            'end_date': '2026-11-07T13:00',
            'department_id': 'dept-welfare'
        })
        self.assertEqual(event.status_code, 201)
        event_id = event.get_json()['id']

        attendance = self.client.post('/api/attendance', headers=headers, json={
            'service_type': 'SPECIAL_EVENT',
            'date': '2026-11-07',
            'event_id': event_id,
            'adult_count': 32,
            'children_count': 8,
            'visitors_count': 5,
            'notes': 'Community health outreach'
        })
        self.assertEqual(attendance.status_code, 201)
        self.assertEqual(attendance.get_json()['total_count'], 45)

        records = self.client.get(f'/api/attendance?event_id={event_id}&service_type=SPECIAL_EVENT', headers=headers)
        self.assertEqual(records.status_code, 200)
        self.assertEqual(records.get_json()[0]['event_title'], 'Community Health Sabbath')
        self.assertEqual(records.get_json()[0]['total_count'], 45)

        invalid_event = self.client.post('/api/events', headers=headers, json={
            'title': 'Invalid date order',
            'location': 'Church',
            'start_date': '2026-11-08T14:00',
            'end_date': '2026-11-08T13:00'
        })
        self.assertEqual(invalid_event.status_code, 400)

        invalid_attendance = self.client.post('/api/attendance', headers=headers, json={
            'service_type': 'DIVINE_SERVICE',
            'date': '2026-11-08',
            'adult_count': -1
        })
        self.assertEqual(invalid_attendance.status_code, 400)

if __name__ == '__main__':
    unittest.main()
