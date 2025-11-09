# app.py
import os
from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from mangum import Mangum
from vercel.blob import put

# --- Config ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/chat_app.db'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- AUTO-CREATE DB ON FIRST REQUEST ---
@app.before_first_request
def create_tables():
    db.create_all()
    print("Database tables created!")

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)

class GroupMember(db.Model):
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True)
    content = db.Column(db.Text)
    media_blob_path = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, server_default=db.func.now())

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')
    group = db.relationship('Group', backref='messages')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- FULL HTML ---
NEXUS_HTML = '''<!DOCTYPE html>
<html lang="en" data-theme="auto">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Nexus Chat • {{ page_title }}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    :root { font-family: 'Inter', system-ui; --primary: oklch(60% 0.25 230); --bg: oklch(98% 0.005 240); --surface: oklch(96% 0.01 240); --text: oklch(20% 0.05 240); --radius: 1rem; --gap: 1rem; }
    [data-theme="dark"] { --bg: oklch(12% 0.01 240); --surface: oklch(16% 0.015 240); --text: oklch(90% 0.02 240); }
    body { background: var(--bg); color: var(--text); margin: 0; padding: 0; min-height: 100dvh; }
    .container { max-width: 1200px; margin: auto; padding: 1rem; }
    .card { background: var(--surface); border-radius: var(--radius); padding: 1.5rem; border: 1px solid oklch(90% 0.01 240 / 0.2); }
    .btn { background: var(--primary); color: white; border: none; padding: 0.75rem 1.5rem; border-radius: 999px; cursor: pointer; font-weight: 600; }
    .input { width: 100%; padding: 0.75rem; border-radius: 0.5rem; border: 1px solid oklch(80% 0.01 240); background: var(--bg); color: var(--text); }
    .chat { display: grid; grid-template-rows: auto 1fr auto; height: 100dvh; }
    .messages { overflow-y: auto; padding: 1rem; display: flex; flex-direction: column; gap: 1rem; }
    .msg { max-width: 70%; padding: 0.75rem 1rem; border-radius: 1rem; }
    .out { align-self: flex-end; background: var(--primary); color: white; }
    .in { align-self: flex-start; background: var(--surface); }
    .input-bar { display: flex; gap: 0.5rem; padding: 1rem; background: var(--surface); border-top: 1px solid oklch(80% 0.01 240); }
    img, video { max-width: 100%; border-radius: 0.5rem; margin-top: 0.5rem; }
  </style>
</head>
<body>
  {% if page == 'login' %}
  <div style="display:flex; align-items:center; justify-content:center; min-height:100dvh;">
    <div class="card" style="width:100%; max-width:400px;">
      <h1 style="text-align:center; margin-bottom:1rem;">Login</h1>
      <form method="post">
        <input name="username" class="input" placeholder="Username" required><br><br>
        <input name="password" type="password" class="input" placeholder="Password" required><br><br>
        <button type="submit" class="btn" style="width:100%;">Login</button>
      </form>
      <p style="text-align:center; margin-top:1rem;"><a href="{{ url_for('register') }}">Register</a></p>
    </div>
  </div>
  {% endif %}

  {% if page == 'register' %}
  <div style="display:flex; align-items:center; justify-content:center; min-height:100dvh;">
    <div class="card" style="width:100%; max-width:400px;">
      <h1 style="text-align:center; margin-bottom:1rem;">Register</h1>
      <form method="post">
        <input name="username" class="input" placeholder="Username" required><br><br>
        <input name="password" type="password" class="input" placeholder="Password" required><br><br>
        <button type="submit" class="btn" style="width:100%;">Register</button>
      </form>
      <p style="text-align:center; margin-top:1rem;"><a href="{{ url_for('login') }}">Login</a></p>
    </div>
  </div>
  {% endif %}

  {% if page == 'home' %}
  <div class="container">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
      <h1>Welcome, {{ current_user.username }}</h1>
      <a href="{{ url_for('logout') }}" class="btn">Logout</a>
    </div>
    {% with messages = get_flashed_messages() %}
      {% if messages %}<div class="card" style="margin-bottom:1rem;">{% for msg in messages %}<p>{{ msg }}</p>{% endfor %}</div>{% endif %}
    {% endwith %}
    <div style="display:grid; gap:1rem; grid-template-columns:1fr 1fr;">
      <div class="card">
        <h2>Create Group</h2>
        <form method="post" action="{{ url_for('create_group') }}">
          <input name="group_name" class="input" placeholder="Group Name" required>
          <button type="submit" class="btn" style="margin-top:0.5rem;">Create</button>
        </form>
      </div>
      <div class="card">
        <h2>Join Group</h2>
        <form method="post" action="{{ url_for('join_group') }}">
          <input name="group_name" class="input" placeholder="Group Name" required>
          <button type="submit" class="btn" style="margin-top:0.5rem;">Join</button>
        </form>
      </div>
    </div>
    <div class="card" style="margin-top:1rem;">
      <h2>All Users</h2>
      <div style="display:flex; flex-wrap:wrap; gap:0.5rem;">
        {% for user in all_users %}{% if user.id != current_user.id %}
          <a href="{{ url_for('private_chat', receiver_id=user.id) }}" style="padding:0.5rem 1rem; background:var(--primary); color:white; border-radius:999px; text-decoration:none;">{{ user.username }}</a>
        {% endif %}{% endfor %}
      </div>
    </div>
  </div>
  {% endif %}

  {% if page == 'private_chat' %}
  <div class="chat">
    <div style="padding:1rem; border-bottom:1px solid var(--surface);">
      <h2>Chat with {{ receiver.username }}</h2>
    </div>
    <div class="messages" id="messages">
      {% for msg in messages %}
        <div class="msg {% if msg.sender_id == current_user.id %}out{% else %}in{% endif %}">
          {% if msg.content %}<p>{{ msg.content }}</p>{% endif %}
          {% if msg.media_blob_path %}
            {% set ext = msg.media_blob_path.split('.')[-1].lower() %}
            {% if ext in ['png','jpg','jpeg','gif'] %}
              <img src="{{ msg.media_blob_path }}">
            {% elif ext in ['mp4','webm'] %}
              <video controls><source src="{{ msg.media_blob_path }}"></video>
            {% else %}
              <a href="{{ msg.media_blob_path }}" target="_blank">Download</a>
            {% endif %}
          {% endif %}
        </div>
      {% endfor %}
    </div>
    <form class="input-bar" method="post" action="{{ url_for('send_message') }}" enctype="multipart/form-data">
      <input type="hidden" name="chat_type" value="private">
      <input type="hidden" name="receiver_id" value="{{ receiver.id }}">
      <textarea name="content" class="input" placeholder="Type..." style="flex:1; resize:none;" rows="1"></textarea>
      <label><input type="file" name="media" style="display:none;"> Attach</label>
      <button type="submit" class="btn">Send</button>
    </form>
  </div>
  {% endif %}

  <script>
    document.addEventListener('DOMContentLoaded', () => {
      const msgDiv = document.getElementById('messages');
      if (msgDiv) msgDiv.scrollTop = msgDiv.scrollHeight;
    });
  </script>
</body>
</html>'''

# --- Routes ---
@app.route('/')
@login_required
def home():
    user_groups = Group.query.join(GroupMember).filter(GroupMember.user_id == current_user.id).all()
    all_users = User.query.all()
    return render_template_string(NEXUS_HTML, page='home', page_title='Home', user_groups=user_groups, all_users=all_users)

@app.route('/private/<int:receiver_id>')
@login_required
def private_chat(receiver_id):
    receiver = User.query.get_or_404(receiver_id)
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == receiver.id)) |
        ((Message.sender_id == receiver.id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp.asc()).all()
    return render_template_string(NEXUS_HTML, page='private_chat', receiver=receiver, messages=messages, page_title=receiver.username)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username taken.')
            return redirect(url_for('register'))
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        flash('Registered! Login now.')
        return redirect(url_for('login'))
    return render_template_string(NEXUS_HTML, page='register', page_title='Register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username'], password=request.form['password']).first()
        if user:
            login_user(user)
            return redirect(url_for('home'))
        flash('Wrong credentials.')
    return render_template_string(NEXUS_HTML, page='login', page_title='Login')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    content = request.form.get('content', '').strip()
    media = request.files.get('media')
    media_url = None
    if media and media.filename:
        filename = secure_filename(media.filename)
        blob = put(f"chat-media/{current_user.id}/{filename}", media.read(), access="public", token=os.getenv('BLOB_READ_WRITE_TOKEN'))
        media_url = blob.url
    if not content and not media_url:
        flash('Empty message.')
        return redirect(request.referrer or url_for('home'))

    if request.form.get('chat_type') == 'private':
        msg = Message(sender_id=current_user.id, receiver_id=request.form['receiver_id'], content=content, media_blob_path=media_url)
    else:
        return redirect(url_for('home'))
    db.session.add(msg)
    db.session.commit()
    return redirect(request.referrer or url_for('home'))

@app.route('/create_group', methods=['POST'])
@login_required
def create_group():
    name = request.form['group_name']
    if not Group.query.filter_by(name=name).first():
        group = Group(name=name)
        db.session.add(group)
        db.session.flush()
        db.session.add(GroupMember(group_id=group.id, user_id=current_user.id))
        db.session.commit()
        flash('Group created!')
    else:
        flash('Group exists.')
    return redirect(url_for('home'))

@app.route('/join_group', methods=['POST'])
@login_required
def join_group():
    group = Group.query.filter_by(name=request.form['group_name']).first()
    if group and not GroupMember.query.filter_by(group_id=group.id, user_id=current_user.id).first():
        db.session.add(GroupMember(group_id=group.id, user_id=current_user.id))
        db.session.commit()
        flash('Joined!')
    return redirect(url_for('home'))

# --- Vercel ---
handler = Mangum(app, lifespan="off")

# --- Local ---
if __name__ == '__main__':
    app.run(debug=True)








