from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import timedelta
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_for_local_testing')
app.config['MONGO_URI'] = os.environ.get(
    'MONGO_URI',
    'mongodb+srv://Muneesh:MI5y8ckbp7QUtTGs@cluster0.vpnqgja.mongodb.net/hosteldb?retryWrites=true&w=majority&appName=Cluster0'
)
app.permanent_session_lifetime = timedelta(minutes=30)
COLLEGE_KEY = 'Rec#1234'

mongo = PyMongo(app)

students = mongo.db.students
wardens = mongo.db.wardens
rooms = mongo.db.rooms
room_requests = mongo.db.room_requests

def get_vacancy(room_doc):
    """Return remaining vacancy count for a room document."""
    if not room_doc:
        return 0
    return int(room_doc.get('vacancies', 0)) - len(room_doc.get('students', []))


def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'user' not in session:
                flash('Login required')
                return redirect(url_for('index'))
            if role and session.get('role') != role:
                flash('Unauthorized')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return wrapper
    return decorator

@app.route('/')
def index():
    return render_template('index.html')

# ---------------- Student routes ----------------
@app.route('/student/register', methods=['GET','POST'])
def student_register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        pwd = request.form.get('password', '')
        if not (name and email and pwd):
            flash('Please fill all fields')
            return redirect(url_for('student_register'))
        if students.find_one({'email': email}):
            flash('Student already registered')
            return redirect(url_for('student_register'))
        students.insert_one({
            'name': name,
            'email': email,
            'password': generate_password_hash(pwd),
            'approved': False,
            'room_id': None
        })
        flash('Registered. Wait for warden approval.')
        return redirect(url_for('index'))
    return render_template('student_register.html')


@app.route('/student/login', methods=['GET','POST'])
def student_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pwd = request.form.get('password', '')
        s = students.find_one({'email': email})
        if not s or not check_password_hash(s['password'], pwd):
            flash('Invalid credentials')
            return redirect(url_for('student_login'))
        if not s.get('approved', False):
            flash('Account not approved by warden yet')
            return redirect(url_for('index'))
        session.permanent = True
        session['user'] = str(s['_id'])
        session['role'] = 'student'
        flash('Logged in as student')
        return redirect(url_for('student_dashboard'))
    return render_template('student_login.html')


@app.route('/student/dashboard')
@login_required('student')
def student_dashboard():
    s = students.find_one({'_id': ObjectId(session['user'])})
    room = None
    if s and s.get('room_id'):
        try:
            room = rooms.find_one({'_id': ObjectId(s['room_id'])})
        except Exception:
            room = None
    return render_template('student_dashboard.html', student=s, room=room)


@app.route('/student/rooms', methods=['GET','POST'])
@login_required('student')
def student_rooms():
    # Expect query params: ac = 'any'|'ac'|'non-ac', room_type = 'any' or specific
    ac_filter = request.args.get('ac', 'any')
    rtype_filter = request.args.get('room_type', 'any')

    all_rooms = []
    for r in rooms.find():
        vac = get_vacancy(r)
        if vac <= 0:
            continue
        ac_type = r.get('ac_type', '').lower()
        if ac_filter == 'ac' and ac_type != 'ac':
            continue
        if ac_filter == 'non-ac' and ac_type == 'ac':
            continue
        if rtype_filter and rtype_filter != 'any' and r.get('room_type','').lower() != rtype_filter.lower():
            continue
        all_rooms.append({
            '_id': str(r['_id']),
            'room_no': r.get('room_no'),
            'room_type': r.get('room_type'),
            'ac_type': r.get('ac_type'),
            'vacancies': r.get('vacancies'),
            'current_students': len(r.get('students', [])),
            'available': vac
        })

    if request.method == 'POST':
        room_id = request.form.get('room_id')
        student_id = session['user']
        # Prevent multiple pending requests from same student
        existing = room_requests.find_one({'student_id': ObjectId(student_id), 'status': 'pending'})
        if existing:
            flash('You already have a pending room request.')
            return redirect(url_for('student_dashboard'))
        room_requests.insert_one({
            'student_id': ObjectId(student_id),
            'room_id': ObjectId(room_id),
            'status': 'pending'
        })
        flash('Room request submitted. Wait for warden approval.')
        return redirect(url_for('student_dashboard'))

    return render_template('room_registration.html', rooms=all_rooms, ac_checked=(ac_filter=='ac'), selected_type=(rtype_filter or 'any'))


@app.route('/student/rooms/filter')
@login_required('student')
def student_rooms_filter():
    # helper that returns JSON filtered rooms (can be used via AJAX)
    ac_filter = request.args.get('ac', 'any')
    rtype_filter = request.args.get('room_type', 'any')
    filtered_rooms = []
    for r in rooms.find():
        vac = get_vacancy(r)
        if vac <= 0:
            continue
        ac_type = r.get('ac_type','').lower()
        if ac_filter == 'ac' and ac_type != 'ac':
            continue
        if ac_filter == 'non-ac' and ac_type == 'ac':
            continue
        if rtype_filter != 'any' and r.get('room_type','').lower() != rtype_filter.lower():
            continue
        filtered_rooms.append({
            '_id': str(r['_id']),
            'room_no': r.get('room_no'),
            'room_type': r.get('room_type'),
            'ac_type': r.get('ac_type'),
            'vacancies': r.get('vacancies'),
            'available': get_vacancy(r)
        })
    return {'rooms': filtered_rooms}

# ---------------- Warden routes ----------------
@app.route('/warden/register', methods=['GET','POST'])
def warden_register():
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        email = request.form.get('email','').strip().lower()
        pwd = request.form.get('password','')
        college_key = request.form.get('college_key','')
        if college_key != COLLEGE_KEY:
            flash('Invalid college key')
            return redirect(url_for('warden_register'))
        if wardens.find_one({'email': email}):
            flash('Warden already exists')
            return redirect(url_for('warden_register'))
        wardens.insert_one({'name': name, 'email': email, 'password': generate_password_hash(pwd)})
        flash('Warden registered. Please login.')
        return redirect(url_for('index'))
    return render_template('warden_register.html')


@app.route('/warden/login', methods=['GET','POST'])
def warden_login():
    if request.method == 'POST':
        email = request.form.get('email','').strip().lower()
        pwd = request.form.get('password','')
        w = wardens.find_one({'email': email})
        if not w or not check_password_hash(w['password'], pwd):
            flash('Invalid credentials')
            return redirect(url_for('warden_login'))
        session.permanent = True
        session['user'] = str(w['_id'])
        session['role'] = 'warden'
        flash('Logged in as warden')
        return redirect(url_for('warden_dashboard'))
    return render_template('warden_login.html')


@app.route('/warden/dashboard')
@login_required('warden')
def warden_dashboard():
    pending_students = list(students.find({'approved': False}))
    pending_room_requests = list(room_requests.find({'status': 'pending'}))
    enriched = []
    for req in pending_room_requests:
        student = students.find_one({'_id': req['student_id']}) if isinstance(req.get('student_id'), ObjectId) else students.find_one({'_id': ObjectId(req['student_id'])})
        room = rooms.find_one({'_id': req['room_id']}) if isinstance(req.get('room_id'), ObjectId) else rooms.find_one({'_id': ObjectId(req['room_id'])})
        enriched.append({'req': req, 'student': student, 'room': room})

    room_list = []
    for r in rooms.find():
        room_list.append({
            '_id': str(r['_id']),
            'room_no': r.get('room_no'),
            'room_type': r.get('room_type'),
            'ac_type': r.get('ac_type'),
            'vacancies': r.get('vacancies'),
            'current_students': len(r.get('students', [])),
            'available': get_vacancy(r)
        })

    return render_template('warden_dashboard.html', pending_students=pending_students, requests=enriched, rooms=room_list)


@app.route('/warden/approve_student/<sid>')
@login_required('warden')
def approve_student(sid):
    students.update_one({'_id': ObjectId(sid)}, {'$set': {'approved': True}})
    flash('Student approved')
    return redirect(url_for('warden_dashboard'))


@app.route('/warden/approve_request/<rid>')
@login_required('warden')
def approve_request(rid):
    req = room_requests.find_one({'_id': ObjectId(rid)})
    if not req:
        flash('Request not found')
        return redirect(url_for('warden_dashboard'))
    # Ensure we fetch the latest room doc and vacancy
    room = rooms.find_one({'_id': req['room_id']}) if isinstance(req.get('room_id'), ObjectId) else rooms.find_one({'_id': ObjectId(req['room_id'])})
    if not room:
        flash('Room not found')
        return redirect(url_for('warden_dashboard'))
    if get_vacancy(room) <= 0:
        room_requests.update_one({'_id': req['_id']}, {'$set': {'status': 'rejected', 'reason': 'No vacancy'}})
        flash('No vacancy, request rejected')
        return redirect(url_for('warden_dashboard'))
    # Push student into room and set student's room_id
    rooms.update_one({'_id': room['_id']}, {'$push': {'students': req['student_id']}})
    students.update_one({'_id': req['student_id']}, {'$set': {'room_id': str(room['_id'])}})
    room_requests.update_one({'_id': req['_id']}, {'$set': {'status': 'approved'}})
    flash('Room request approved and assigned')
    return redirect(url_for('warden_dashboard'))


@app.route('/warden/reject_request/<rid>')
@login_required('warden')
def reject_request(rid):
    room_requests.update_one({'_id': ObjectId(rid)}, {'$set': {'status': 'rejected'}})
    flash('Request rejected')
    return redirect(url_for('warden_dashboard'))


@app.route('/warden/room/add', methods=['GET','POST'])
@login_required('warden')
def room_add():
    if request.method == 'POST':
        room_no = request.form.get('room_no','').strip()
        room_type = request.form.get('room_type','').strip()
        ac_type = request.form.get('ac_type','').strip()
        try:
            vacancies = int(request.form.get('vacancies', 0))
        except ValueError:
            vacancies = 0
        if not room_no:
            flash('Room number required')
            return redirect(url_for('warden_dashboard'))
        rooms.insert_one({
            'room_no': room_no,
            'room_type': room_type,
            'ac_type': ac_type,
            'vacancies': vacancies,
            'students': []
        })
        flash('Room added')
        return redirect(url_for('warden_dashboard'))
    return render_template('room_edit.html')


@app.route('/warden/room/edit/<room_id>', methods=['GET','POST'])
@login_required('warden')
def room_edit(room_id):
    r = rooms.find_one({'_id': ObjectId(room_id)})
    if not r:
        flash('Room not found')
        return redirect(url_for('warden_dashboard'))
    if request.method == 'POST':
        room_no = request.form.get('room_no','').strip()
        room_type = request.form.get('room_type','').strip()
        ac_type = request.form.get('ac_type','').strip()
        try:
            vacancies = int(request.form.get('vacancies', r.get('vacancies',0)))
        except ValueError:
            vacancies = r.get('vacancies',0)
        students_list = r.get('students', [])
        if len(students_list) > vacancies:
            flash('Vacancies less than current students; remove students first')
            return redirect(url_for('warden_dashboard'))
        rooms.update_one({'_id': r['_id']}, {'$set': {
            'room_no': room_no,
            'room_type': room_type,
            'ac_type': ac_type,
            'vacancies': vacancies
        }})
        flash('Room updated')
        return redirect(url_for('warden_dashboard'))
    return render_template('room_edit.html', room=r)

# ---------------- Common ----------------
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out')
    return redirect(url_for('index'))

# ---------------- AI BOT FEATURE (Warden Assistant) ----------------
import cohere
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import jsonify

COHERE_API_KEY = "o683w4VvCMRvuCrz71ymHiylSpWX1jIJxZel1sPY"
COHERE_MODEL = "command-a-03-2025"
co = cohere.Client(COHERE_API_KEY)

# Configure sender email (Gmail)
SENDER_EMAIL = "220701175@rajalakshmi.edu.in"  # change this
SENDER_PASSWORD = "moue nyue baxv rpdr"  # Gmail app password

@app.route('/warden/ai_bot')
@login_required('warden')
def ai_bot_page():
    return render_template('ai_bot.html')

@app.route('/warden/ai_generate', methods=['POST'])
@login_required('warden')
def ai_generate():
    data = request.json
    prompt = data.get('prompt', '')
    try:
        response = co.chat(
            model=COHERE_MODEL,
            message=prompt+" without any subject and wishes just the elaborate my content don't ask for any input just give a short notice",          # <-- New format
            temperature=0.7
        )
        text = response.text.strip()
        return jsonify({"text": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/warden/send_notice', methods=['POST'])
@login_required('warden')
def send_notice():
    data = request.json
    message_body = data.get('message', '')
    try:
        # Fetch all student emails dynamically from MongoDB
        student_docs = students.find({"approved": True})
        recipient_emails = [s["email"] for s in student_docs if "email" in s]

        if not recipient_emails:
            return jsonify({"error": "No approved students found"}), 400

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)

        for email in recipient_emails:
            msg = MIMEMultipart()
            msg['From'] = SENDER_EMAIL
            msg['To'] = email
            msg['Subject'] = "Hostel Notice from Warden"
            msg.attach(MIMEText(message_body, 'plain'))
            server.sendmail(SENDER_EMAIL, email, msg.as_string())

        server.quit()
        return jsonify({"status": "✅ Emails sent successfully!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
