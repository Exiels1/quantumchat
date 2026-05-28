import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, redirect, request, url_for, flash
from flask_socketio import SocketIO, emit, join_room
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import or_
from sqlalchemy.pool import StaticPool
from models import db, User, DirectThread, DirectMessage
import cloudinary
import cloudinary.uploader
import secrets
import os

app = Flask(__name__)
app.config['SECRET_KEY']                = os.environ.get('FLASK_SECRET', 'change-me-in-prod')
app.config['SQLALCHEMY_DATABASE_URI']   = os.environ.get('DATABASE_URL', 'sqlite:///quantumchat.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'check_same_thread': False},
    'poolclass': StaticPool,
}
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# ── Cloudinary config ──
cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME', ''),
    api_key    = os.environ.get('CLOUDINARY_API_KEY', ''),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET', ''),
    secure     = True
)

db.init_app(app)
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins='*')

login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

# ── helpers ──
def make_codes(n=8):
    return [secrets.token_hex(4) for _ in range(n)]

def user_room(username):
    return f'user_{username}'

def get_or_create_thread(uid_a, uid_b):
    a, b = sorted([uid_a, uid_b])
    thread = DirectThread.query.filter_by(a_id=a, b_id=b).first()
    if not thread:
        thread = DirectThread(a_id=a, b_id=b)
        db.session.add(thread)
        db.session.commit()
    return thread

# =============================================
# AUTH ROUTES
# =============================================

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('inbox'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not (3 <= len(username) <= 30):
            flash('Username must be 3-30 characters.', 'error')
            return render_template('register.html')
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('register.html')
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash('Username or email already taken.', 'error')
            return render_template('register.html')

        user = User(username=username, email=email)
        user.set_password(password)
        codes = make_codes()
        user.set_backup_codes(codes)
        db.session.add(user)
        db.session.commit()

        return render_template('backup_codes.html', codes=codes, username=username)

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            user.status = 'online'
            db.session.commit()
            return redirect(url_for('inbox'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    current_user.status = 'offline'
    db.session.commit()
    logout_user()
    return redirect(url_for('login'))

@app.route('/forgot', methods=['GET', 'POST'])
def forgot():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        code     = request.form.get('code', '').strip()
        password = request.form.get('password', '')
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('forgot.html')
        user = User.query.filter_by(username=username).first()
        if not user:
            flash('Username not found.', 'error')
            return render_template('forgot.html')
        if user.consume_backup_code(code):
            user.set_password(password)
            db.session.commit()
            flash('Password reset. You can now log in.', 'success')
            return redirect(url_for('login'))
        flash('Invalid backup code.', 'error')
    return render_template('forgot.html')

# =============================================
# MAIN ROUTES
# =============================================

@app.route('/inbox')
@login_required
def inbox():
    threads = DirectThread.query.filter(
        or_(DirectThread.a_id == current_user.id, DirectThread.b_id == current_user.id)
    ).all()
    chats = []
    for t in threads:
        other = t.user_b if t.a_id == current_user.id else t.user_a
        last  = DirectMessage.query.filter_by(thread_id=t.id).order_by(DirectMessage.created_at.desc()).first()
        chats.append({'thread': t, 'other': other, 'last': last})
    return render_template('inbox.html', chats=chats)

@app.route('/search')
@login_required
def search():
    query = request.args.get('q', '').strip()
    users = []
    suggestions = []

    if query:
        users = User.query.filter(
            User.username.ilike(f'%{query}%'),
            User.id != current_user.id
        ).limit(20).all()
    else:
        # People you haven't chatted with yet
        existing_threads = DirectThread.query.filter(
            or_(DirectThread.a_id == current_user.id, DirectThread.b_id == current_user.id)
        ).all()
        chatted_ids = set()
        for t in existing_threads:
            chatted_ids.add(t.b_id if t.a_id == current_user.id else t.a_id)
        chatted_ids.add(current_user.id)

        suggestions = User.query.filter(
            User.id.notin_(chatted_ids)
        ).order_by(User.status.desc()).limit(30).all()

    return render_template('search.html', users=users, suggestions=suggestions, query=query)

@app.route('/chat/<int:user_id>')
@login_required
def chat(user_id):
    other    = User.query.get_or_404(user_id)
    thread   = get_or_create_thread(current_user.id, other.id)
    messages = DirectMessage.query.filter_by(thread_id=thread.id)\
                .order_by(DirectMessage.created_at.asc()).limit(200).all()
    return render_template('chat.html', thread=thread, other=other, messages=messages)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        status = request.form.get('status', '').strip()[:120]
        bio    = request.form.get('bio', '').strip()[:220]
        current_user.status = status or 'online'
        current_user.bio    = bio

        # Handle avatar upload to Cloudinary
        file = request.files.get('avatar')
        if file and file.filename:
            allowed = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
            ext = file.filename.rsplit('.', 1)[-1].lower()
            if ext not in allowed:
                flash('Invalid image type. Use PNG, JPG, GIF or WEBP.', 'error')
            else:
                try:
                    result = cloudinary.uploader.upload(
                        file,
                        public_id=f'quantumchat/avatars/user_{current_user.id}',
                        overwrite=True,
                        transformation=[
                            {'width': 200, 'height': 200, 'crop': 'fill', 'gravity': 'face'}
                        ]
                    )
                    current_user.avatar = result['secure_url']
                except Exception as e:
                    flash(f'Image upload failed: {str(e)}', 'error')

        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('profile'))

    return render_template('profile.html')

# =============================================
# SOCKETIO — MESSAGING
# =============================================

@socketio.on('connect')
def on_connect():
    if not current_user.is_authenticated:
        return False
    join_room(user_room(current_user.username))
    threads = DirectThread.query.filter(
        or_(DirectThread.a_id == current_user.id, DirectThread.b_id == current_user.id)
    ).all()
    for t in threads:
        join_room(f'dm_{t.id}')

@socketio.on('disconnect')
def on_disconnect():
    if current_user.is_authenticated:
        current_user.status = 'offline'
        db.session.commit()

@socketio.on('join')
def on_join(data):
    thread_id = data.get('thread')
    thread = DirectThread.query.get(thread_id)
    if thread and current_user.id in (thread.a_id, thread.b_id):
        join_room(f'dm_{thread_id}')

@socketio.on('send_message')
def handle_message(data):
    if not current_user.is_authenticated:
        return
    thread_id = data.get('thread')
    content   = (data.get('message') or '').strip()
    if not (thread_id and content):
        return
    thread = DirectThread.query.get(thread_id)
    if not thread or current_user.id not in (thread.a_id, thread.b_id):
        return
    msg = DirectMessage(thread_id=thread_id, sender_id=current_user.id, content=content)
    db.session.add(msg)
    db.session.commit()
    emit('receive_message', {
        'message':    msg.content,
        'sender':     current_user.username,
        'sender_id':  current_user.id,
        'created_at': msg.created_at.strftime('%H:%M'),
        'thread':     thread_id,
    }, to=f'dm_{thread_id}')

@socketio.on('typing')
def on_typing(data):
    if not current_user.is_authenticated:
        return
    thread_id = data.get('thread')
    emit('typing', {'user': current_user.username}, to=f'dm_{thread_id}', include_self=False)

@socketio.on('stop_typing')
def on_stop_typing(data):
    if not current_user.is_authenticated:
        return
    thread_id = data.get('thread')
    emit('stop_typing', {}, to=f'dm_{thread_id}', include_self=False)

# =============================================
# SOCKETIO — CALL SIGNALING
# =============================================

@socketio.on('call_user')
def on_call_user(data):
    if not current_user.is_authenticated:
        return
    target = (data.get('target') or '').strip()
    if not target:
        return
    emit('incoming_call', {'caller': current_user.username}, to=user_room(target))

@socketio.on('call_accepted')
def on_call_accepted(data):
    if not current_user.is_authenticated:
        return
    target = (data.get('target') or '').strip()
    emit('call_accepted', {'callee': current_user.username}, to=user_room(target))

@socketio.on('call_declined')
def on_call_declined(data):
    if not current_user.is_authenticated:
        return
    target = (data.get('target') or '').strip()
    emit('call_declined', {'callee': current_user.username}, to=user_room(target))

@socketio.on('call_ended')
def on_call_ended(data):
    if not current_user.is_authenticated:
        return
    target = (data.get('target') or '').strip()
    emit('call_ended', {'by': current_user.username}, to=user_room(target))

@socketio.on('offer')
def on_offer(data):
    if not current_user.is_authenticated:
        return
    target = (data.get('target') or '').strip()
    emit('offer', {'sdp': data.get('sdp'), 'caller': current_user.username}, to=user_room(target))

@socketio.on('answer')
def on_answer(data):
    if not current_user.is_authenticated:
        return
    target = (data.get('target') or '').strip()
    emit('answer', {'sdp': data.get('sdp'), 'callee': current_user.username}, to=user_room(target))

@socketio.on('ice_candidate')
def on_ice(data):
    if not current_user.is_authenticated:
        return
    target = (data.get('target') or '').strip()
    emit('ice_candidate', {'candidate': data.get('candidate'), 'from': current_user.username}, to=user_room(target))

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)