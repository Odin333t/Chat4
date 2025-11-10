# app.py
import os
from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from mangum import Mangum
from vercel.blob import put

# --- Flask App Configuration ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret')

# Ensure SSL is required for Neon PostgreSQL
database_url = os.getenv('DATABASE_URL')
if database_url and 'sslmode' not in database_url:
    database_url += '?sslmode=require'
app.config['SQLALCHEMY_DATABASE_URI'] = database_url

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB upload limit

# --- Database and Login Setup ---
db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- INIT DB ON STARTUP (Vercel) ---
with app.app_context():
    db.create_all()
    print("Neon PostgreSQL DB initialized!")
    
# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True)
    content = db.Column(db.Text)
    media_blob_path = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, server_default=db.func.now())

    # FIXED: Relationships
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')
    group = db.relationship('Group', backref='messages')

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)

class GroupMember(db.Model):
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Init DB ---
def init_db():
    with app.app_context():
        db.create_all()

# --- Full HTML Template (Self-Contained) ---
NEXUS_HTML = '''<!DOCTYPE html>
<html lang="en" data-theme="auto">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Nexus Chat • {{ page_title }}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    :root {
      --font-family: 'Inter', system-ui, sans-serif;
      font-family: var(--font-family);
      --font-weight-light: 300;
      --font-weight-regular: 400;
      --font-weight-medium: 500;
      --font-weight-semibold: 600;
      --font-weight-bold: 700;

      --type-xs: clamp(0.75rem, 0.7rem + 0.25vw, 0.875rem);
      --type-sm: clamp(0.875rem, 0.8rem + 0.375vw, 1rem);
      --type-base: clamp(1rem, 0.9rem + 0.5vw, 1.125rem);
      --type-lg: clamp(1.125rem, 1rem + 0.625vw, 1.375rem);
      --type-xl: clamp(1.25rem, 1.1rem + 0.75vw, 1.5rem);
      --type-2xl: clamp(1.5rem, 1.3rem + 1vw, 1.875rem);
      --type-3xl: clamp(1.875rem, 1.6rem + 1.375vw, 2.25rem);

      --line-height-tight: 1.25;
      --line-height-snug: 1.375;
      --line-height-normal: 1.5;

      --radius-sm: 0.375rem;
      --radius-md: 0.5rem;
      --radius-lg: 0.75rem;
      --radius-xl: 1rem;
      --radius-2xl: 1.5rem;
      --radius-full: 9999px;

      --spacing-0: 0;
      --spacing-1: 0.25rem;
      --spacing-2: 0.5rem;
      --spacing-3: 0.75rem;
      --spacing-4: 1rem;
      --spacing-5: 1.25rem;
      --spacing-6: 1.5rem;
      --spacing-8: 2rem;
      --spacing-12: 3rem;

      --shadow-sm: 0 1px 2px 0 oklch(0% 0 0 / 0.05);
      --shadow-md: 0 4px 6px -1px oklch(0% 0 0 / 0.1), 0 2px 4px -2px oklch(0% 0 0 / 0.1);
      --shadow-lg: 0 10px 15px -3px oklch(0% 0 0 / 0.1), 0 4px 6px -4px oklch(0% 0 0 / 0.1);
      --shadow-xl: 0 20px 25px -5px oklch(0% 0 0 / 0.1), 0 8px 10px -6px oklch(0% 0 0 / 0.1);
      --shadow-2xl: 0 25px 50px -12px oklch(0% 0 0 / 0.25);

      --motion-fast: 150ms;
      --motion-normal: 250ms;
      --motion-slow: 400ms;
      --motion-quint: cubic-bezier(0.86, 0, 0.07, 1);
      --motion-standard: cubic-bezier(0.2, 0, 0, 1);

      --container-max-width: min(100% - 2rem, 1400px);
      --container-padding: clamp(1rem, 4vw, 3rem);
      --grid-gap: clamp(1rem, 2.5vw, 2rem);
    }

    :root {
      --color-surface-0: oklch(100% 0 0);
      --color-surface-1: oklch(99% 0.001 240);
      --color-surface-2: oklch(97% 0.005 240);
      --color-surface-3: oklch(95% 0.01 240);
      --color-surface-elevated: oklch(98% 0.005 240 / 0.9);

      --color-primary-100: oklch(95% 0.03 230);
      --color-primary-200: oklch(85% 0.08 230);
      --color-primary-300: oklch(65% 0.18 230);
      --color-primary-400: oklch(55% 0.22 230);
      --color-primary-500: oklch(50% 0.25 230);

      --color-secondary-300: oklch(70% 0.12 170);
      --color-danger: oklch(60% 0.25 20);
      --color-success: oklch(65% 0.18 140);
    }

    @media (prefers-color-scheme: dark), [data-theme="dark"] {
      :root, html[data-theme="dark"] {
        --color-surface-0: oklch(8% 0 0);
        --color-surface-1: oklch(12% 0.005 240);
        --color-surface-2: oklch(16% 0.01 240);
        --color-surface-3: oklch(20% 0.015 240);
        --color-surface-elevated: oklch(15% 0.01 240 / 0.8);

        --color-primary-100: oklch(40% 0.12 230);
        --color-primary-200: oklch(50% 0.18 230);
        --color-primary-300: oklch(65% 0.22 230);
        --color-primary-400: oklch(75% 0.2 230);
        --color-primary-500: oklch(85% 0.15 230);

        --color-secondary-300: oklch(55% 0.1 170);
        --color-danger: oklch(55% 0.22 20);
      }
    }

    html[data-theme="auto"] { color-scheme: light dark; }

    :root { --gradient-primary: linear-gradient(135deg, var(--color-primary-300), var(--color-primary-500)); }

    .nexus-container { max-width: var(--container-max-width); margin-inline: auto; padding-inline: var(--container-padding); }

    .nexus-grid { display: grid; gap: var(--grid-gap); grid-template-columns: 1fr; }
    @container (min-width: 640px) { .nexus-grid { grid-template-columns: repeat(8, 1fr); } }
    @container (min-width: 1024px) { .nexus-grid { grid-template-columns: repeat(12, 1fr); } }
    @container (min-width: 1440px) { .nexus-grid { grid-template-columns: 300px 1fr 300px; } }

    .nexus-header {
      display: flex; justify-content: space-between; align-items: center;
      padding: var(--spacing-4) 0; border-bottom: 1px solid var(--color-surface-3);
      margin-bottom: var(--spacing-6);
    }

    .nexus-card {
      background: var(--color-surface-1); border-radius: var(--radius-xl);
      padding: var(--spacing-6); border: 1px solid var(--color-surface-3);
      transition: all var(--motion-normal) var(--motion-quint);
    }
    .nexus-card.elevated { box-shadow: var(--shadow-lg); backdrop-filter: blur(12px); }
    .nexus-card.filled { background: var(--color-surface-2); }
    .nexus-card.outlined { background: transparent; }
    .nexus-card:hover { transform: translateY(-4px); box-shadow: var(--shadow-xl); }

    .nexus-button {
      display: inline-flex; align-items: center; justify-content: center;
      gap: var(--spacing-2); font-weight: var(--font-weight-semibold);
      font-size: var(--type-base); line-height: var(--line-height-snug);
      border-radius: var(--radius-full); padding: var(--spacing-3) var(--spacing-5);
      cursor: pointer; position: relative; overflow: hidden; border: none;
      transition: all var(--motion-normal) var(--motion-quint);
    }
    .nexus-button.primary { background: var(--gradient-primary); color: white; box-shadow: 0 4px 12px oklch(50% .25 230 / .3); }
    .nexus-button.secondary { background: var(--color-secondary-300); color: white; }
    .nexus-button.ghost { background: transparent; color: var(--color-primary-300); }
    .nexus-button.destructive { background: var(--color-danger); color: white; }
    .nexus-button:hover { transform: translateY(-1px); box-shadow: 0 8px 16px oklch(0% 0 0 / .2); }
    .nexus-button:active { transform: translateY(0); transition-duration: var(--motion-fast); }

    .nexus-button .ripple {
      position: absolute; border-radius: 50%;
      background: radial-gradient(circle at center, oklch(100% 0 0 / .2) 0%, transparent 70%);
      transform: scale(0); animation: ripple 600ms var(--motion-standard) forwards;
      pointer-events: none;
    }
    @keyframes ripple { to { transform: scale(4); opacity: 0; } }

    .nexus-input, .nexus-textarea {
      width: 100%; padding: var(--spacing-4); font-size: var(--type-base);
      line-height: var(--line-height-normal); border-radius: var(--radius-lg);
      border: 1px solid var(--color-surface-3); background: var(--color-surface-1);
      color: var(--color-primary-500); transition: all var(--motion-normal) var(--motion-standard);
      outline: none;
    }
    .nexus-textarea { resize: vertical; min-height: 100px; }
    .nexus-input:focus, .nexus-textarea:focus {
      border-color: var(--color-primary-300);
      box-shadow: 0 0 0 3px oklch(65% .18 230 / .2);
      background: var(--color-surface-0);
    }

    .nexus-chat-layout {
      display: grid; grid-template-rows: auto 1fr auto; height: 100dvh;
    }

    .nexus-message-list {
      display: flex; flex-direction: column; gap: var(--spacing-4);
      padding: var(--spacing-4); overflow-y: auto; scroll-behavior: smooth;
      max-height: 100%;
    }
    .nexus-message { display: flex; flex-direction: column; }
    .nexus-message.outgoing { align-items: flex-end; }
    .nexus-message.incoming { align-items: flex-start; }
    .nexus-bubble {
      max-width: 75%; padding: var(--spacing-3) var(--spacing-4);
      border-radius: var(--radius-lg); background: var(--color-surface-2);
      color: var(--color-primary-500);
      animation: slide-fade-in .3s var(--motion-quint) forwards;
    }
    .nexus-message.outgoing .nexus-bubble { background: var(--gradient-primary); color: white; }
    .nexus-timestamp {
      font-size: var(--type-xs); color: oklch(60% 0.1 240 / 0.7);
      margin-top: var(--spacing-1); align-self: flex-end;
    }
    .nexus-media-preview { margin-top: var(--spacing-2); border-radius: var(--radius-md); overflow: hidden; }
    .nexus-media-preview img, .nexus-media-preview video { max-width: 100%; border-radius: var(--radius-md); }

    .nexus-input-bar {
      display: flex; gap: var(--spacing-2); padding: var(--spacing-4);
      background: var(--color-surface-1); border-top: 1px solid var(--color-surface-3);
    }
    .nexus-input-bar .nexus-textarea { flex: 1; min-height: 48px; }
    .nexus-file-input { display: none; }

    @keyframes slide-fade-in {
      from { opacity: 0; transform: translateY(8px) scale(0.98); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }

    .nexus-type-2xl { font-size: var(--type-2xl); }
    .nexus-type-xl { font-size: var(--type-xl); }
    .nexus-type-lg { font-size: var(--type-lg); }
    .nexus-type-3xl { font-size: var(--type-3xl); }
    .nexus-link { color: var(--color-primary-300); text-decoration: none; }
    .nexus-link:hover { text-decoration: underline; }
    .nexus-chip { display: inline-block; padding: var(--spacing-2) var(--spacing-3); background: var(--color-surface-2); border-radius: var(--radius-full); font-size: var(--type-sm); }
    .nexus-list { list-style: none; padding: 0; margin: 0; }
    .nexus-list li { margin-bottom: var(--spacing-2); }
  </style>
</head>
<body>

  <!-- LOGIN -->
  {% if page == 'login' %}
  <div style="min-height:100dvh; display:flex; align-items:center; justify-content:center; background:var(--color-surface-0);">
    <div class="nexus-card elevated" style="max-width:400px; width:100%;">
      <h1 class="nexus-type-3xl" style="text-align:center; margin-bottom:var(--spacing-6);">Login</h1>
      <form action="{{ url_for('login') }}" method="post">
        <input type="text" name="username" class="nexus-input" placeholder="Username" required>
        <input type="password" name="password" class="nexus-input" placeholder="Password" required>
        <button type="submit" class="nexus-button primary" style="width:100%; margin-top:var(--spacing-4);">Login</button>
      </form>
      <p style="text-align:center; margin-top:var(--spacing-4);">
        <a href="{{ url_for('register') }}" class="nexus-link">Don't have an account? Register</a>
      </p>
    </div>
  </div>
  {% endif %}

  <!-- REGISTER -->
  {% if page == 'register' %}
  <div style="min-height:100dvh; display:flex; align-items:center; justify-content:center; background:var(--color-surface-0);">
    <div class="nexus-card elevated" style="max-width:400px; width:100%;">
      <h1 class="nexus-type-3xl" style="text-align:center; margin-bottom:var(--spacing-6);">Register</h1>
      <form action="{{ url_for('register') }}" method="post">
        <input type="text" name="username" class="nexus-input" placeholder="Username" required>
        <input type="password" name="password" class="nexus-input" placeholder="Password" required>
        <button type="submit" class="nexus-button primary" style="width:100%; margin-top:var(--spacing-4);">Register</button>
      </form>
      <p style="text-align:center; margin-top:var(--spacing-4);">
        <a href="{{ url_for('login') }}" class="nexus-link">Already have an account? Login</a>
      </p>
    </div>
  </div>
  {% endif %}

  <!-- HOME -->
  {% if page == 'home' %}
  <div class="nexus-container">
    <header class="nexus-header">
      <h1 class="nexus-type-2xl">Welcome, {{ current_user.username }}</h1>
      <a href="{{ url_for('logout') }}" class="nexus-button ghost">Logout</a>
    </header>

    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        <div style="margin-bottom: var(--spacing-6);">
          {% for category, msg in messages %}
            <div class="nexus-card outlined {{ category }}" style="margin-bottom: var(--spacing-2);">{{ msg }}</div>
          {% endfor %}
        </div>
      {% endif %}
    {% endwith %}

    <div class="nexus-grid home">
      <section class="nexus-card elevated">
        <h2 class="nexus-type-lg">Send Private Message</h2>
        <p>Select a user from "All Users" below.</p>
      </section>

      <section class="nexus-card elevated">
        <h2 class="nexus-type-lg">Create Group</h2>
        <form action="{{ url_for('create_group') }}" method="post">
          <input type="text" name="group_name" class="nexus-input" placeholder="Group Name" required>
          <button type="submit" class="nexus-button primary">Create</button>
        </form>
      </section>

      <section class="nexus-card filled">
        <h2 class="nexus-type-lg">Your Groups</h2>
        <ul class="nexus-list">
          {% for group in user_groups %}
            <li><a href="{{ url_for('group_chat', group_id=group.id) }}" class="nexus-link">{{ group.name }}</a></li>
          {% else %}
            <li>No groups yet.</li>
          {% endfor %}
        </ul>
      </section>

      <section class="nexus-card filled">
        <h2 class="nexus-type-lg">Join Group</h2>
        <form action="{{ url_for('join_group') }}" method="post">
          <input type="text" name="group_name" class="nexus-input" placeholder="Group Name" required>
          <button type="submit" class="nexus-button secondary">Join</button>
        </form>
      </section>

      <section class="nexus-card outlined" style="grid-column: 1 / -1;">
        <h2 class="nexus-type-lg">All Users</h2>
        <div style="display:flex; flex-wrap:wrap; gap: var(--spacing-2);">
          {% for user in all_users %}
            {% if user.id != current_user.id %}
              <a href="{{ url_for('private_chat', receiver_id=user.id) }}" class="nexus-chip">{{ user.username }}</a>
            {% endif %}
          {% endfor %}
        </div>
      </section>

      <section class="nexus-card outlined" style="grid-column: 1 / -1;">
        <h2 class="nexus-type-lg">Recent Messages</h2>
        <ul class="nexus-message-list">
          {% for msg in received_messages %}
            <li class="nexus-message incoming">
              <div class="nexus-bubble">
                <strong>{{ msg.sender.username }}</strong>
                <p style="white-space: pre-wrap; margin: var(--spacing-1) 0;">{{ msg.content }}</p>
                {% if msg.media_blob_path %}
                  <div class="nexus-media-preview">
                    {% set ext = msg.media_blob_path.split('.')[-1].lower() %}
                    {% if ext in ['png','jpg','jpeg','gif'] %}
                      <img src="{{ msg.media_blob_path }}" alt="Image">
                    {% elif ext in ['mp4','webm'] %}
                      <video controls style="max-width:100%;"><source src="{{ msg.media_blob_path }}"></video>
                    {% elif ext in ['mp3','wav'] %}
                      <audio controls style="width:100%;"><source src="{{ msg.media_blob_path }}"></audio>
                    {% else %}
                      <a href="{{ msg.media_blob_path }}" target="_blank">Download {{ msg.media_blob_path.split('/')[-1] }}</a>
                    {% endif %}
                  </div>
                {% endif %}
                <span class="nexus-timestamp">{{ msg.timestamp.strftime('%H:%M') }}</span>
              </div>
            </li>
          {% else %}
            <li>No messages yet.</li>
          {% endfor %}
        </ul>
      </section>
    </div>
  </div>
  {% endif %}

  <!-- GROUPS -->
  {% if page == 'groups' %}
  <div class="nexus-container">
    <header class="nexus-header">
      <h1 class="nexus-type-2xl">Your Groups</h1>
      <a href="{{ url_for('home') }}" class="nexus-button ghost">Back</a>
    </header>

    <div class="nexus-grid">
      {% for group in groups %}
        <div class="nexus-card filled">
          <h3 class="nexus-type-lg">#{{ group.name }}</h3>
          <p>{{ group.group_members|length }} members</p>
          <a href="{{ url_for('group_chat', group_id=group.id) }}" class="nexus-button primary">Open Chat</a>
        </div>
      {% else %}
        <div class="nexus-card outlined" style="grid-column: 1 / -1; text-align:center;">
          <p>No groups yet. <a href="{{ url_for('home') }}" class="nexus-link">Create or join one</a>.</p>
        </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  <!-- PRIVATE CHAT -->
  {% if page == 'private_chat' %}
  <div class="nexus-chat-layout">
    <header class="nexus-header">
      <h1 class="nexus-type-xl">Chat with {{ receiver.username }}</h1>
      <a href="{{ url_for('home') }}" class="nexus-button ghost">Back</a>
    </header>

    <main class="nexus-message-list" id="messages">
      {% for msg in messages %}
        <div class="nexus-message {% if msg.sender.id == current_user.id %}outgoing{% else %}incoming{% endif %}">
          <div class="nexus-bubble">
            <p style="white-space: pre-wrap; margin: var(--spacing-1) 0;">{{ msg.content }}</p>
            {% if msg.media_blob_path %}
              <div class="nexus-media-preview">
                {% set ext = msg.media_blob_path.split('.')[-1].lower() %}
                {% if ext in ['png','jpg','jpeg','gif'] %}
                  <img src="{{ msg.media_blob_path }}" alt="Media">
                {% elif ext in ['mp4','webm'] %}
                  <video controls style="max-width:100%;"><source src="{{ msg.media_blob_path }}"></video>
                {% elif ext in ['mp3','wav'] %}
                  <audio controls style="width:100%;"><source src="{{ msg.media_blob_path }}"></audio>
                {% else %}
                  <a href="{{ msg.media_blob_path }}" target="_blank">Open File</a>
                {% endif %}
              </div>
            {% endif %}
            <span class="nexus-timestamp">{{ msg.timestamp.strftime('%H:%M') }}</span>
          </div>
        </div>
      {% endfor %}
    </main>

    <form class="nexus-input-bar" action="{{ url_for('send_message') }}" method="post" enctype="multipart/form-data">
      <input type="hidden" name="chat_type" value="private">
      <input type="hidden" name="receiver_id" value="{{ receiver.id }}">
      <textarea name="content" class="nexus-textarea" placeholder="Type a message..." required></textarea>
      <label class="nexus-button ghost" style="cursor:pointer;">
        Attach <input type="file" name="media" class="nexus-file-input">
      </label>
      <button type="submit" class="nexus-button primary">Send</button>
      <button type="button" class="nexus-button ghost" onclick="pasteFromClipboard()">Paste</button>
    </form>
  </div>
  {% endif %}

  <!-- GROUP CHAT -->
  {% if page == 'group_chat' %}
  <div class="nexus-chat-layout">
    <header class="nexus-header">
      <h1 class="nexus-type-xl">#{{ group.name }}</h1>
      <a href="{{ url_for('groups') }}" class="nexus-button ghost">Back</a>
    </header>

    <main class="nexus-message-list" id="group-messages">
      {% for msg in messages %}
        <div class="nexus-message incoming">
          <div class="nexus-bubble">
            <strong>{{ msg.sender.username }}</strong>
            <p style="white-space: pre-wrap; margin: var(--spacing-1) 0;">{{ msg.content }}</p>
            {% if msg.media_blob_path %}
              <div class="nexus-media-preview">
                {% set ext = msg.media_blob_path.split('.')[-1].lower() %}
                {% if ext in ['png','jpg','jpeg','gif'] %}
                  <img src="{{ msg.media_blob_path }}">
                {% elif ext in ['mp4','webm'] %}
                  <video controls style="max-width:100%;"><source src="{{ msg.media_blob_path }}"></video>
                {% else %}
                  <a href="{{ msg.media_blob_path }}" target="_blank">Download</a>
                {% endif %}
              </div>
            {% endif %}
            <span class="nexus-timestamp">{{ msg.timestamp.strftime('%H:%M') }}</span>
          </div>
        </div>
      {% endfor %}
    </main>

    <form class="nexus-input-bar" action="{{ url_for('group_chat', group_id=group.id) }}" method="post" enctype="multipart/form-data">
      <input type="text" name="message" class="nexus-input" placeholder="Message #{{ group.name }}" required autocomplete="off">
      <label class="nexus-button ghost">
        Attach <input type="file" name="media" class="nexus-file-input">
      </label>
      <button type="submit" class="nexus-button primary">Send</button>
    </form>
  </div>
  {% endif %}

  <script>
    document.addEventListener('DOMContentLoaded', () => {
      ['messages', 'group-messages'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.scrollTop = el.scrollHeight;
      });

      document.querySelectorAll('.nexus-button').forEach(btn => {
        btn.addEventListener('click', e => {
          const ripple = document.createElement('span');
          ripple.classList.add('ripple');
          const rect = btn.getBoundingClientRect();
          ripple.style.left = `${e.clientX - rect.left}px`;
          ripple.style.top = `${e.clientY - rect.top}px`;
          btn.appendChild(ripple);
          setTimeout(() => ripple.remove(), 600);
        });
      });
    });

    async function pasteFromClipboard() {
      try {
        const text = await navigator.clipboard.readText();
        const textarea = document.querySelector('.nexus-textarea');
        if (textarea) {
          const start = textarea.selectionStart;
          const end = textarea.selectionEnd;
          textarea.value = textarea.value.substring(0, start) + text + textarea.value.substring(end);
          textarea.selectionStart = textarea.selectionEnd = start + text.length;
          textarea.focus();
        }
      } catch (err) { console.error('Paste failed:', err); }
    }
  </script>
</body>
</html>'''

# --- Routes ---
@app.route('/')
@login_required
def home():
    user_groups = Group.query.join(GroupMember).filter(GroupMember.user_id == current_user.id).all()
    all_users = User.query.all()
    # Eager-load the sender relationship to avoid 'Message has no attribute sender'
    received_messages = (
        Message.query
        .filter_by(receiver_id=current_user.id)
        .options(db.joinedload(Message.sender))
        .order_by(Message.timestamp.desc())
        .all()
    )
    return render_template_string(
        NEXUS_HTML,
        page='home',
        page_title='Home',
        user_groups=user_groups,
        all_users=all_users,
        received_messages=received_messages
    )

@app.route('/private/<int:receiver_id>')
@login_required
def private_chat(receiver_id):
    receiver = User.query.get_or_404(receiver_id)
    # Eager-load sender to prevent the same error in private chat
    messages = (
        Message.query
        .filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == receiver.id)) |
            ((Message.sender_id == receiver.id) & (Message.receiver_id == current_user.id))
        )
        .options(db.joinedload(Message.sender))
        .order_by(Message.timestamp.asc())
        .all()
    )
    return render_template_string(
        NEXUS_HTML,
        page='private_chat',
        receiver=receiver,
        messages=messages,
        page_title='Chat'
    )

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return redirect(url_for('register'))
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        flash('Registered! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template_string(NEXUS_HTML, page='register', page_title='Register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            login_user(user)
            return redirect(url_for('home'))
        flash('Invalid credentials', 'error')
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
    chat_type = request.form.get('chat_type')
    media = request.files.get('media')
    media_url = None

    # Allow empty text if media is attached
    if not content and not media:
        flash('Cannot send empty message.', 'error')
        return redirect(request.referrer or url_for('home'))

    if media and media.filename:
        filename = secure_filename(media.filename)
        try:
            blob = put(
                pathname=f"chat-media/{current_user.id}/{filename}",
                data=media.read(),
                access="public",
                token=os.getenv('BLOB_READ_WRITE_TOKEN')
            )
            media_url = blob.url
        except Exception as e:
            flash('Media upload failed.', 'error')
            return redirect(request.referrer or url_for('home'))

    if chat_type == 'private':
        receiver_id = request.form.get('receiver_id')
        if not receiver_id:
            flash('Receiver missing.', 'error')
            return redirect(url_for('home'))
        msg = Message(
            sender_id=current_user.id,
            receiver_id=receiver_id,
            content=content or '',
            media_blob_path=media_url
        )
    elif chat_type == 'group':
        group_id = request.form.get('group_id')
        if not group_id:
            flash('Group missing.', 'error')
            return redirect(url_for('home'))
        msg = Message(
            sender_id=current_user.id,
            group_id=group_id,
            content=content or '',
            media_blob_path=media_url
        )
    else:
        flash('Invalid chat type.', 'error')
        return redirect(url_for('home'))

    db.session.add(msg)
    db.session.commit()
    return redirect(request.referrer or url_for('home'))

@app.route('/create_group', methods=['POST'])
@login_required
def create_group():
    name = request.form.get('group_name')
    if Group.query.filter_by(name=name).first():
        flash('Group exists.', 'error')
    else:
        group = Group(name=name)
        db.session.add(group)
        db.session.flush()
        db.session.add(GroupMember(group_id=group.id, user_id=current_user.id))
        db.session.commit()
        flash('Group created!', 'success')
    return redirect(url_for('home'))

@app.route('/join_group', methods=['POST'])
@login_required
def join_group():
    name = request.form.get('group_name')
    group = Group.query.filter_by(name=name).first()
    if group and not GroupMember.query.filter_by(group_id=group.id, user_id=current_user.id).first():
        db.session.add(GroupMember(group_id=group.id, user_id=current_user.id))
        db.session.commit()
        flash('Joined group!', 'success')
    return redirect(url_for('home'))

@app.route('/groups')
@login_required
def groups():
    user_groups = Group.query.join(GroupMember).filter(GroupMember.user_id == current_user.id).all()
    return render_template_string(
        NEXUS_HTML,
        page='groups',
        page_title='Groups',
        groups=user_groups
    )

@app.route('/group/<int:group_id>', methods=['GET', 'POST'])
@login_required
def group_chat(group_id):
    group = Group.query.get_or_404(group_id)
    if not GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first():
        return redirect(url_for('groups'))

    if request.method == 'POST':
        content = request.form.get('message')
        media = request.files.get('media')
        media_url = None
        if media and media.filename:
            filename = secure_filename(media.filename)
            blob = put(
                pathname=f"chat-media/{current_user.id}/{filename}",
                data=media.read(),
                access="public",
                token=os.getenv('BLOB_READ_WRITE_TOKEN')
            )
            media_url = blob.url
        if content or media_url:
            msg = Message(
                sender_id=current_user.id,
                group_id=group_id,
                content=content,
                media_blob_path=media_url
            )
            db.session.add(msg)
            db.session.commit()
        return redirect(url_for('group_chat', group_id=group_id))

    # Eager-load sender for group messages too
    messages = (
        Message.query
        .filter_by(group_id=group_id)
        .options(db.joinedload(Message.sender))
        .order_by(Message.timestamp.asc())
        .all()
    )
    return render_template_string(
        NEXUS_HTML,
        page='group_chat',
        group=group,
        messages=messages,
        page_title=group.name
    )

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    abort(404)

# --- Vercel Handler ---
handler = Mangum(app, lifespan="off")

# --- Local Dev ---
if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)



