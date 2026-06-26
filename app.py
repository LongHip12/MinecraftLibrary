import os
import sys
import json
import io
import time
from collections import deque
from dotenv import load_dotenv
load_dotenv()
import uuid
import secrets
import mimetypes
import requests
import smtplib
import threading
import re
import traceback
import urllib.parse
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify, make_response, send_from_directory, g
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import supabase_backup

LOG_BUFFER = deque(maxlen=1000)

def _detect_level(text):
    ll = text.lower()
    if 'traceback' in ll or 'exception' in ll:
        return 'error'
    if ll.startswith('[error]') or ' error' in ll or 'error:' in ll:
        return 'error'
    if ll.startswith('[warn]') or 'warning' in ll or 'warn:' in ll:
        return 'warn'
    if ll.startswith('[debug]') or 'debug:' in ll:
        return 'debug'
    return 'info'

class _TeeStream:
    def __init__(self, original, default_level='info'):
        self._orig = original
        self._default = default_level
        self._buf = ''
    def write(self, text):
        self._orig.write(text)
        try:
            self._orig.flush()
        except Exception:
            pass
        self._buf += text
        while '\n' in self._buf:
            line, self._buf = self._buf.split('\n', 1)
            line = line.rstrip('\r')
            if line.strip():
                lv = _detect_level(line) if self._default == 'info' else self._default
                LOG_BUFFER.append({'t': datetime.now().isoformat(timespec='milliseconds'), 'level': lv, 'msg': line})
    def flush(self):
        try:
            self._orig.flush()
        except Exception:
            pass
    def isatty(self):
        return False
    def fileno(self):
        try:
            return self._orig.fileno()
        except Exception:
            raise io.UnsupportedOperation('fileno')

sys.stdout = _TeeStream(sys.stdout, 'info')
sys.stderr = _TeeStream(sys.stderr, 'error')

class _LogHandler(logging.Handler):
    def emit(self, record):
        lv_map = {'DEBUG': 'debug', 'INFO': 'info', 'WARNING': 'warn', 'ERROR': 'error', 'CRITICAL': 'error'}
        lv = lv_map.get(record.levelname, 'info')
        msg = self.format(record)
        LOG_BUFFER.append({'t': datetime.now().isoformat(timespec='milliseconds'), 'level': lv, 'msg': msg})

_log_handler = _LogHandler()
_log_handler.setFormatter(logging.Formatter('%(name)s — %(message)s'))
logging.getLogger().addHandler(_log_handler)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_prefix=1)
app.secret_key = os.environ.get("SESSION_SECRET") or secrets.token_hex(32)
APP_START_TIME = datetime.now()
STATUS_HISTORY = []
LOG_BUFFER.append({'t': APP_START_TIME.isoformat(timespec='milliseconds'), 'level': 'startup', 'msg': f'[STARTUP] App started — Python {sys.version.split()[0]}'})
CORS(app)

@app.after_request
def _rotate_remember_cookie(response):
    series = getattr(g, "_new_remember_series", None)
    token = getattr(g, "_new_remember_token", None)
    if series and token:
        expires = datetime.now() + timedelta(days=30)
        response.set_cookie("remember_me", f"{series}:{token}",
            expires=expires, httponly=True, secure=True, samesite="Lax", max_age=30*24*3600)
    return response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
FORUM_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "forum_uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
HCAPTCHA_SECRET = os.environ.get("SECRET", "")
HCAPTCHA_SITE_KEY = os.environ.get("KEY", "")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
GMAIL_FROM = "lonelyhub12@gmail.com"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")
DISCORD_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.environ.get("DISCORD_REDIRECT_URI", "")
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "")
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
MAX_FILE_SIZE = 10 * 1024 * 1024
FORUM_MAX_FILE_SIZE = 50 * 1024 * 1024

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, "modbanner"), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, "avatars"), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, "banners"), exist_ok=True)
os.makedirs(FORUM_UPLOAD_DIR, exist_ok=True)
REPORT_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "report_uploads")
os.makedirs(REPORT_UPLOAD_DIR, exist_ok=True)

DEFAULT_DATA = {
    "accounts-data.json": {"users": []},
    "mods-data.json": {"mods": [], "next_id": 1, "next_client_id": 1},
    "sessions-data.json": {"sessions": {}},
    "forum-data.json": {"posts": []},
    "settings-data.json": {"api_rate_limit": 60},
    "reports-data.json": {"reports": []},
}

_rate_limit_store = {}

for _fname, _default in DEFAULT_DATA.items():
    _fpath = os.path.join(DATA_DIR, _fname)
    if not os.path.exists(_fpath):
        with open(_fpath, "w", encoding="utf-8") as _f:
            json.dump(_default, _f, ensure_ascii=False, indent=2)


def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            result = json.load(f)
            if not isinstance(result, dict):
                raise ValueError("Expected dict")
            return result
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        default = DEFAULT_DATA.get(filename, {})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
        return default


def save_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_session_user(request):
    token = request.cookies.get("session_token")
    if token:
        sessions = load_json("sessions-data.json")
        session = sessions.get("sessions", {}).get(token)
        if session:
            try:
                expires = datetime.fromisoformat(session["expires"])
            except (KeyError, ValueError):
                expires = None
            if expires and datetime.now() <= expires:
                accounts = load_json("accounts-data.json")
                user = next((u for u in accounts.get("users", []) if u["id"] == session["user_id"]), None)
                if user:
                    return user
            sessions["sessions"].pop(token, None)
            save_json("sessions-data.json", sessions)
    user, series, new_token = validate_remember_token(request)
    if user and series:
        g._new_remember_series = series
        g._new_remember_token = new_token
    return user


def create_session(user_id):
    token = secrets.token_hex(32)
    expires = datetime.now() + timedelta(hours=2)
    sessions = load_json("sessions-data.json")
    sessions.setdefault("sessions", {})[token] = {
        "user_id": user_id,
        "expires": expires.isoformat()
    }
    save_json("sessions-data.json", sessions)
    return token, expires


def issue_device_token():
    return secrets.token_hex(32)


def create_remember_token(user_id):
    series = secrets.token_hex(32)
    token = secrets.token_hex(32)
    expires = datetime.now() + timedelta(days=30)
    sessions = load_json("sessions-data.json")
    sessions.setdefault("remember_tokens", []).append({
        "user_id": user_id,
        "series": series,
        "token": token,
        "expires": expires.isoformat()
    })
    save_json("sessions-data.json", sessions)
    return series, token, expires


def validate_remember_token(request_obj):
    cookie = request_obj.cookies.get("remember_me")
    if not cookie or ":" not in cookie:
        return None, None, None
    series, token = cookie.split(":", 1)
    sessions = load_json("sessions-data.json")
    tokens = sessions.get("remember_tokens", [])
    match = next((t for t in tokens if t["series"] == series), None)
    if not match:
        return None, "not_found", None
    try:
        expires = datetime.fromisoformat(match["expires"])
    except (KeyError, ValueError):
        return None, "expired", None
    if datetime.now() > expires:
        sessions["remember_tokens"] = [t for t in tokens if t["series"] != series]
        save_json("sessions-data.json", sessions)
        return None, "expired", None
    if match["token"] != token:
        sessions["remember_tokens"] = [t for t in tokens if t["user_id"] != match["user_id"]]
        save_json("sessions-data.json", sessions)
        return None, "stolen", None
    new_token = secrets.token_hex(32)
    new_expires = datetime.now() + timedelta(days=30)
    for t in sessions["remember_tokens"]:
        if t["series"] == series:
            t["token"] = new_token
            t["expires"] = new_expires.isoformat()
    save_json("sessions-data.json", sessions)
    accounts = load_json("accounts-data.json")
    user = next((u for u in accounts.get("users", []) if u["id"] == match["user_id"]), None)
    return user, series, new_token


def send_email_html(to, subject, html_body):

    if BREVO_API_KEY:
        try:
            resp = requests.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
                json={
                    "sender": {"name": "Lonely Hub", "email": GMAIL_FROM},
                    "to": [{"email": to}],
                    "subject": subject,
                    "htmlContent": html_body
                },
                timeout=15
            )
            return resp.status_code in (200, 201, 202)
        except Exception:
            pass

    if not APP_PASSWORD:
        return False
    from email.mime.multipart import MIMEMultipart as _MM
    from email.mime.text import MIMEText as _MT
    msg = _MM("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_FROM
    msg["To"] = to
    msg.attach(_MT(html_body, "html"))
    result = [False]
    def _do_send():
        for attempt in [
            lambda: smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=12),
            lambda: smtplib.SMTP("smtp.gmail.com", 587, timeout=12),
        ]:
            try:
                server = attempt()
                if isinstance(server, smtplib.SMTP) and not isinstance(server, smtplib.SMTP_SSL):
                    server.starttls()
                server.login(GMAIL_FROM, APP_PASSWORD)
                server.send_message(msg)
                server.quit()
                result[0] = True
                return
            except Exception:
                continue
    t = threading.Thread(target=_do_send, daemon=True)
    t.start()
    t.join(timeout=20)
    return result[0]


def otp_email_html(otp, purpose_text):
    return (
        "<!DOCTYPE html><html><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"></head>"
        "<body style=\"margin:0;padding:0;background:#0f0f1a;font-family:Arial,sans-serif;\">"
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#0f0f1a;padding:40px 0;\">"
        "<tr><td align=\"center\">"
        "<table width=\"520\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#1a1a2e;border-radius:16px;overflow:hidden;border:1px solid rgba(255,255,255,0.07);max-width:520px;width:100%;\">"
        "<tr><td style=\"padding:36px 40px 24px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.06);\">"
        "<img src=\"https://i.imgur.com/xY7M2iE.jpeg\" width=\"52\" height=\"52\" style=\"border-radius:12px;margin-bottom:14px;display:block;margin-left:auto;margin-right:auto;\">"
        "<div style=\"color:#ffffff;font-size:20px;font-weight:700;\">Lonely Hub</div>"
        "<div style=\"color:#606078;font-size:13px;margin-top:2px;\">Minecraft Library</div>"
        "</td></tr>"
        "<tr><td style=\"padding:32px 40px 28px;\">"
        "<div style=\"color:#f0f0f8;font-size:17px;font-weight:600;margin-bottom:10px;\">Verification Code</div>"
        f"<div style=\"color:#a0a0b8;font-size:14px;line-height:1.65;margin-bottom:28px;\">{purpose_text} &mdash; enter this code. It expires in <strong style=\"color:#f0f0f8;\">10 minutes</strong>.</div>"
        "<div style=\"background:rgba(250,80,80,0.07);border:1.5px solid rgba(250,80,80,0.22);border-radius:14px;padding:26px 20px;text-align:center;margin-bottom:28px;\">"
        f"<div style=\"color:#fa5050;font-size:38px;font-weight:800;letter-spacing:14px;\">{otp}</div>"
        "</div>"
        "<div style=\"color:#606070;font-size:12px;text-align:center;line-height:1.5;\">If you didn\'t request this, you can safely ignore this email.<br>Do not share this code with anyone.</div>"
        "</td></tr>"
        "<tr><td style=\"padding:18px 40px;border-top:1px solid rgba(255,255,255,0.05);text-align:center;\">"
        "<div style=\"color:#404050;font-size:12px;\">&copy; 2026 Lonely Hub &middot; Minecraft Library</div>"
        "</td></tr></table></td></tr></table></body></html>"
    )


def welcome_email_html(username):
    return (
        "<!DOCTYPE html><html><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"></head>"
        "<body style=\"margin:0;padding:0;background:#0f0f1a;font-family:Arial,sans-serif;\">"
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#0f0f1a;padding:40px 0;\">"
        "<tr><td align=\"center\">"
        "<table width=\"520\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#1a1a2e;border-radius:16px;overflow:hidden;border:1px solid rgba(255,255,255,0.07);max-width:520px;width:100%;\">"
        "<tr><td style=\"padding:36px 40px 24px;text-align:center;background:linear-gradient(135deg,rgba(250,80,80,0.08),rgba(139,92,246,0.08));border-bottom:1px solid rgba(255,255,255,0.06);\">"
        "<img src=\"https://i.imgur.com/xY7M2iE.jpeg\" width=\"64\" height=\"64\" style=\"border-radius:14px;margin-bottom:16px;display:block;margin-left:auto;margin-right:auto;border:2px solid rgba(250,80,80,0.25);\">"
        "<div style=\"color:#ffffff;font-size:22px;font-weight:700;\">Welcome to Lonely Hub!</div>"
        "<div style=\"color:#606078;font-size:13px;margin-top:4px;\">Minecraft Library</div>"
        "</td></tr>"
        "<tr><td style=\"padding:32px 40px 28px;\">"
        f"<div style=\"color:#f0f0f8;font-size:17px;font-weight:600;margin-bottom:12px;\">Hey <span style=\"color:#fa5050;\">{username}</span>, great to have you!</div>"
        "<div style=\"color:#a0a0b8;font-size:14px;line-height:1.7;margin-bottom:24px;\">"
        "You\'ve just joined <strong style=\"color:#f0f0f8;\">Lonely Hub</strong> &mdash; the community-driven Minecraft mod library. Discover, upload, and share your favourite mods with thousands of players."
        "</div>"
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"margin-bottom:28px;\">"
        "<tr>"
        "<td style=\"padding:14px 10px;background:rgba(250,80,80,0.06);border-radius:10px;text-align:center;vertical-align:top;width:30%;\">"
        "<div style=\"font-size:22px;margin-bottom:6px;\">&#128230;</div>"
        "<div style=\"color:#f0f0f8;font-size:12px;font-weight:600;\">Upload Mods</div>"
        "<div style=\"color:#606070;font-size:11px;margin-top:2px;\">Share your creations</div>"
        "</td><td style=\"width:5%;\"></td>"
        "<td style=\"padding:14px 10px;background:rgba(139,92,246,0.06);border-radius:10px;text-align:center;vertical-align:top;width:30%;\">"
        "<div style=\"font-size:22px;margin-bottom:6px;\">&#128269;</div>"
        "<div style=\"color:#f0f0f8;font-size:12px;font-weight:600;\">Browse Library</div>"
        "<div style=\"color:#606070;font-size:11px;margin-top:2px;\">Find new mods</div>"
        "</td><td style=\"width:5%;\"></td>"
        "<td style=\"padding:14px 10px;background:rgba(59,130,246,0.06);border-radius:10px;text-align:center;vertical-align:top;width:30%;\">"
        "<div style=\"font-size:22px;margin-bottom:6px;\">&#128172;</div>"
        "<div style=\"color:#f0f0f8;font-size:12px;font-weight:600;\">Forum</div>"
        "<div style=\"color:#606070;font-size:11px;margin-top:2px;\">Join the community</div>"
        "</td></tr></table>"
        "<div style=\"text-align:center;\">"
        "<a href=\"https://lonelyhub.replit.app\" style=\"display:inline-block;background:linear-gradient(135deg,#fa5050,#c0392b);color:#fff;font-weight:700;font-size:14px;padding:13px 32px;border-radius:10px;text-decoration:none;\">Get Started</a>"
        "</div></td></tr>"
        "<tr><td style=\"padding:18px 40px;border-top:1px solid rgba(255,255,255,0.05);text-align:center;\">"
        "<div style=\"color:#404050;font-size:12px;\">&copy; 2026 Lonely Hub &middot; Minecraft Library</div>"
        "</td></tr></table></td></tr></table></body></html>"
    )


def notify_email_html(notification_type, username, **kwargs):
    def _base(accent, heading, body):
        return (
            "<!DOCTYPE html><html><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"></head>"
            "<body style=\"margin:0;padding:0;background:#0f0f1a;font-family:Arial,sans-serif;\">"
            "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#0f0f1a;padding:40px 0;\">"
            "<tr><td align=\"center\">"
            "<table width=\"520\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#1a1a2e;border-radius:16px;overflow:hidden;border:1px solid rgba(255,255,255,0.07);max-width:520px;width:100%;\">"
            f"<tr><td style=\"height:3px;background:{accent};\"></td></tr>"
            "<tr><td style=\"padding:32px 40px 24px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.06);\">"
            "<img src=\"https://i.imgur.com/xY7M2iE.jpeg\" width=\"48\" height=\"48\" style=\"border-radius:11px;margin-bottom:12px;display:block;margin-left:auto;margin-right:auto;\">"
            "<div style=\"color:#fff;font-size:18px;font-weight:700;\">Lonely Hub</div>"
            "<div style=\"color:#606078;font-size:12px;margin-top:2px;\">Minecraft Library</div>"
            "</td></tr>"
            f"<tr><td style=\"padding:32px 40px 28px;\"><div style=\"color:#f0f0f8;font-size:17px;font-weight:700;margin-bottom:14px;\">{heading}</div>{body}</div></td></tr>"
            "<tr><td style=\"padding:16px 40px;border-top:1px solid rgba(255,255,255,0.05);text-align:center;\">"
            "<div style=\"color:#404050;font-size:12px;\">&copy; 2026 Lonely Hub &middot; Minecraft Library</div>"
            "</td></tr></table></td></tr></table></body></html>"
        ).replace("</div></div>", "</div>")

    if notification_type == "verified_granted":
        body = (
            f"<div style=\"color:#a0a0b8;font-size:14px;line-height:1.7;margin-bottom:18px;\">Hi <strong style=\"color:#fff;\">{username}</strong>, your account has been granted the <strong style=\"color:#3b82f6;\">Verified</strong> badge by an administrator. The badge will now appear next to your name across the platform.</div>"
            "<a href=\"https://hubmc.onrender.com\" style=\"display:inline-block;background:#3b82f6;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:700;font-size:13px;\">Visit Lonely Hub</a>"
        )
        return _base("linear-gradient(90deg,#3b82f6,#06b6d4)", "Verified badge granted", body)

    elif notification_type == "verified_removed":
        body = (
            f"<div style=\"color:#a0a0b8;font-size:14px;line-height:1.7;margin-bottom:8px;\">Hi <strong style=\"color:#fff;\">{username}</strong>, your <strong style=\"color:#ef4444;\">Verified</strong> badge has been removed from your account by an administrator.</div>"
            "<div style=\"color:#606070;font-size:13px;margin-top:10px;\">If you believe this is a mistake, please contact us.</div>"
        )
        return _base("#ef4444", "Verified badge removed", body)

    elif notification_type == "admin_granted":
        body = (
            f"<div style=\"color:#a0a0b8;font-size:14px;line-height:1.7;margin-bottom:18px;\">Hi <strong style=\"color:#fff;\">{username}</strong>, you have been granted <strong style=\"color:#4ade80;\">Admin</strong> privileges on Lonely Hub by an administrator. You now have access to the admin control panel.</div>"
            "<a href=\"https://hubmc.onrender.com/api/v1/auth/admin\" style=\"display:inline-block;background:linear-gradient(135deg,#4ade80,#16a34a);color:#000;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:700;font-size:13px;\">Open Admin Panel</a>"
        )
        return _base("linear-gradient(90deg,#4ade80,#22d3ee)", "Admin access granted", body)

    elif notification_type == "admin_removed":
        body = (
            f"<div style=\"color:#a0a0b8;font-size:14px;line-height:1.7;margin-bottom:8px;\">Hi <strong style=\"color:#fff;\">{username}</strong>, your <strong style=\"color:#f97316;\">Admin</strong> privileges on Lonely Hub have been revoked by an administrator.</div>"
            "<div style=\"color:#606070;font-size:13px;margin-top:10px;\">If you believe this is a mistake, please contact us.</div>"
        )
        return _base("#f97316", "Admin access revoked", body)

    elif notification_type == "banned":
        duration_text = kwargs.get("duration_text", "")
        dur_block = f"<div style=\"background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.18);border-radius:8px;padding:10px 14px;margin:14px 0;font-size:13px;color:#ef4444;font-weight:600;\">Duration: {duration_text}</div>" if duration_text else ""
        body = (
            f"<div style=\"color:#a0a0b8;font-size:14px;line-height:1.7;\">Hi <strong style=\"color:#fff;\">{username}</strong>, your account has been <strong style=\"color:#ef4444;\">banned</strong> from Lonely Hub by an administrator.</div>"
            f"{dur_block}"
            "<div style=\"color:#606070;font-size:13px;margin-top:8px;\">If you believe this is a mistake, please contact us.</div>"
        )
        return _base("#ef4444", "Account banned", body)

    elif notification_type == "muted":
        duration_text = kwargs.get("duration_text", "")
        dur_block = f"<div style=\"background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.18);border-radius:8px;padding:10px 14px;margin:14px 0;font-size:13px;color:#fbbf24;font-weight:600;\">Duration: {duration_text}</div>" if duration_text else ""
        body = (
            f"<div style=\"color:#a0a0b8;font-size:14px;line-height:1.7;\">Hi <strong style=\"color:#fff;\">{username}</strong>, your account has been <strong style=\"color:#fbbf24;\">muted</strong> on Lonely Hub. You will not be able to upload mods or post in the forum during the mute period.</div>"
            f"{dur_block}"
            "<div style=\"color:#606070;font-size:13px;margin-top:8px;\">If you believe this is a mistake, please contact us.</div>"
        )
        return _base("#fbbf24", "Account muted", body)

    elif notification_type == "mod_deleted":
        mod_name = kwargs.get("mod_name", "your content")
        mod_type = kwargs.get("mod_type", "mod").capitalize()
        body = (
            f"<div style=\"color:#a0a0b8;font-size:14px;line-height:1.7;margin-bottom:14px;\">Hi <strong style=\"color:#fff;\">{username}</strong>, your {mod_type.lower()} <strong style=\"color:#fff;\">\"{mod_name}\"</strong> has been removed from Lonely Hub by an administrator.</div>"
            "<div style=\"color:#606070;font-size:13px;\">If you believe this is a mistake or need more information, please contact us.</div>"
        )
        return _base("#ef4444", f"{mod_type} removed by admin", body)

    return ""


def _send_notify_bg(to_email, subject, html_body):
    threading.Thread(target=lambda: send_email_html(to_email, subject, html_body), daemon=True).start()


def generate_otp():
    return str(secrets.randbelow(900000) + 100000)


def store_otp(email, purpose):
    otp = generate_otp()
    sessions = load_json("sessions-data.json")
    sessions.setdefault("otps", {})[email] = {
        "code": otp,
        "purpose": purpose,
        "expires": (datetime.now() + timedelta(minutes=10)).isoformat()
    }
    save_json("sessions-data.json", sessions)
    return otp


def verify_otp_code(email, code, purpose):
    sessions = load_json("sessions-data.json")
    otps = sessions.get("otps", {})
    entry = otps.get(email)
    if not entry:
        return False
    if entry["purpose"] != purpose:
        return False
    if datetime.fromisoformat(entry["expires"]) < datetime.now():
        return False
    if entry["code"] != code:
        return False
    otps.pop(email)
    sessions["otps"] = otps
    save_json("sessions-data.json", sessions)
    return True


def get_user_by_email(email):
    if not email:
        return None
    accounts = load_json("accounts-data.json")
    return next((u for u in accounts["users"] if (u.get("email") or "").lower() == email.lower()), None)


def verify_hcaptcha(token):
    if not token:
        return False
    if not HCAPTCHA_SECRET:
        print("[CAPTCHA] HCAPTCHA_SECRET not set — skipping server-side verify")
        return True
    try:
        resp = requests.post("https://hcaptcha.com/siteverify", data={
            "secret": HCAPTCHA_SECRET,
            "response": token
        }, timeout=5)
        result = resp.json()
        if not result.get("success", False):
            print(f"[CAPTCHA] Failed: {result.get('error-codes', [])}")
        return result.get("success", False)
    except Exception as ex:
        print(f"[CAPTCHA] Exception: {ex}")
        return False
def is_admin(user):
    if not user or user.get("tag") != "admin":
        return False
    admin_until = user.get("admin_until")
    if admin_until == "lifetime":
        return True
    if admin_until:
        try:
            return datetime.now() < datetime.fromisoformat(admin_until)
        except Exception:
            return False
    return False


def is_muted(user):
    if not user or not user.get("muted_until"):
        return False
    try:
        return datetime.now() < datetime.fromisoformat(user["muted_until"])
    except Exception:
        return False


def is_banned(user):
    if not user or not user.get("banned_until"):
        return False
    if user["banned_until"] == "lifetime":
        return True
    try:
        return datetime.now() < datetime.fromisoformat(user["banned_until"])
    except Exception:
        return False


def get_ban_remaining(user):
    if not user:
        return None
    banned_until = user.get("banned_until")
    if banned_until == "lifetime":
        return "permanent"
    if not banned_until:
        return None
    try:
        delta = datetime.fromisoformat(banned_until) - datetime.now()
        if delta.total_seconds() <= 0:
            return None
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        return f"{hours}h {minutes}m"
    except Exception:
        return None


def get_site_stats():
    accounts = load_json("accounts-data.json")
    mods_data = load_json("mods-data.json")
    sessions = load_json("sessions-data.json")
    return {
        "total_mods": len(mods_data.get("mods", [])),
        "total_users": len(accounts.get("users", [])),
        "active_users": sum(
            1 for s in sessions.get("sessions", {}).values()
            if datetime.fromisoformat(s["expires"]) > datetime.now()
        ),
        "total_downloads": sum(m.get("downloads", 0) for m in mods_data.get("mods", [])),
        "total_views": sum(m.get("views", 0) for m in mods_data.get("mods", [])),
        "uptime": "99%"
    }


def get_today_str():
    return datetime.now().strftime("%Y-%m-%d")


def track_daily(mod, stat_type):
    today = get_today_str()
    mod.setdefault("daily_stats", {}).setdefault(today, {"views": 0, "downloads": 0})
    mod["daily_stats"][today][stat_type] = mod["daily_stats"][today].get(stat_type, 0) + 1


def get_chart_data(mods, days=14):
    dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days - 1, -1, -1)]
    views = [sum(m.get("daily_stats", {}).get(d, {}).get("views", 0) for m in mods) for d in dates]
    downloads = [sum(m.get("daily_stats", {}).get(d, {}).get("downloads", 0) for m in mods) for d in dates]
    labels = [(datetime.now() - timedelta(days=i)).strftime("%d/%m") for i in range(days - 1, -1, -1)]
    return labels, views, downloads


def get_avg_rating(mod):
    ratings = mod.get("ratings", [])
    if not ratings:
        return 0
    return round(sum(r["stars"] for r in ratings) / len(ratings), 1)


def get_user_by_id(uid):
    accounts = load_json("accounts-data.json")
    return next((u for u in accounts.get("users", []) if u["id"] == uid), None)


def get_user_by_username(username):
    accounts = load_json("accounts-data.json")
    return next((u for u in accounts.get("users", []) if u["username"].lower() == username.lower()), None)


PER_PAGE = 12

FORUM_CATEGORIES = [
    "General Discussion",
    "Mod Help & Support",
    "Mod Showcases",
    "Suggestions",
    "Bug Reports",
    "Off-Topic",
]

FORUM_PER_PAGE = 15
ANONYMOUS_AVATAR = "https://i.imgur.com/BCzwCla.png"


_SKIP_LOG_PREFIXES = ('/static/', '/static/css/', '/static/js/', '/static/uploads/', '/static/forum_uploads/')

@app.before_request
def _req_start():
    g._req_t0 = time.monotonic()

@app.after_request
def _req_log(response):
    try:
        skip = any(request.path.startswith(p) for p in _SKIP_LOG_PREFIXES)
        if not skip:
            elapsed = (time.monotonic() - g._req_t0) * 1000
            status = response.status_code
            if status >= 500:
                lv = 'error'
            elif status >= 400:
                lv = 'warn'
            else:
                lv = 'http'
            msg = f'{request.method} {request.full_path.rstrip("?")} {status} {elapsed:.0f}ms'
            LOG_BUFFER.append({'t': datetime.now().isoformat(timespec='milliseconds'), 'level': lv, 'msg': msg})
    except Exception:
        pass
    return response

@app.before_request
def check_ban():
    allowed_paths = ["/error", "/static", "/login", "/register", "/logout"]
    if any(request.path.startswith(p) for p in allowed_paths):
        return None
    try:
        user = get_session_user(request)
    except Exception:
        return None
    if user and is_banned(user):
        remaining = get_ban_remaining(user)
        ban_msg = "You+have+been+banned.+Ban+expires+in:+" + remaining if remaining else "You+have+been+banned+from+Lonely+Hub"
        return redirect(f"/error?code=403&msg={ban_msg}")


@app.route("/")
def index():
    user = get_session_user(request)
    stats = get_site_stats()
    today = get_today_str()
    mods_data = load_json("mods-data.json")
    trending = sorted(mods_data["mods"],
                      key=lambda m: m.get("daily_stats", {}).get(today, {}).get("views", 0),
                      reverse=True)[:5]
    for m in trending:
        m["avg_rating"] = get_avg_rating(m)
        m.setdefault("tags", [])
        m.setdefault("comments", [])
        m.setdefault("daily_stats", {})
    return render_template("index.html", user=user, stats=stats, hcaptcha_site_key=HCAPTCHA_SITE_KEY, trending=trending)


@app.route("/mods")
def mods_page():
    user = get_session_user(request)
    mods_data = load_json("mods-data.json")
    mods = mods_data["mods"]
    search = request.args.get("search", "").strip().lower()
    filter_by = request.args.get("filter", "newest")
    loader_filter = request.args.get("loader", "")
    tag_filter = request.args.get("tag", "").strip().lower()
    version_filter = request.args.get("version", "").strip()
    page = int(request.args.get("page", 1))

    uploader_filter = request.args.get("uploader", "").strip().lower()
    mods = [m for m in mods if m.get("type", "mod") != "client"]
    if search:
        mods = [m for m in mods if search in m["name"].lower() or search in m.get("description", "").lower()]
    if loader_filter:
        mods = [m for m in mods if loader_filter in m.get("loaders", [])]
    if tag_filter:
        mods = [m for m in mods if tag_filter in [t.lower() for t in m.get("tags", [])]]
    if version_filter:
        mods = [m for m in mods if any(version_filter.lower() in v.lower() for v in m.get("mc_versions", []))]
    if uploader_filter:
        mods = [m for m in mods if uploader_filter in m.get("uploader_username", "").lower()]

    if filter_by == "most_download":
        mods = sorted(mods, key=lambda m: m.get("downloads", 0), reverse=True)
    elif filter_by == "most_popular":
        mods = sorted(mods, key=lambda m: m.get("views", 0), reverse=True)
    elif filter_by == "top_rated":
        mods = sorted(mods, key=lambda m: get_avg_rating(m), reverse=True)
    else:
        mods = sorted(mods, key=lambda m: m.get("created_at", ""), reverse=True)

    total = len(mods)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))
    paginated = mods[(page - 1) * PER_PAGE:page * PER_PAGE]

    all_mods = mods_data["mods"]
    all_ratings = [r for m in all_mods for r in m.get("ratings", [])]
    avg_rate = round(sum(r["stars"] for r in all_ratings) / len(all_ratings), 1) if all_ratings else 0

    tag_counts = {}
    for m in all_mods:
        for t in m.get("tags", []):
            t = t.strip().lower()
            if t:
                tag_counts[t] = tag_counts.get(t, 0) + 1
    popular_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]

    for m in paginated:
        m["avg_rating"] = get_avg_rating(m)
        m.setdefault("tags", [])

    return render_template("mods.html", user=user, mods=paginated,
                           total=total, page=page, total_pages=total_pages,
                           search=search, filter_by=filter_by, loader_filter=loader_filter,
                           tag_filter=tag_filter, version_filter=version_filter,
                           uploader_filter=uploader_filter,
                           popular_tags=popular_tags,
                           total_downloads=sum(m.get("downloads", 0) for m in all_mods),
                           total_views=sum(m.get("views", 0) for m in all_mods),
                           avg_rate=avg_rate, total_lib=len(all_mods))


@app.route("/mods/<int:mod_id>/info")
def mod_info(mod_id):
    user = get_session_user(request)
    mods_data = load_json("mods-data.json")
    mod = next((m for m in mods_data["mods"] if m["id"] == mod_id), None)
    if not mod:
        return redirect(f"/error?code=404&msg=Page+not+found")
    mod["views"] = mod.get("views", 0) + 1
    track_daily(mod, "views")
    save_json("mods-data.json", mods_data)
    mod["avg_rating"] = get_avg_rating(mod)
    mod.setdefault("tags", [])
    mod.setdefault("comments", [])
    mod.setdefault("daily_stats", {})
    uploader = get_user_by_id(mod.get("uploader_id", ""))
    is_bookmarked = False
    if user:
        accounts_bm = load_json("accounts-data.json")
        bm_user = next((u for u in accounts_bm["users"] if u["id"] == user["id"]), None)
        if bm_user:
            is_bookmarked = mod["id"] in bm_user.get("bookmarks", [])
    user_rated = False
    user_rate_blocked = False
    if user:
        for r in mod.get("ratings", []):
            if r["user_id"] == user["id"]:
                if datetime.now() - datetime.fromisoformat(r["rated_at"]) < timedelta(hours=12):
                    user_rated = True
                    user_rate_blocked = True
    return render_template("mod_info.html", user=user, mod=mod, uploader=uploader,
                           hcaptcha_site_key=HCAPTCHA_SITE_KEY,
                           user_rated=user_rated, user_rate_blocked=user_rate_blocked,
                           is_bookmarked=is_bookmarked)


@app.route("/mods/<int:mod_id>/download")
def mod_download(mod_id):
    mods_data = load_json("mods-data.json")
    mod = next((m for m in mods_data["mods"] if m["id"] == mod_id), None)
    if not mod:
        user = get_session_user(request)
        return redirect(f"/error?code=404&msg=Page+not+found")
    mod["downloads"] = mod.get("downloads", 0) + 1
    track_daily(mod, "downloads")
    save_json("mods-data.json", mods_data)
    dl = mod.get("download_link", "")
    if dl:
        return redirect(dl)
    return redirect(url_for("mod_info", mod_id=mod_id))


@app.route("/api/rate/<int:mod_id>", methods=["POST"])
def rate_mod(mod_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    data = request.get_json(silent=True) or {}
    stars = data.get("stars", 0)
    if not (1 <= stars <= 5):
        return jsonify({"success": False, "error": "Invalid rating"}), 400
    mods_data = load_json("mods-data.json")
    mod = next((m for m in mods_data["mods"] if m["id"] == mod_id), None)
    if not mod:
        return jsonify({"success": False, "error": "Mod not found"}), 404
    ratings = mod.get("ratings", [])
    for r in ratings:
        if r["user_id"] == user["id"]:
            if datetime.now() - datetime.fromisoformat(r["rated_at"]) < timedelta(hours=12):
                return jsonify({"success": False, "error": "Already rated in last 12h"}), 429
            ratings.remove(r)
            break
    ratings.append({"user_id": user["id"], "stars": stars, "rated_at": datetime.now().isoformat()})
    mod["ratings"] = ratings
    save_json("mods-data.json", mods_data)
    avg = get_avg_rating(mod)
    return jsonify({"success": True, "avg": avg, "count": len(ratings)})


@app.route("/login", methods=["GET", "POST"])
def login():
    user = get_session_user(request)
    if user:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"
        captcha_token = request.form.get("h-captcha-response", "")
        if not verify_hcaptcha(captcha_token):
            error = "Please complete the captcha"
        else:
            accounts = load_json("accounts-data.json")
            found = next((u for u in accounts["users"] if u["username"].lower() == username.lower() or (u.get("email") or "").lower() == username.lower()), None)
            if found and found.get("password") and check_password_hash(found["password"], password):
                token, expires = create_session(found["id"])
                next_url = request.args.get("next", url_for("index"))
                resp = make_response(jsonify({"success": True, "redirect": next_url}))
                resp.set_cookie("session_token", token, expires=expires, httponly=True, secure=True, samesite="Lax")
                if remember:
                    r_series, r_token, r_exp = create_remember_token(found["id"])
                    resp.set_cookie("remember_me", f"{r_series}:{r_token}",
                        expires=r_exp, httponly=True, secure=True, samesite="Lax", max_age=30*24*3600)
                return resp
            else:
                error = "Invalid username or password"
        return jsonify({"success": False, "error": error})
    next_url = request.args.get("next", "")
    return render_template("login.html", user=None, error=error, next_url=next_url, hcaptcha_site_key=HCAPTCHA_SITE_KEY)


@app.route("/api/send-otp", methods=["POST"])
def api_send_otp():
    try:
        data = request.get_json(silent=True) or {}
        purpose = data.get("purpose", "")
        email = ""
        if purpose in ("register", "reset"):
            email = (data.get("email") or "").strip().lower()
            captcha_token = data.get("captchaToken", "") or data.get("captcha_token", "")
            if not captcha_token:
                return jsonify({"success": False, "error": "Please complete the captcha to continue"})
            if not verify_hcaptcha(captcha_token):
                return jsonify({"success": False, "error": "Captcha verification failed. Please try again."})
                return jsonify({"success": False, "error": "Please complete the captcha"})
            if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
                return jsonify({"success": False, "error": "Invalid email address"})
            if purpose == "register":
                if get_user_by_email(email):
                    return jsonify({"success": False, "error": "Email already in use"})
            elif purpose == "reset":
                if not get_user_by_email(email):
                    return jsonify({"success": False, "error": "No account with that email address"})
        elif purpose in ("verify_email", "change_password", "verify_current_email", "remove_email", "unlink_google"):
            logged_user = get_session_user(request)
            if not logged_user:
                return jsonify({"success": False, "error": "Not logged in"})
            email = logged_user.get("email", "").strip().lower()
            if not email:
                return jsonify({"success": False, "error": "No email linked to your account"})
            if purpose == "change_password" and not logged_user.get("email_verified"):
                return jsonify({"success": False, "error": "Email must be verified first"})
            if purpose == "verify_current_email" and not logged_user.get("email_verified"):
                return jsonify({"success": False, "error": "Current email is not verified"})
        elif purpose == "change_email":
            logged_user = get_session_user(request)
            if not logged_user:
                return jsonify({"success": False, "error": "Not logged in"})
            email = (data.get("email") or "").strip().lower()
            if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
                return jsonify({"success": False, "error": "Invalid email address"})
            accounts = load_json("accounts-data.json")
            if any((u.get("email") or "").lower() == email and u["id"] != logged_user["id"] for u in accounts["users"]):
                return jsonify({"success": False, "error": "Email already used by another account"})
        else:
            return jsonify({"success": False, "error": "Invalid purpose"})
        purpose_texts = {
            "register": "to complete your registration",
            "reset": "to reset your password",
            "verify_email": "to verify your email address",
            "change_password": "to confirm your password change",
            "change_email": "to verify your new email address",
            "verify_current_email": "to confirm your identity before changing your email",
            "remove_email": "to confirm removal of your linked email",
            "unlink_google": "to confirm disconnecting your Google account"
        }
        otp = store_otp(email, purpose)
        sent = send_email_html(email, "Lonely Hub — Verification Code", otp_email_html(otp, purpose_texts.get(purpose, "")))
        if not sent:
            return jsonify({"success": False, "error": "Failed to send email. Please check that your email address is correct and try again."})
        return jsonify({"success": True})


    except Exception as ex:
        print(f"[ERROR] api_send_otp: {type(ex).__name__}: {ex}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": f"Server error: {type(ex).__name__}: {ex}"}), 500
@app.route("/api/account/add-email", methods=["POST"])
def add_email():
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Not logged in"})
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return jsonify({"success": False, "error": "Invalid email address"})
    accounts = load_json("accounts-data.json")
    if any((u.get("email") or "").lower() == email and u["id"] != user["id"] for u in accounts["users"]):
        return jsonify({"success": False, "error": "Email already used by another account"})
    target = next((u for u in accounts["users"] if u["id"] == user["id"]), None)
    if not target:
        return jsonify({"success": False, "error": "User not found"})
    target["email"] = email
    target["email_verified"] = False
    save_json("accounts-data.json", accounts)
    otp = store_otp(email, "verify_email")
    sent = send_email_html(email, "Lonely Hub — Verify Your Email", otp_email_html(otp, "to verify your email address"))
    if not sent:
        return jsonify({"success": False, "error": "Failed to send verification email. Please check your email address."})
    return jsonify({"success": True})


@app.route("/api/account/verify-email", methods=["POST"])
def verify_email_route():
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Not logged in"})
    data = request.get_json(silent=True) or {}
    otp_code = data.get("otp_code", "").strip()
    email = user.get("email", "").strip().lower()
    if not email:
        return jsonify({"success": False, "error": "No email linked to your account"})
    if not verify_otp_code(email, otp_code, "verify_email"):
        return jsonify({"success": False, "error": "Invalid or expired code"})
    accounts = load_json("accounts-data.json")
    target = next((u for u in accounts["users"] if u["id"] == user["id"]), None)
    if target:
        target["email_verified"] = True
        save_json("accounts-data.json", accounts)
    return jsonify({"success": True})


@app.route("/register", methods=["GET", "POST"])
def register():
    user = get_session_user(request)
    if user:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"
        otp_code = request.form.get("otp_code", "").strip()
        tos_accepted = request.form.get("tos_accepted") == "on"
        if not tos_accepted:
            error = "You must accept the Terms of Service to register"
        elif len(username) < 3 or len(username) > 20:
            error = "Username must be 3-20 characters"
        elif not username.replace("_", "").replace("-", "").isalnum():
            error = "Username can only contain letters, numbers, - and _"
        elif not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            error = "Invalid email address"
        elif len(password) < 6:
            error = "Password must be at least 6 characters"
        elif not otp_code:
            error = "Email verification code is required"
        elif not verify_otp_code(email, otp_code, "register"):
            error = "Invalid or expired verification code"
        else:
            accounts = load_json("accounts-data.json")
            if any(u["username"].lower() == username.lower() for u in accounts["users"]):
                error = "Username already taken"
            elif any((u.get("email") or "").lower() == email for u in accounts["users"]):
                error = "Email already in use"
            else:
                new_id = str(uuid.uuid4())
                accounts["users"].append({
                    "id": new_id,
                    "username": username,
                    "display_name": username,
                    "email": email,
                    "email_verified": True,
                    "password": generate_password_hash(password),
                    "tag": "user",
                    "avatar": "",
                    "banner": "",
                    "description": "Hello World!",
                    "followers": [],
                    "following": [],
                    "created_at": datetime.now().isoformat(),
                    "username_last_changed": None,
                    "muted_until": None,
                    "banned_until": None,
                    "admin_until": None
                })
                save_json("accounts-data.json", accounts)
                threading.Thread(target=send_email_html, args=(email, "Welcome to Lonely Hub!", welcome_email_html(username)), daemon=True).start()
                token, expires = create_session(new_id)
                next_url = request.args.get("next", url_for("index"))
                resp = make_response(jsonify({"success": True, "redirect": next_url}))
                resp.set_cookie("session_token", token, expires=expires, httponly=True, secure=True, samesite="Lax")
                if remember:
                    r_series, r_token, r_exp = create_remember_token(new_id)
                    resp.set_cookie("remember_me", f"{r_series}:{r_token}",
                        expires=r_exp, httponly=True, secure=True, samesite="Lax", max_age=30*24*3600)
                return resp
        return jsonify({"success": False, "error": error})
    next_url = request.args.get("next", "")
    return render_template("register.html", user=None, error=error, next_url=next_url, hcaptcha_site_key=HCAPTCHA_SITE_KEY)


@app.route("/logout")
def logout():
    token = request.cookies.get("session_token")
    if token:
        sessions = load_json("sessions-data.json")
        sessions.get("sessions", {}).pop(token, None)
        save_json("sessions-data.json", sessions)
    rm_cookie = request.cookies.get("remember_me")
    if rm_cookie and ":" in rm_cookie:
        series = rm_cookie.split(":", 1)[0]
        sessions = load_json("sessions-data.json")
        sessions["remember_tokens"] = [t for t in sessions.get("remember_tokens", []) if t["series"] != series]
        save_json("sessions-data.json", sessions)
    resp = make_response(redirect(url_for("index")))
    resp.delete_cookie("session_token")
    resp.delete_cookie("remember_me")
    return resp




@app.route("/terms-of-service")
def terms_of_service():
    user = get_session_user(request)
    return render_template("legal/terms.html", user=user)

@app.route("/privacy-policy")
def privacy_policy():
    user = get_session_user(request)
    return render_template("legal/privacy.html", user=user)

@app.route("/cookie-policy")
def cookie_policy():
    user = get_session_user(request)
    return render_template("legal/cookie_policy.html", user=user)

@app.route("/community-guidelines")
def community_guidelines():
    user = get_session_user(request)
    return render_template("legal/community_guidelines.html", user=user)

@app.route("/disclaimer")
def disclaimer():
    user = get_session_user(request)
    return render_template("legal/disclaimer.html", user=user)

@app.route("/forgot-password")
def forgot_password():
    user = get_session_user(request)
    if user:
        return redirect(url_for("index"))
    return render_template("forgot_password.html", user=None, hcaptcha_site_key=HCAPTCHA_SITE_KEY)


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    user = get_session_user(request)
    if user:
        return redirect(url_for("index"))
    if request.method == "POST":
        if request.is_json:
            body = request.get_json(silent=True) or {}
            email = body.get("email", "").strip().lower()
            otp_code = body.get("otp_code", "").strip()
            new_password = body.get("new_password", "")
            confirm_password = body.get("confirm_password", new_password)
        else:
            email = request.form.get("email", "").strip().lower()
            otp_code = request.form.get("otp_code", "").strip()
            new_password = request.form.get("new_password", "")
            confirm_password = new_password
        if len(new_password) < 6:
            return jsonify({"success": False, "error": "Password must be at least 6 characters"})
        if new_password != confirm_password:
            return jsonify({"success": False, "error": "Passwords do not match"})
        if not verify_otp_code(email, otp_code, "reset"):
            return jsonify({"success": False, "error": "Invalid or expired verification code"})
        accounts = load_json("accounts-data.json")
        target = next((u for u in accounts["users"] if (u.get("email") or "").lower() == email), None)
        if not target:
            return jsonify({"success": False, "error": "Account not found"})
        target["password"] = generate_password_hash(new_password)
        save_json("accounts-data.json", accounts)
        return jsonify({"success": True})
    email = request.args.get("email", "")
    return render_template("reset_password.html", user=None, email=email)


@app.route("/auth/google")
def google_login():
    state = secrets.token_hex(16)
    sessions = load_json("sessions-data.json")
    sessions.setdefault("oauth_states", {})[state] = {
        "expires": (datetime.now() + timedelta(minutes=10)).isoformat()
    }
    save_json("sessions-data.json", sessions)
    redirect_uri = GOOGLE_REDIRECT_URI or (request.url_root.rstrip("/") + "/auth/google/callback")
    params = urllib.parse.urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account"
    })
    return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@app.route("/auth/google/callback")
def google_callback():
    code = request.args.get("code")
    state = request.args.get("state")
    if not code or not state:
        return redirect(url_for("login"))
    sessions = load_json("sessions-data.json")
    oauth_states = sessions.get("oauth_states", {})
    state_entry = oauth_states.pop(state, None)
    sessions["oauth_states"] = oauth_states
    save_json("sessions-data.json", sessions)
    if not state_entry:
        return redirect(url_for("login"))
    redirect_uri = GOOGLE_REDIRECT_URI or (request.url_root.rstrip("/") + "/auth/google/callback")
    token_resp = requests.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    })
    if not token_resp.ok:
        return redirect(url_for("login"))
    access_token = token_resp.json().get("access_token")
    user_info_resp = requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    if not user_info_resp.ok:
        return redirect(url_for("login"))
    ginfo = user_info_resp.json()
    google_id = ginfo.get("sub")
    g_email = ginfo.get("email", "")
    g_name = ginfo.get("name", "")
    accounts = load_json("accounts-data.json")
    found_user = next((u for u in accounts["users"] if u.get("google_id") == google_id), None)
    if not found_user and g_email:
        found_user = next((u for u in accounts["users"] if (u.get("email") or "").lower() == g_email.lower()), None)
        if found_user:
            found_user["google_id"] = google_id
            save_json("accounts-data.json", accounts)
    if not found_user:
        email_prefix = g_email.split("@")[0] if g_email else ""
        base_username = re.sub(r'[^a-zA-Z0-9_-]', '', email_prefix)[:20] or "user"
        username = base_username
        suffix = 1
        while any(u["username"].lower() == username.lower() for u in accounts["users"]):
            username = f"{base_username}{suffix}"
            suffix += 1
        new_id = str(uuid.uuid4())
        found_user = {
            "id": new_id,
            "username": username,
            "display_name": g_name or username,
            "email": None,
            "email_verified": False,
            "password": None,
            "google_id": google_id,
            "tag": "user",
            "avatar": ginfo.get("picture", ""),
            "banner": "",
            "description": "Hello World!",
            "followers": [],
            "following": [],
            "created_at": datetime.now().isoformat(),
            "username_last_changed": None,
            "muted_until": None,
            "banned_until": None,
            "admin_until": None
        }
        accounts["users"].append(found_user)
        save_json("accounts-data.json", accounts)
    session_token, expires = create_session(found_user["id"])
    device_token = issue_device_token()
    resp = make_response(redirect(url_for("index")))
    resp.set_cookie("session_token", session_token, expires=expires, httponly=True, secure=True, samesite="Lax")
    resp.set_cookie("device_token", device_token, max_age=365 * 24 * 3600, httponly=True, secure=True, samesite="Lax")
    return resp


@app.route("/api/account/unlink-google", methods=["POST"])
def unlink_google():
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Not logged in"})
    accounts = load_json("accounts-data.json")
    target = next((u for u in accounts["users"] if u["id"] == user["id"]), None)
    if not target:
        return jsonify({"success": False, "error": "User not found"})
    if not target.get("password") and not target.get("discord_id"):
        return jsonify({"success": False, "error": "Cannot disconnect Google — you have no other login method"})
    if target.get("email") and target.get("email_verified"):
        data = request.get_json(silent=True) or {}
        otp_code = data.get("otp_code", "").strip()
        if not otp_code:
            return jsonify({"success": False, "error": "Verification code required"})
        if not verify_otp_code(target["email"].lower(), otp_code, "unlink_google"):
            return jsonify({"success": False, "error": "Invalid or expired code"})
    target.pop("google_id", None)
    save_json("accounts-data.json", accounts)
    return jsonify({"success": True})


@app.route("/api/account/authorize-email-change", methods=["POST"])
def authorize_email_change():
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Not logged in"})
    data = request.get_json(silent=True) or {}
    otp_code = data.get("otp_code", "").strip()
    current_email = user.get("email", "").strip().lower()
    if not current_email:
        return jsonify({"success": False, "error": "No current email to verify"})
    if not verify_otp_code(current_email, otp_code, "verify_current_email"):
        return jsonify({"success": False, "error": "Invalid or expired code"})
    auth_token = secrets.token_hex(24)
    sessions = load_json("sessions-data.json")
    sessions.setdefault("email_change_auths", {})[user["id"]] = {
        "token": auth_token,
        "expires": (datetime.now() + timedelta(minutes=15)).isoformat()
    }
    save_json("sessions-data.json", sessions)
    return jsonify({"success": True, "auth_token": auth_token})


@app.route("/api/account/remove-email", methods=["POST"])
def remove_email():
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Not logged in"})
    data = request.get_json(silent=True) or {}
    otp_code = data.get("otp_code", "").strip()
    current_email = user.get("email", "").strip().lower()
    if current_email:
        if not otp_code:
            return jsonify({"success": False, "error": "Verification code required"})
        if not verify_otp_code(current_email, otp_code, "remove_email"):
            return jsonify({"success": False, "error": "Invalid or expired code"})
    accounts = load_json("accounts-data.json")
    target = next((u for u in accounts["users"] if u["id"] == user["id"]), None)
    if not target:
        return jsonify({"success": False, "error": "User not found"})
    target["email"] = None
    target["email_verified"] = False
    save_json("accounts-data.json", accounts)
    return jsonify({"success": True})


@app.route("/api/account/confirm-change-email", methods=["POST"])
def confirm_change_email():
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Not logged in"})
    data = request.get_json(silent=True) or {}
    new_email = (data.get("email") or "").strip().lower()
    otp_code = data.get("otp_code", "").strip()
    auth_token = data.get("auth_token", "").strip()
    if not new_email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', new_email):
        return jsonify({"success": False, "error": "Invalid email address"})
    if user.get("email") and user.get("email_verified"):
        sessions = load_json("sessions-data.json")
        stored = sessions.get("email_change_auths", {}).get(user["id"])
        if not stored:
            return jsonify({"success": False, "error": "Current email not verified — please restart the flow"})
        if datetime.fromisoformat(stored["expires"]) < datetime.now():
            return jsonify({"success": False, "error": "Session expired — please restart the flow"})
        if stored["token"] != auth_token:
            return jsonify({"success": False, "error": "Invalid authorization token"})
        sessions["email_change_auths"].pop(user["id"], None)
        save_json("sessions-data.json", sessions)
    if not verify_otp_code(new_email, otp_code, "change_email"):
        return jsonify({"success": False, "error": "Invalid or expired code for new email"})
    accounts = load_json("accounts-data.json")
    if any((u.get("email") or "").lower() == new_email and u["id"] != user["id"] for u in accounts["users"]):
        return jsonify({"success": False, "error": "Email already used by another account"})
    target = next((u for u in accounts["users"] if u["id"] == user["id"]), None)
    if not target:
        return jsonify({"success": False, "error": "User not found"})
    target["email"] = new_email
    target["email_verified"] = True
    save_json("accounts-data.json", accounts)
    return jsonify({"success": True})


@app.route("/auth/discord")
def discord_login():
    action = request.args.get("action", "login")
    state_data = secrets.token_hex(16)
    sessions = load_json("sessions-data.json")
    sessions.setdefault("oauth_states", {})[state_data] = {
        "expires": (datetime.now() + timedelta(minutes=10)).isoformat(),
        "action": action
    }
    save_json("sessions-data.json", sessions)
    redirect_uri = DISCORD_REDIRECT_URI or (request.url_root.rstrip("/") + "/auth/discord/callback")
    params = urllib.parse.urlencode({
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify email guilds.join",
        "state": state_data,
        "prompt": "consent"
    })
    return redirect(f"https://discord.com/api/oauth2/authorize?{params}")


@app.route("/auth/discord/callback")
def discord_callback():
    code = request.args.get("code")
    state = request.args.get("state")
    if not code or not state:
        return redirect(url_for("login"))
    sessions = load_json("sessions-data.json")
    oauth_states = sessions.get("oauth_states", {})
    state_entry = oauth_states.pop(state, None)
    sessions["oauth_states"] = oauth_states
    save_json("sessions-data.json", sessions)
    if not state_entry:
        return redirect(url_for("login"))
    action = state_entry.get("action", "login")
    redirect_uri = DISCORD_REDIRECT_URI or (request.url_root.rstrip("/") + "/auth/discord/callback")
    token_resp = requests.post(
        "https://discord.com/api/oauth2/token",
        data={
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    if not token_resp.ok:
        return redirect(url_for("login"))
    access_token = token_resp.json().get("access_token")
    user_info_resp = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    if not user_info_resp.ok:
        return redirect(url_for("login"))
    dinfo = user_info_resp.json()
    discord_id = dinfo.get("id")
    d_username = dinfo.get("username", "")
    d_global_name = dinfo.get("global_name") or d_username
    d_avatar_hash = dinfo.get("avatar")
    d_avatar = f"https://cdn.discordapp.com/avatars/{discord_id}/{d_avatar_hash}.png" if d_avatar_hash else ""

    def try_join_guild(user_access_token, uid):
        if DISCORD_GUILD_ID and DISCORD_BOT_TOKEN:
            try:
                requests.put(
                    f"https://discord.com/api/guilds/{DISCORD_GUILD_ID}/members/{uid}",
                    headers={
                        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
                        "Content-Type": "application/json"
                    },
                    json={"access_token": user_access_token},
                    timeout=5
                )
            except Exception:
                pass

    try_join_guild(access_token, discord_id)
    accounts = load_json("accounts-data.json")
    if action == "link":
        current_user = get_session_user(request)
        if not current_user:
            return redirect(url_for("login"))
        if any(u.get("discord_id") == discord_id and u["id"] != current_user["id"] for u in accounts["users"]):
            return redirect("/dashboard?discord_error=already_linked")
        target = next((u for u in accounts["users"] if u["id"] == current_user["id"]), None)
        if target:
            target["discord_id"] = discord_id
            target["discord_username"] = d_username
            save_json("accounts-data.json", accounts)
        return redirect("/dashboard?discord_linked=1")
    found_user = next((u for u in accounts["users"] if u.get("discord_id") == discord_id), None)
    if not found_user:
        base_username = re.sub(r'[^a-zA-Z0-9_-]', '', d_username)[:20] or "user"
        username = base_username
        suffix = 1
        while any(u["username"].lower() == username.lower() for u in accounts["users"]):
            username = f"{base_username}{suffix}"
            suffix += 1
        new_id = str(uuid.uuid4())
        found_user = {
            "id": new_id,
            "username": username,
            "display_name": d_global_name or username,
            "email": None,
            "email_verified": False,
            "password": None,
            "discord_id": discord_id,
            "discord_username": d_username,
            "tag": "user",
            "avatar": d_avatar,
            "banner": "",
            "description": "Hello World!",
            "followers": [],
            "following": [],
            "created_at": datetime.now().isoformat(),
            "username_last_changed": None,
            "muted_until": None,
            "banned_until": None,
            "admin_until": None
        }
        accounts["users"].append(found_user)
        save_json("accounts-data.json", accounts)
    session_token, expires = create_session(found_user["id"])
    device_token = issue_device_token()
    resp = make_response(redirect(url_for("index")))
    resp.set_cookie("session_token", session_token, expires=expires, httponly=True, secure=True, samesite="Lax")
    resp.set_cookie("device_token", device_token, max_age=365 * 24 * 3600, httponly=True, secure=True, samesite="Lax")
    return resp


@app.route("/api/account/unlink-discord", methods=["POST"])
def unlink_discord():
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Not logged in"})
    accounts = load_json("accounts-data.json")
    target = next((u for u in accounts["users"] if u["id"] == user["id"]), None)
    if not target:
        return jsonify({"success": False, "error": "User not found"})
    if not target.get("password") and not target.get("google_id"):
        return jsonify({"success": False, "error": "Cannot disconnect Discord — you have no other login method"})
    target.pop("discord_id", None)
    target.pop("discord_username", None)
    save_json("accounts-data.json", accounts)
    return jsonify({"success": True})


@app.route("/upload")
def upload_redirect():
    user = get_session_user(request)
    if not user:
        return redirect(url_for("login", next=request.url))
    return redirect(url_for("user_upload", user_id=user["id"]))


@app.route("/users/<username>")
def user_profile(username):
    current_user = get_session_user(request)
    profile_user = get_user_by_username(username)
    if not profile_user:
        return redirect(f"/error?code=404&msg=Page+not+found")
    mods_data = load_json("mods-data.json")
    user_mods = [m for m in mods_data["mods"] if m.get("uploader_id") == profile_user["id"]]
    for m in user_mods:
        m["avg_rating"] = get_avg_rating(m)
    page = int(request.args.get("page", 1))
    total = len(user_mods)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))
    paginated_mods = user_mods[(page - 1) * PER_PAGE:page * PER_PAGE]
    is_own = current_user and current_user["id"] == profile_user["id"]
    is_following = current_user and current_user["id"] in profile_user.get("followers", [])
    return render_template("user_profile.html", user=current_user, profile=profile_user,
                           mods=paginated_mods, page=page, total_pages=total_pages,
                           total_mods=total, is_own=is_own, is_following=is_following,
                           is_admin_user=is_admin(profile_user))


@app.route("/api/follow/<user_id>", methods=["POST"])
def follow_user(user_id):
    current_user = get_session_user(request)
    if not current_user:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    if current_user["id"] == user_id:
        return jsonify({"success": False, "error": "Cannot follow yourself"}), 400
    accounts = load_json("accounts-data.json")
    target = next((u for u in accounts["users"] if u["id"] == user_id), None)
    if not target:
        return jsonify({"success": False, "error": "User not found"}), 404
    me = next((u for u in accounts["users"] if u["id"] == current_user["id"]), None)
    if not me:
        return jsonify({"success": False, "error": "Not found"}), 404
    if current_user["id"] in target.get("followers", []):
        target["followers"] = [f for f in target.get("followers", []) if f != current_user["id"]]
        me["following"] = [f for f in me.get("following", []) if f != user_id]
        save_json("accounts-data.json", accounts)
        return jsonify({"success": True, "following": False, "count": len(target["followers"])})
    target.setdefault("followers", []).append(current_user["id"])
    me.setdefault("following", []).append(user_id)
    save_json("accounts-data.json", accounts)
    return jsonify({"success": True, "following": True, "count": len(target["followers"])})


@app.route("/users/<user_id>/upload", methods=["GET", "POST"])
def user_upload(user_id):
    current_user = get_session_user(request)
    if not current_user:
        return redirect(url_for("login", next=request.url))
    if current_user["id"] != user_id and not is_admin(current_user):
        return redirect(f"/error?code=403&msg=Access+forbidden")
    if is_muted(current_user):
        return render_template("muted.html", user=current_user)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        download_link = request.form.get("download_link", "").strip()
        loaders = request.form.getlist("loaders")
        mc_versions = request.form.get("mc_versions", "").strip()
        editions = request.form.getlist("editions")
        images_urls = []
        for file in request.files.getlist("images"):
            if file and file.filename and allowed_file(file.filename):
                ext = file.filename.rsplit(".", 1)[1].lower()
                fname = f"{uuid.uuid4()}.{ext}"
                file.save(os.path.join(UPLOAD_DIR, "modbanner", fname))
                images_urls.append(f"/static/uploads/modbanner/{fname}")
        if not images_urls and "banner" in request.files:
            file = request.files["banner"]
            if file and file.filename and allowed_file(file.filename):
                ext = file.filename.rsplit(".", 1)[1].lower()
                fname = f"{uuid.uuid4()}.{ext}"
                file.save(os.path.join(UPLOAD_DIR, "modbanner", fname))
                images_urls = [f"/static/uploads/modbanner/{fname}"]
        banner_url = images_urls[0] if images_urls else ""
        mods_data = load_json("mods-data.json")
        tags_raw = request.form.get("tags", "")
        tags = list(dict.fromkeys([t.strip().lower() for t in tags_raw.split(",") if t.strip()]))[:10]
        upload_type = request.form.get("upload_type", "mod").strip().lower()
        if upload_type not in ("mod", "client"):
            upload_type = "mod"
        global_id = mods_data.get("next_id", len(mods_data["mods"]) + 1)
        new_mod = {
            "id": global_id,
            "name": name,
            "description": description,
            "banner": banner_url,
            "images": images_urls,
            "download_link": download_link,
            "uploader_id": current_user["id"],
            "uploader_username": current_user["username"],
            "loaders": loaders,
            "mc_versions": [v.strip() for v in mc_versions.split(",") if v.strip()],
            "editions": editions,
            "tags": tags,
            "type": upload_type,
            "downloads": 0,
            "views": 0,
            "ratings": [],
            "comments": [],
            "daily_stats": {},
            "created_at": datetime.now().isoformat()
        }
        if upload_type == "client":
            client_id = mods_data.get("next_client_id", 1)
            new_mod["client_id"] = client_id
            mods_data["next_client_id"] = client_id + 1
        mods_data["mods"].append(new_mod)
        mods_data["next_id"] = global_id + 1
        save_json("mods-data.json", mods_data)
        if new_mod.get("type") == "client":
            redir = url_for("client_info", mod_id=new_mod["client_id"])
        else:
            redir = url_for("mod_info", mod_id=new_mod["id"])
        return jsonify({"success": True, "redirect": redir})
    return render_template("upload.html", user=current_user, user_id=user_id)


@app.route("/users/<user_id>/manager-upload", methods=["GET"])
def manager_upload(user_id):
    current_user = get_session_user(request)
    if not current_user:
        return redirect(url_for("login", next=request.url))
    if current_user["id"] != user_id and not is_admin(current_user):
        return redirect(f"/error?code=403&msg=Access+forbidden")
    target_user = get_user_by_id(user_id)
    if not target_user:
        return redirect(f"/error?code=404&msg=Page+not+found")
    mods_data = load_json("mods-data.json")
    user_mods = [m for m in mods_data["mods"] if m.get("uploader_id") == user_id]
    for m in user_mods:
        m["avg_rating"] = get_avg_rating(m)
    page = int(request.args.get("page", 1))
    total = len(user_mods)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))
    paginated = user_mods[(page - 1) * PER_PAGE:page * PER_PAGE]
    return render_template("manager_upload.html", user=current_user, target_user=target_user,
                           mods=paginated, page=page, total_pages=total_pages)


@app.route("/users/<user_id>/manager-upload/edit/<int:mod_id>", methods=["POST"])
def edit_mod(user_id, mod_id):
    current_user = get_session_user(request)
    if not current_user:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    if current_user["id"] != user_id and not is_admin(current_user):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    mods_data = load_json("mods-data.json")
    mod = next((m for m in mods_data["mods"] if m["id"] == mod_id), None)
    if not mod:
        return jsonify({"success": False, "error": "Not found"}), 404
    mod["name"] = request.form.get("name", mod["name"]).strip()
    mod["description"] = request.form.get("description", mod["description"]).strip()
    mod["download_link"] = request.form.get("download_link", mod["download_link"]).strip()
    mod["loaders"] = request.form.getlist("loaders")
    mod["editions"] = request.form.getlist("editions")
    mc_versions = request.form.get("mc_versions", "")
    mod["mc_versions"] = [v.strip() for v in mc_versions.split(",") if v.strip()]
    if "banner" in request.files:
        file = request.files["banner"]
        if file and file.filename and allowed_file(file.filename):
            ext = file.filename.rsplit(".", 1)[1].lower()
            fname = f"{uuid.uuid4()}.{ext}"
            file.save(os.path.join(UPLOAD_DIR, "modbanner", fname))
            mod["banner"] = f"/static/uploads/modbanner/{fname}"
    save_json("mods-data.json", mods_data)
    return jsonify({"success": True})


@app.route("/users/<user_id>/manager-upload/delete/<int:mod_id>", methods=["POST"])
def delete_mod(user_id, mod_id):
    current_user = get_session_user(request)
    if not current_user:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    if current_user["id"] != user_id and not is_admin(current_user):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    mods_data = load_json("mods-data.json")
    mods_data["mods"] = [m for m in mods_data["mods"] if m["id"] != mod_id]
    save_json("mods-data.json", mods_data)
    return jsonify({"success": True})


@app.route("/users/<user_id>/edit", methods=["POST"])
def edit_profile(user_id):
    current_user = get_session_user(request)
    if not current_user:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    if current_user["id"] != user_id:
        return jsonify({"success": False, "error": "Forbidden"}), 403
    accounts = load_json("accounts-data.json")
    user = next((u for u in accounts["users"] if u["id"] == user_id), None)
    if not user:
        return jsonify({"success": False, "error": "Not found"}), 404
    display_name = request.form.get("display_name", "").strip()
    description = request.form.get("description", "").strip()
    new_username = request.form.get("username", "").strip()
    if display_name:
        user["display_name"] = display_name[:32]
    if description is not None:
        user["description"] = description[:500]
    if new_username and new_username.lower() != user["username"].lower():
        last_changed = user.get("username_last_changed")
        if last_changed:
            if (datetime.now() - datetime.fromisoformat(last_changed)).total_seconds() < 86400:
                return jsonify({"success": False, "error": "Username can only be changed once every 24 hours"}), 429
        if any(u["username"].lower() == new_username.lower() for u in accounts["users"] if u["id"] != user_id):
            return jsonify({"success": False, "error": "Username already taken"}), 409
        user["username"] = new_username
        user["username_last_changed"] = datetime.now().isoformat()
    if "avatar" in request.files:
        file = request.files["avatar"]
        if file and file.filename and allowed_file(file.filename):
            ext = file.filename.rsplit(".", 1)[1].lower()
            fname = f"avatar_{user_id}_{uuid.uuid4()}.{ext}"
            file.save(os.path.join(UPLOAD_DIR, "avatars", fname))
            user["avatar"] = f"/static/uploads/avatars/{fname}"
    if "banner" in request.files:
        file = request.files["banner"]
        if file and file.filename and allowed_file(file.filename):
            ext = file.filename.rsplit(".", 1)[1].lower()
            fname = f"banner_{user_id}_{uuid.uuid4()}.{ext}"
            file.save(os.path.join(UPLOAD_DIR, "banners", fname))
            user["banner"] = f"/static/uploads/banners/{fname}"
    hide_followers = request.form.get("hide_followers", "").strip()
    if hide_followers in ("1", "true", "on"):
        user["hide_followers"] = True
    else:
        user["hide_followers"] = False
    hide_following = request.form.get("hide_following", "").strip()
    if hide_following in ("1", "true", "on"):
        user["hide_following"] = True
    else:
        user["hide_following"] = False
    save_json("accounts-data.json", accounts)
    return jsonify({"success": True, "username": user["username"]})


@app.route("/clients")
def clients_page():
    user = get_session_user(request)
    mods_data = load_json("mods-data.json")
    clients = [m for m in mods_data["mods"] if m.get("type") == "client"]
    search = request.args.get("search", "").strip().lower()
    filter_by = request.args.get("filter", "newest")
    tag_filter = request.args.get("tag", "").strip().lower()
    uploader_filter = request.args.get("uploader", "").strip().lower()
    page = int(request.args.get("page", 1))
    if search:
        clients = [m for m in clients if search in m["name"].lower() or search in m.get("description", "").lower()]
    if tag_filter:
        clients = [m for m in clients if tag_filter in [t.lower() for t in m.get("tags", [])]]
    if uploader_filter:
        clients = [m for m in clients if uploader_filter in m.get("uploader_username", "").lower()]
    if filter_by == "most_download":
        clients = sorted(clients, key=lambda m: m.get("downloads", 0), reverse=True)
    elif filter_by == "most_popular":
        clients = sorted(clients, key=lambda m: m.get("views", 0), reverse=True)
    elif filter_by == "top_rated":
        clients = sorted(clients, key=lambda m: get_avg_rating(m), reverse=True)
    else:
        clients = sorted(clients, key=lambda m: m.get("created_at", ""), reverse=True)
    total = len(clients)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))
    paginated = clients[(page - 1) * PER_PAGE:page * PER_PAGE]
    all_clients = [m for m in mods_data["mods"] if m.get("type") == "client"]
    tag_counts = {}
    for m in all_clients:
        for t in m.get("tags", []):
            t = t.strip().lower()
            if t:
                tag_counts[t] = tag_counts.get(t, 0) + 1
    popular_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    for m in paginated:
        m["avg_rating"] = get_avg_rating(m)
        m.setdefault("tags", [])
    return render_template("clients.html", user=user, mods=paginated,
                           total=total, page=page, total_pages=total_pages,
                           search=search, filter_by=filter_by,
                           tag_filter=tag_filter, uploader_filter=uploader_filter,
                           popular_tags=popular_tags,
                           total_clients=len(all_clients))


@app.route("/clients/<int:mod_id>/info")
def client_info(mod_id):
    user = get_session_user(request)
    mods_data = load_json("mods-data.json")
    mod = next((m for m in mods_data["mods"] if m.get("type") == "client" and m.get("client_id", m["id"]) == mod_id), None)
    if not mod:
        mod = next((m for m in mods_data["mods"] if m["id"] == mod_id and m.get("type") == "client"), None)
    if not mod:
        return redirect(f"/error?code=404&msg=Page+not+found")
    mod["views"] = mod.get("views", 0) + 1
    track_daily(mod, "views")
    save_json("mods-data.json", mods_data)
    mod["avg_rating"] = get_avg_rating(mod)
    mod.setdefault("tags", [])
    mod.setdefault("comments", [])
    mod.setdefault("daily_stats", {})
    uploader = get_user_by_id(mod.get("uploader_id", ""))
    is_bookmarked = False
    if user:
        accounts_bm = load_json("accounts-data.json")
        bm_user = next((u for u in accounts_bm["users"] if u["id"] == user["id"]), None)
        if bm_user:
            is_bookmarked = mod["id"] in bm_user.get("bookmarks", [])
    user_rated = False
    user_rate_blocked = False
    if user:
        for r in mod.get("ratings", []):
            if r["user_id"] == user["id"]:
                if datetime.now() - datetime.fromisoformat(r["rated_at"]) < timedelta(hours=12):
                    user_rated = True
                    user_rate_blocked = True
    return render_template("mod_info.html", user=user, mod=mod, uploader=uploader,
                           hcaptcha_site_key=HCAPTCHA_SITE_KEY,
                           user_rated=user_rated, user_rate_blocked=user_rate_blocked,
                           is_bookmarked=is_bookmarked)


@app.route("/clients/<int:mod_id>/download")
def client_download(mod_id):
    return redirect(url_for("mod_download", mod_id=mod_id))


@app.route("/api/v1/auth/admin")
def admin_panel():
    current_user = get_session_user(request)
    if not current_user:
        return redirect(url_for("login", next=request.url))
    if not is_admin(current_user):
        return redirect(f"/error?code=403&msg=Access+forbidden")
    panel_type = request.args.get("type", "users")
    search_q = request.args.get("search", "").strip().lower()
    accounts = load_json("accounts-data.json")
    mods_data = load_json("mods-data.json")
    all_users = sorted(accounts["users"], key=lambda u: len(u.get("followers", [])), reverse=True)
    if search_q:
        all_users = [u for u in all_users if search_q in u.get("username", "").lower() or search_q in u.get("display_name", "").lower()]
    top_mods = sorted([m for m in mods_data["mods"] if m.get("type", "mod") == "mod"], key=lambda m: m.get("views", 0), reverse=True)[:20]
    top_clients = sorted([m for m in mods_data["mods"] if m.get("type") == "client"], key=lambda m: m.get("views", 0), reverse=True)[:20]
    for m in top_mods:
        m["avg_rating"] = get_avg_rating(m)
    for m in top_clients:
        m["avg_rating"] = get_avg_rating(m)
    return render_template("admin.html", user=current_user, panel_type=panel_type,
                           all_users=all_users, search_q=search_q,
                           top_mods=top_mods, top_clients=top_clients)


@app.route("/api/v1/auth/admin/mute", methods=["GET", "POST"])
def admin_mute_route():
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return redirect(f"/error?code=403&msg=Access+forbidden")
    if request.method == "POST":
        uid = request.form.get("user_id", "")
        hours = int(request.form.get("hours", 1))
        accounts = load_json("accounts-data.json")
        user = next((u for u in accounts["users"] if u["id"] == uid), None)
        if not user:
            return jsonify({"success": False}), 404
        user["muted_until"] = (datetime.now() + timedelta(hours=hours)).isoformat()
        save_json("accounts-data.json", accounts)
        if user.get("email"):
            _send_notify_bg(user["email"], "Your account has been muted — Lonely Hub",
                notify_email_html("muted", user.get("display_name") or user.get("username", "User"),
                    duration_text=f"{hours} hour{'s' if hours != 1 else ''}"))
        return redirect(url_for("admin_panel"))
    uid = request.args.get("user", "")
    target = get_user_by_id(uid)
    if not target:
        return redirect(f"/error?code=404&msg=Page+not+found")
    return render_template("admin_action.html", user=current_user, target=target, action="mute")


@app.route("/api/v1/auth/admin/ban", methods=["GET", "POST"])
def admin_ban_route():
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return redirect(f"/error?code=403&msg=Access+forbidden")
    if request.method == "POST":
        uid = request.form.get("user_id", "")
        hours = int(request.form.get("hours", 24))
        accounts = load_json("accounts-data.json")
        user = next((u for u in accounts["users"] if u["id"] == uid), None)
        if not user:
            return jsonify({"success": False}), 404
        user["banned_until"] = (datetime.now() + timedelta(hours=hours)).isoformat()
        save_json("accounts-data.json", accounts)
        if user.get("email"):
            _send_notify_bg(user["email"], "Your account has been banned — Lonely Hub",
                notify_email_html("banned", user.get("display_name") or user.get("username", "User"),
                    duration_text=f"{hours} hour{'s' if hours != 1 else ''}"))
        return redirect(url_for("admin_panel"))
    uid = request.args.get("user", "")
    target = get_user_by_id(uid)
    if not target:
        return redirect(f"/error?code=404&msg=Page+not+found")
    return render_template("admin_action.html", user=current_user, target=target, action="ban")


@app.route("/api/v1/auth/admin/perm", methods=["GET", "POST"])
def admin_perm_route():
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return redirect(f"/error?code=403&msg=Access+forbidden")
    if request.method == "POST":
        uid = request.form.get("user_id", "")
        lifetime = request.form.get("lifetime") == "on"
        hours = request.form.get("hours", "")
        accounts = load_json("accounts-data.json")
        user = next((u for u in accounts["users"] if u["id"] == uid), None)
        if not user:
            return jsonify({"success": False}), 404
        user["tag"] = "admin"
        if lifetime:
            user["admin_until"] = "lifetime"
        else:
            h = int(hours) if hours else 24
            user["admin_until"] = (datetime.now() + timedelta(hours=h)).isoformat()
        save_json("accounts-data.json", accounts)
        if user.get("email"):
            _send_notify_bg(user["email"], "You have been granted Admin access — Lonely Hub",
                notify_email_html("admin_granted", user.get("display_name") or user.get("username", "User")))
        return redirect(url_for("admin_panel"))
    uid = request.args.get("user", "")
    target = get_user_by_id(uid)
    if not target:
        return redirect(f"/error?code=404&msg=Page+not+found")
    return render_template("admin_action.html", user=current_user, target=target, action="perm")


@app.route("/api/v1/auth/admin/delete", methods=["GET", "POST"])
def admin_delete_route():
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return redirect(f"/error?code=403&msg=Access+forbidden")
    if request.method == "POST":
        uid = request.form.get("user_id", "")
        accounts = load_json("accounts-data.json")
        accounts["users"] = [u for u in accounts["users"] if u["id"] != uid]
        save_json("accounts-data.json", accounts)
        sessions = load_json("sessions-data.json")
        sessions["sessions"] = {t: s for t, s in sessions.get("sessions", {}).items() if s["user_id"] != uid}
        save_json("sessions-data.json", sessions)
        mods_data = load_json("mods-data.json")
        mods_data["mods"] = [m for m in mods_data["mods"] if m.get("uploader_id") != uid]
        save_json("mods-data.json", mods_data)
        return redirect(url_for("admin_panel"))
    uid = request.args.get("user", "")
    target = get_user_by_id(uid)
    if not target:
        return redirect(f"/error?code=404&msg=Page+not+found")
    return render_template("admin_action.html", user=current_user, target=target, action="delete")


@app.route("/api/v1/auth/admin/pages")
def admin_pages():
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return redirect(f"/error?code=403&msg=Access+forbidden")
    mods_data = load_json("mods-data.json")
    top_mods = sorted(mods_data["mods"], key=lambda m: m.get("views", 0), reverse=True)[:10]
    for m in top_mods:
        m["avg_rating"] = get_avg_rating(m)
    return render_template("admin_pages.html", user=current_user, top_mods=top_mods)


@app.route("/api/v1/auth/admin/pages/edit/<int:mod_id>", methods=["POST"])
def admin_edit_mod(mod_id):
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return jsonify({"success": False}), 403
    mods_data = load_json("mods-data.json")
    mod = next((m for m in mods_data["mods"] if m["id"] == mod_id), None)
    if not mod:
        return jsonify({"success": False}), 404
    mod["name"] = request.form.get("name", mod["name"]).strip()
    mod["description"] = request.form.get("description", mod["description"]).strip()
    mod["download_link"] = request.form.get("download_link", mod["download_link"]).strip()
    mod["loaders"] = request.form.getlist("loaders")
    mod["editions"] = request.form.getlist("editions")
    mc_versions = request.form.get("mc_versions", "")
    mod["mc_versions"] = [v.strip() for v in mc_versions.split(",") if v.strip()]
    save_json("mods-data.json", mods_data)
    return redirect(url_for("admin_pages"))


@app.route("/api/v1/auth/admin/pages/delete/<int:mod_id>", methods=["POST"])
def admin_delete_mod(mod_id):
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return jsonify({"success": False}), 403
    mods_data = load_json("mods-data.json")
    deleted_mod = next((m for m in mods_data["mods"] if m["id"] == mod_id), None)
    mods_data["mods"] = [m for m in mods_data["mods"] if m["id"] != mod_id]
    save_json("mods-data.json", mods_data)
    if deleted_mod:
        uploader_id = deleted_mod.get("uploader_id")
        if uploader_id and uploader_id != current_user["id"]:
            accounts = load_json("accounts-data.json")
            uploader = next((u for u in accounts["users"] if u["id"] == uploader_id), None)
            if uploader and uploader.get("email"):
                mod_type = deleted_mod.get("type", "mod")
                _send_notify_bg(uploader["email"],
                    f"Your {mod_type} was removed — Lonely Hub",
                    notify_email_html("mod_deleted",
                        uploader.get("display_name") or uploader.get("username", "User"),
                        mod_name=deleted_mod.get("name", "Unknown"),
                        mod_type=mod_type))
    return redirect(url_for("admin_pages"))




@app.route("/api/report", methods=["POST"])
def api_submit_report():
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Login required"}), 401
    report_type = request.form.get("type", "").strip()
    target_id = request.form.get("target_id", "").strip()
    target_url = request.form.get("target_url", "").strip()
    reason = request.form.get("reason", "").strip()
    description = request.form.get("description", "").strip()
    if not report_type or not target_id or not reason:
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    files = request.files.getlist("images")
    saved_images = []
    for f in files[:5]:
        if f and allowed_file(f.filename):
            fname = secrets.token_hex(16) + "." + f.filename.rsplit(".", 1)[1].lower()
            fpath = os.path.join(REPORT_UPLOAD_DIR, fname)
            f.save(fpath)
            saved_images.append("/static/report_uploads/" + fname)
    reports = load_json("reports-data.json")
    reports.setdefault("reports", []).append({
        "id": str(uuid.uuid4()),
        "type": report_type,
        "target_id": target_id,
        "target_url": target_url,
        "reporter_id": user["id"],
        "reporter_username": user["username"],
        "reason": reason,
        "description": description,
        "images": saved_images,
        "created_at": datetime.now().isoformat(),
        "status": "pending"
    })
    save_json("reports-data.json", reports)
    return jsonify({"success": True})


@app.route("/admin/reports")
def admin_reports():
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return redirect(f"/error?code=403&msg=Access+forbidden")
    reports_data = load_json("reports-data.json")
    accounts = load_json("accounts-data.json")
    users_map = {u["id"]: u for u in accounts.get("users", [])}
    reports = reports_data.get("reports", [])
    for r in reports:
        r["reporter"] = users_map.get(r.get("reporter_id"), {})
        if r.get("type") == "user":
            r["target_user"] = users_map.get(r.get("target_id"), {})
    status_filter = request.args.get("status", "all")
    if status_filter != "all":
        reports = [r for r in reports if r.get("status") == status_filter]
    reports = sorted(reports, key=lambda r: r.get("created_at", ""), reverse=True)
    return render_template("admin_reports.html", user=current_user, reports=reports, status_filter=status_filter)


@app.route("/api/admin/report/<report_id>/status", methods=["POST"])
def api_admin_report_status(report_id):
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    new_status = (request.get_json(silent=True) or {}).get("status", "")
    if new_status not in ("pending", "resolved", "dismissed"):
        return jsonify({"success": False, "error": "Invalid status"}), 400
    reports = load_json("reports-data.json")
    for r in reports.get("reports", []):
        if r["id"] == report_id:
            r["status"] = new_status
            save_json("reports-data.json", reports)
            return jsonify({"success": True})
    return jsonify({"success": False, "error": "Report not found"}), 404

@app.route("/api/stats")
def api_stats():
    return jsonify(get_site_stats())


@app.route("/api/tags")
def api_tags():
    mods_data = load_json("mods-data.json")
    tag_counts = {}
    for mod in mods_data["mods"]:
        for tag in mod.get("tags", []):
            t = tag.strip().lower()
            if t:
                tag_counts[t] = tag_counts.get(t, 0) + 1
    return jsonify(sorted(tag_counts.items(), key=lambda x: x[1], reverse=True))


@app.route("/api/comment/<int:mod_id>", methods=["POST"])
def add_comment(mod_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    if is_muted(user):
        return jsonify({"success": False, "error": "You are muted"}), 403
    ct = request.content_type or ""
    if "multipart" in ct or "form" in ct:
        text = request.form.get("text", "").strip()
        reply_to_id = request.form.get("reply_to_id", "")
        reply_to_name = request.form.get("reply_to_name", "")
        reply_to_content = request.form.get("reply_to_content", "").strip()[:200]
        reply_to_author = request.form.get("reply_to_author", "").strip()[:80]
        image_url = ""
        if "image" in request.files:
            file = request.files["image"]
            if file and file.filename and allowed_file(file.filename):
                ext = file.filename.rsplit(".", 1)[1].lower()
                fname = f"{uuid.uuid4()}.{ext}"
                file.save(os.path.join(UPLOAD_DIR, "modbanner", fname))
                image_url = f"/static/uploads/modbanner/{fname}"
    else:
        data = request.get_json(silent=True) or {}
        text = data.get("text", "").strip()
        reply_to_id = data.get("reply_to_id", "")
        reply_to_name = data.get("reply_to_name", "")
        reply_to_content = data.get("reply_to_content", "").strip()[:200]
        reply_to_author = data.get("reply_to_author", "").strip()[:80]
        image_url = ""
    if not text or len(text) > 1000:
        return jsonify({"success": False, "error": "Comment must be 1-1000 characters"}), 400
    mods_data = load_json("mods-data.json")
    mod = next((m for m in mods_data["mods"] if m["id"] == mod_id), None)
    if not mod:
        return jsonify({"success": False, "error": "Mod not found"}), 404
    comment = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "username": user["username"],
        "display_name": user.get("display_name", user["username"]),
        "avatar": user.get("avatar", ""),
        "text": text,
        "image": image_url,
        "reply_to_id": reply_to_id,
        "reply_to_name": reply_to_name,
        "reply_to_content": reply_to_content or None,
        "reply_to_author": reply_to_author or None,
        "reactions": {},
        "created_at": datetime.now().isoformat()
    }
    mod.setdefault("comments", []).append(comment)
    save_json("mods-data.json", mods_data)
    return jsonify({"success": True, "comment": comment})


@app.route("/api/react/<int:mod_id>/<comment_id>", methods=["POST"])
def react_comment(mod_id, comment_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    data = request.get_json(silent=True) or {}
    emoji = data.get("emoji", "")
    if not emoji or len(emoji) > 10:
        return jsonify({"success": False, "error": "Invalid emoji"}), 400
    mods_data = load_json("mods-data.json")
    mod = next((m for m in mods_data["mods"] if m["id"] == mod_id), None)
    if not mod:
        return jsonify({"success": False, "error": "Mod not found"}), 404
    comment = next((c for c in mod.get("comments", []) if c["id"] == comment_id), None)
    if not comment:
        return jsonify({"success": False, "error": "Comment not found"}), 404
    reactions = comment.setdefault("reactions", {})
    users = reactions.setdefault(emoji, [])
    if user["id"] in users:
        users.remove(user["id"])
        active = False
    else:
        users.append(user["id"])
        active = True
    save_json("mods-data.json", mods_data)
    return jsonify({"success": True, "active": active, "count": len(users)})


@app.route("/api/comment/<int:mod_id>/<comment_id>", methods=["DELETE"])
def delete_comment(mod_id, comment_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    mods_data = load_json("mods-data.json")
    mod = next((m for m in mods_data["mods"] if m["id"] == mod_id), None)
    if not mod:
        return jsonify({"success": False, "error": "Mod not found"}), 404
    comment = next((c for c in mod.get("comments", []) if c["id"] == comment_id), None)
    if not comment:
        return jsonify({"success": False, "error": "Comment not found"}), 404
    if comment["user_id"] != user["id"] and not is_admin(user):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    mod["comments"] = [c for c in mod["comments"] if c["id"] != comment_id]
    save_json("mods-data.json", mods_data)
    return jsonify({"success": True})


@app.route("/api/bookmark/<int:mod_id>", methods=["POST"])
def toggle_bookmark(mod_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    mods_data = load_json("mods-data.json")
    mod = next((m for m in mods_data["mods"] if m["id"] == mod_id), None)
    if not mod:
        return jsonify({"success": False, "error": "Mod not found"}), 404
    accounts = load_json("accounts-data.json")
    account = next((u for u in accounts["users"] if u["id"] == user["id"]), None)
    if not account:
        return jsonify({"success": False}), 404
    bookmarks = account.get("bookmarks", [])
    if mod_id in bookmarks:
        bookmarks.remove(mod_id)
        bookmarked = False
    else:
        bookmarks.append(mod_id)
        bookmarked = True
    account["bookmarks"] = bookmarks
    save_json("accounts-data.json", accounts)
    return jsonify({"success": True, "bookmarked": bookmarked})


@app.route("/dashboard")
def dashboard_redirect():
    user = get_session_user(request)
    if not user:
        return redirect(url_for("login", next="/dashboard"))
    return redirect(f"/users/{user['username']}/dashboard")


@app.route("/users/<username>/dashboard")
def user_dashboard(username):
    current_user = get_session_user(request)
    if not current_user:
        return redirect(url_for("login", next=request.url))
    profile_user = get_user_by_username(username)
    if not profile_user:
        return redirect(f"/error?code=404&msg=Page+not+found")
    if current_user["id"] != profile_user["id"] and not is_admin(current_user):
        return redirect(f"/error?code=403&msg=Access+forbidden")
    mods_data = load_json("mods-data.json")
    user_mods = [m for m in mods_data["mods"] if m.get("uploader_id") == profile_user["id"]]
    today = get_today_str()
    labels, chart_views, chart_downloads = get_chart_data(user_mods, 14)
    top_mods = sorted(user_mods, key=lambda m: m.get("views", 0), reverse=True)[:5]
    for m in top_mods:
        m["avg_rating"] = get_avg_rating(m)
    following_ids = profile_user.get("following", [])
    accounts = load_json("accounts-data.json")
    following_profiles = [u for u in accounts["users"] if u["id"] in following_ids][:12]
    bookmarked_ids = profile_user.get("bookmarks", [])
    bookmarked_mods = [m for m in mods_data["mods"] if m["id"] in bookmarked_ids][:6]
    for m in bookmarked_mods:
        m["avg_rating"] = get_avg_rating(m)
    return render_template("user_dashboard.html",
        user=current_user, profile=profile_user,
        total_views=sum(m.get("views", 0) for m in user_mods),
        total_downloads=sum(m.get("downloads", 0) for m in user_mods),
        total_mods=len(user_mods),
        views_today=sum(m.get("daily_stats", {}).get(today, {}).get("views", 0) for m in user_mods),
        downloads_today=sum(m.get("daily_stats", {}).get(today, {}).get("downloads", 0) for m in user_mods),
        chart_labels=labels, chart_views=chart_views, chart_downloads=chart_downloads,
        top_mods=top_mods,
        followers_count=len(profile_user.get("followers", [])),
        following_count=len(following_ids),
        following_profiles=following_profiles,
        bookmarked_mods=bookmarked_mods)


@app.route("/admin/dashboard")
def admin_dashboard():
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return redirect(f"/error?code=403&msg=Access+forbidden")
    accounts = load_json("accounts-data.json")
    mods_data = load_json("mods-data.json")
    sessions = load_json("sessions-data.json")
    settings = load_json("settings-data.json")
    today = get_today_str()
    labels, chart_views, chart_downloads = get_chart_data(mods_data["mods"], 14)
    top_mods = sorted(mods_data["mods"], key=lambda m: m.get("views", 0), reverse=True)[:8]
    for m in top_mods:
        m["avg_rating"] = get_avg_rating(m)
    tag_counts = {}
    for m in mods_data["mods"]:
        for tag in m.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    return render_template("admin_dashboard.html",
        user=current_user,
        total_users=len(accounts["users"]),
        total_mods=len(mods_data["mods"]),
        total_downloads=sum(m.get("downloads", 0) for m in mods_data["mods"]),
        total_views=sum(m.get("views", 0) for m in mods_data["mods"]),
        active_now=sum(
            1 for s in sessions.get("sessions", {}).values()
            if datetime.fromisoformat(s["expires"]) > datetime.now()
        ),
        views_today=sum(m.get("daily_stats", {}).get(today, {}).get("views", 0) for m in mods_data["mods"]),
        downloads_today=sum(m.get("daily_stats", {}).get(today, {}).get("downloads", 0) for m in mods_data["mods"]),
        chart_labels=labels, chart_views=chart_views, chart_downloads=chart_downloads,
        top_mods=top_mods,
        recent_users=sorted(accounts["users"], key=lambda u: u.get("created_at", ""), reverse=True)[:6],
        top_tags=sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10],
        trending=sorted(mods_data["mods"],
                        key=lambda m: m.get("daily_stats", {}).get(today, {}).get("views", 0),
                        reverse=True)[:5],
        api_rate_limit=settings.get("api_rate_limit", 60),
        today_str=today)


@app.route("/error")
def error_page():
    user = get_session_user(request)
    return render_template("error.html", user=user)


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Endpoint not found"}), 404
    return redirect(f"/error?code=404&msg=Page+not+found")


@app.errorhandler(403)
def forbidden(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Access forbidden"}), 403
    return redirect(f"/error?code=403&msg=Access+forbidden")


@app.errorhandler(500)
def internal_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Server error. Please try again."}), 500
    return redirect(f"/error?code=500&msg=Internal+server+error")


@app.errorhandler(Exception)
def handle_exception(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    print(f"[ERROR] Unhandled {request.method} {request.path}: {type(e).__name__}: {e}")
    print(traceback.format_exc())
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Server error. Please try again."}), 500
    raise e


def load_forum():
    return load_json("forum-data.json")


def save_forum(data):
    save_json("forum-data.json", data)


def anonymous_user():
    return {
        "id": None,
        "username": "anonymous",
        "display_name": "Anonymous",
        "avatar": ANONYMOUS_AVATAR,
        "tag": "user",
    }


def enrich_post(post):
    author = get_user_by_id(post.get("author_id", "")) if post.get("author_id") else None
    post["author"] = author if author else anonymous_user()
    post.setdefault("messages", [])
    post.setdefault("views", 0)
    post.setdefault("pinned", False)
    post.setdefault("locked", False)
    reply_count = 0
    for msg in post["messages"]:
        msg_author = get_user_by_id(msg.get("author_id", "")) if msg.get("author_id") else None
        msg["author"] = msg_author if msg_author else anonymous_user()
        msg.setdefault("attachments", [])
        msg.setdefault("replies", [])
        reply_count += 1
        for rep in msg["replies"]:
            rep_author = get_user_by_id(rep.get("author_id", "")) if rep.get("author_id") else None
            rep["author"] = rep_author if rep_author else anonymous_user()
            rep.setdefault("attachments", [])
            rep.setdefault("replies", [])
            reply_count += 1
            for srep in rep["replies"]:
                srep_author = get_user_by_id(srep.get("author_id", "")) if srep.get("author_id") else None
                srep["author"] = srep_author if srep_author else anonymous_user()
                srep.setdefault("attachments", [])
                reply_count += 1
    post["reply_count"] = reply_count
    return post


def save_forum_files(files_list):
    attachments = []
    for f in files_list:
        if not f or not f.filename:
            continue
        original_name = secure_filename(f.filename)
        if not original_name:
            continue
        ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else "bin"
        file_id = str(uuid.uuid4())
        stored_name = f"{file_id}.{ext}"
        dest = os.path.join(FORUM_UPLOAD_DIR, stored_name)
        f.seek(0, 2)
        size = f.tell()
        f.seek(0)
        if size > FORUM_MAX_FILE_SIZE:
            continue
        f.save(dest)
        mime = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
        is_image = mime.startswith("image/")
        attachments.append({
            "id": file_id,
            "original_name": original_name,
            "stored_name": stored_name,
            "size": size,
            "mime": mime,
            "is_image": is_image,
            "url": "/static/forum_uploads/" + stored_name,
        })
    return attachments


@app.route("/browse")
def browse_page():
    user = get_session_user(request)
    mods_data = load_json("mods-data.json")
    mod_count = len([m for m in mods_data["mods"] if m.get("type", "mod") != "client"])
    client_count = len([m for m in mods_data["mods"] if m.get("type") == "client"])
    return render_template("browse.html", user=user, mod_count=mod_count, client_count=client_count)


@app.route("/forum")
def forum_index():
    user = get_session_user(request)
    forum = load_forum()
    posts = list(forum["posts"])
    category = request.args.get("category", "").strip()
    sort = request.args.get("sort", "latest")
    search = request.args.get("search", "").strip().lower()
    page = max(1, int(request.args.get("page", 1)))

    if category:
        posts = [p for p in posts if p.get("category") == category]
    if search:
        posts = [p for p in posts if
                 search in p.get("title", "").lower() or
                 search in p.get("content", "").lower()]

    pinned = [p for p in posts if p.get("pinned")]
    normal = [p for p in posts if not p.get("pinned")]

    if sort == "most_replies":
        normal = sorted(normal, key=lambda p: len(p.get("messages", [])), reverse=True)
    elif sort == "most_views":
        normal = sorted(normal, key=lambda p: p.get("views", 0), reverse=True)
    else:
        normal = sorted(normal, key=lambda p: p.get("created_at", ""), reverse=True)

    all_posts = pinned + normal
    total = len(all_posts)
    total_pages = max(1, (total + FORUM_PER_PAGE - 1) // FORUM_PER_PAGE)
    page = min(page, total_pages)
    paginated = all_posts[(page - 1) * FORUM_PER_PAGE:page * FORUM_PER_PAGE]

    for p in paginated:
        enrich_post(p)
        cover = None
        for att in p.get("attachments", []):
            if att.get("is_image"):
                cover = att["url"]
                break
        if not cover:
            for msg in p.get("messages", []):
                for att in msg.get("attachments", []):
                    if att.get("is_image"):
                        cover = att["url"]
                        break
                if cover:
                    break
        p["cover_image"] = cover

    total_messages = sum(
        len(p.get("messages", [])) +
        sum(len(m.get("replies", [])) for m in p.get("messages", []))
        for p in forum["posts"]
    )

    return render_template(
        "forum.html",
        user=user,
        posts=paginated,
        categories=FORUM_CATEGORIES,
        category=category,
        sort=sort,
        search=search,
        page=page,
        total_pages=total_pages,
        total=total,
        total_posts=len(forum["posts"]),
        total_messages=total_messages,
    )


@app.route("/forum/new", methods=["GET", "POST"])
def forum_new_post():
    user = get_session_user(request)
    if not user:
        return redirect(url_for("login", next="/forum/new"))
    if is_muted(user):
        return render_template("muted.html", user=user)

    is_ajax = (request.headers.get("X-Requested-With") == "XMLHttpRequest"
               or "application/json" in request.headers.get("Accept", ""))
    error = None
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        category = request.form.get("category", "General Discussion").strip()
        if category not in FORUM_CATEGORIES:
            category = "General Discussion"
        files = request.files.getlist("files")
        if not title or len(title) < 3:
            error = "Title must be at least 3 characters."
        elif len(title) > 150:
            error = "Title is too long (max 150 characters)."
        elif not content or len(content) < 10:
            error = "Post content must be at least 10 characters."
        else:
            attachments = save_forum_files(files)
            post_id = str(uuid.uuid4())
            new_post = {
                "id": post_id,
                "title": title,
                "content": content,
                "category": category,
                "author_id": user["id"],
                "created_at": datetime.now().isoformat(),
                "pinned": False,
                "locked": False,
                "views": 0,
                "attachments": attachments,
                "messages": [],
            }
            forum = load_forum()
            forum["posts"].append(new_post)
            save_forum(forum)
            redir = url_for("forum_post", post_id=post_id)
            if is_ajax:
                return jsonify({"success": True, "redirect": redir})
            return redirect(redir)

        if is_ajax and error:
            return jsonify({"success": False, "error": error}), 400

    return render_template("forum_new.html", user=user, categories=FORUM_CATEGORIES, error=error)


@app.route("/forum/post/<post_id>")
def forum_post(post_id):
    user = get_session_user(request)
    forum = load_forum()
    post = next((p for p in forum["posts"] if p["id"] == post_id), None)
    if not post:
        return redirect(f"/error?code=404&msg=Page+not+found")
    post["views"] = post.get("views", 0) + 1
    save_forum(forum)
    enrich_post(post)
    return render_template("forum_post.html", user=user, post=post)


@app.route("/forum/post/<post_id>/message", methods=["POST"])
def forum_add_message(post_id):
    user = get_session_user(request)
    if user and is_muted(user):
        return jsonify({"success": False, "error": "You are muted"}), 403
    if not user:
        return jsonify({"success": False, "error": "Login required"}), 401
    forum = load_forum()
    post = next((p for p in forum["posts"] if p["id"] == post_id), None)
    if not post:
        return jsonify({"success": False, "error": "Post not found"}), 404
    if post.get("locked") and not is_admin(user):
        return jsonify({"success": False, "error": "Thread is locked"}), 403
    content = request.form.get("content", "").strip()
    files = request.files.getlist("files")
    if not content and not files:
        return jsonify({"success": False, "error": "Message cannot be empty"}), 400
    attachments = save_forum_files(files)
    msg_id = str(uuid.uuid4())
    reply_to = request.form.get("reply_to_msg_id", "").strip()
    post.setdefault("messages", []).append({
        "id": msg_id,
        "author_id": user["id"],
        "content": content,
        "created_at": datetime.now().isoformat(),
        "attachments": attachments,
        "replies": [],
        "reply_to_msg_id": reply_to if reply_to else None,
    })
    save_forum(forum)
    return jsonify({"success": True, "redirect": url_for("forum_post", post_id=post_id) + "#messages"})


@app.route("/forum/message/<post_id>/<msg_id>/reply", methods=["POST"])
def forum_add_reply(post_id, msg_id):
    user = get_session_user(request)
    if user and is_muted(user):
        return render_template("muted.html", user=user)
    forum = load_forum()
    post = next((p for p in forum["posts"] if p["id"] == post_id), None)
    if not post:
        return redirect(f"/error?code=404&msg=Page+not+found")
    if post.get("locked") and not (user and is_admin(user)):
        return redirect(url_for("forum_post", post_id=post_id))
    msg = next((m for m in post.get("messages", []) if m["id"] == msg_id), None)
    if not msg:
        return redirect(url_for("forum_post", post_id=post_id))
    content = request.form.get("content", "").strip()
    files = request.files.getlist("files")
    reply_to_content = request.form.get("reply_to_content", "").strip()[:200]
    reply_to_author = request.form.get("reply_to_author", "").strip()[:80]
    if content or files:
        attachments = save_forum_files(files)
        msg.setdefault("replies", []).append({
            "id": str(uuid.uuid4()),
            "author_id": user["id"] if user else None,
            "content": content,
            "created_at": datetime.now().isoformat(),
            "reply_to_id": msg_id,
            "reply_to_content": reply_to_content or None,
            "reply_to_author": reply_to_author or None,
            "attachments": attachments,
        })
        save_forum(forum)
    new_rep = msg["replies"][-1]
    redir = url_for("forum_post", post_id=post_id) + "#msg-" + msg_id
    return jsonify({
        "success": True,
        "redirect": redir,
        "reply": {
            "id": new_rep["id"],
            "msg_id": msg_id,
            "author_name": user.get("display_name", user.get("username", "Anonymous")),
            "author_avatar": user.get("avatar", ""),
            "author_id": user["id"],
            "content": new_rep.get("content", ""),
            "created_at": new_rep.get("created_at", ""),
            "reply_to_content": new_rep.get("reply_to_content"),
            "reply_to_author": new_rep.get("reply_to_author"),
        }
    })


@app.route("/forum/message/<post_id>/<msg_id>/reply/<rep_id>/subreply", methods=["POST"])
def forum_add_subreply(post_id, msg_id, rep_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Login required"}), 401
    if is_muted(user):
        return jsonify({"success": False, "error": "You are muted"}), 403
    forum = load_forum()
    post = next((p for p in forum["posts"] if p["id"] == post_id), None)
    if not post:
        return jsonify({"success": False, "error": "Post not found"}), 404
    if post.get("locked") and not is_admin(user):
        return jsonify({"success": False, "error": "Thread is locked"}), 403
    msg = next((m for m in post.get("messages", []) if m["id"] == msg_id), None)
    if not msg:
        return jsonify({"success": False, "error": "Message not found"}), 404
    rep = next((r for r in msg.get("replies", []) if r["id"] == rep_id), None)
    if not rep:
        return jsonify({"success": False, "error": "Reply not found"}), 404
    content = request.form.get("content", "").strip()
    files = request.files.getlist("files")
    reply_to_content = request.form.get("reply_to_content", "").strip()[:200]
    reply_to_author = request.form.get("reply_to_author", "").strip()[:80]
    if not content and not files:
        return jsonify({"success": False, "error": "Message cannot be empty"}), 400
    attachments = save_forum_files(files)
    rep.setdefault("replies", []).append({
        "id": str(uuid.uuid4()),
        "author_id": user["id"],
        "content": content,
        "created_at": datetime.now().isoformat(),
        "reply_to_content": reply_to_content or None,
        "reply_to_author": reply_to_author or None,
        "attachments": attachments,
    })
    save_forum(forum)
    new_srep = rep["replies"][-1]
    return jsonify({
        "success": True,
        "redirect": url_for("forum_post", post_id=post_id) + "#rep-" + rep_id,
        "subreply": {
            "id": new_srep["id"],
            "msg_id": msg_id,
            "rep_id": rep_id,
            "author_name": user.get("display_name", user.get("username", "Anonymous")),
            "author_avatar": user.get("avatar", ""),
            "author_id": user["id"],
            "content": new_srep.get("content", ""),
            "created_at": new_srep.get("created_at", ""),
            "reply_to_content": new_srep.get("reply_to_content"),
            "reply_to_author": new_srep.get("reply_to_author"),
        }
    })


@app.route("/forum/download/<file_id>")
def forum_download_warn(file_id):
    redirect_flag = request.args.get("redirect", "")
    forum = load_forum()
    att = None
    for p in forum["posts"]:
        for a in p.get("attachments", []):
            if a["id"] == file_id:
                att = a
                break
        if att:
            break
        for m in p.get("messages", []):
            for a in m.get("attachments", []):
                if a["id"] == file_id:
                    att = a
                    break
            if att:
                break
            for r in m.get("replies", []):
                for a in r.get("attachments", []):
                    if a["id"] == file_id:
                        att = a
                        break
                if att:
                    break
            if att:
                break
        if att:
            break

    if not att:
        user = get_session_user(request)
        return redirect(f"/error?code=404&msg=Page+not+found")

    if redirect_flag == "true":
        return send_from_directory(FORUM_UPLOAD_DIR, att["stored_name"],
                                   as_attachment=True, download_name=att["original_name"])

    user = get_session_user(request)
    return render_template("forum_download.html", user=user, att=att, file_id=file_id)


@app.route("/api/forum/react/<post_id>/<msg_id>/<rep_id>", methods=["POST"])
def forum_react_reply(post_id, msg_id, rep_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Login required"}), 401
    data = request.get_json(silent=True) or {}
    emoji = (data.get("emoji") or "").strip()
    if not emoji:
        return jsonify({"success": False, "error": "No emoji"}), 400
    forum = load_forum()
    post = next((p for p in forum["posts"] if p["id"] == post_id), None)
    if not post:
        return jsonify({"success": False, "error": "Post not found"}), 404
    msg = next((m for m in post.get("messages", []) if m["id"] == msg_id), None)
    if not msg:
        return jsonify({"success": False, "error": "Message not found"}), 404
    rep = next((r for r in msg.get("replies", []) if r["id"] == rep_id), None)
    if not rep:
        return jsonify({"success": False, "error": "Reply not found"}), 404
    reactions = rep.setdefault("reactions", {})
    react_users = reactions.setdefault(emoji, [])
    uid = user["id"]
    if uid in react_users:
        react_users.remove(uid)
        added = False
    else:
        react_users.append(uid)
        added = True
    if not react_users:
        del reactions[emoji]
    save_forum(forum)
    return jsonify({"success": True, "added": added, "count": len(react_users)})


@app.route("/api/forum/react/<post_id>/<msg_id>/<rep_id>/<srep_id>", methods=["POST"])
def forum_react_subreply(post_id, msg_id, rep_id, srep_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Login required"}), 401
    data = request.get_json(silent=True) or {}
    emoji = (data.get("emoji") or "").strip()
    if not emoji:
        return jsonify({"success": False, "error": "No emoji"}), 400
    forum = load_forum()
    post = next((p for p in forum["posts"] if p["id"] == post_id), None)
    if not post:
        return jsonify({"success": False, "error": "Post not found"}), 404
    msg = next((m for m in post.get("messages", []) if m["id"] == msg_id), None)
    if not msg:
        return jsonify({"success": False, "error": "Message not found"}), 404
    rep = next((r for r in msg.get("replies", []) if r["id"] == rep_id), None)
    if not rep:
        return jsonify({"success": False, "error": "Reply not found"}), 404
    srep = next((s for s in rep.get("replies", []) if s["id"] == srep_id), None)
    if not srep:
        return jsonify({"success": False, "error": "Sub-reply not found"}), 404
    reactions = srep.setdefault("reactions", {})
    react_users = reactions.setdefault(emoji, [])
    uid = user["id"]
    if uid in react_users:
        react_users.remove(uid)
        added = False
    else:
        react_users.append(uid)
        added = True
    if not react_users:
        del reactions[emoji]
    save_forum(forum)
    return jsonify({"success": True, "added": added, "count": len(react_users)})


@app.route("/api/forum/react/<post_id>/<msg_id>", methods=["POST"])
def forum_react(post_id, msg_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Login required"}), 401
    data = request.get_json(silent=True) or {}
    emoji = (data.get("emoji") or "").strip()
    if not emoji:
        return jsonify({"success": False, "error": "No emoji"}), 400
    forum = load_forum()
    post = next((p for p in forum["posts"] if p["id"] == post_id), None)
    if not post:
        return jsonify({"success": False, "error": "Post not found"}), 404
    msg = next((m for m in post.get("messages", []) if m["id"] == msg_id), None)
    if not msg:
        return jsonify({"success": False, "error": "Message not found"}), 404
    reactions = msg.setdefault("reactions", {})
    react_users = reactions.setdefault(emoji, [])
    uid = user["id"]
    if uid in react_users:
        react_users.remove(uid)
        added = False
    else:
        react_users.append(uid)
        added = True
    if not react_users:
        del reactions[emoji]
    save_forum(forum)
    return jsonify({"success": True, "added": added, "count": len(react_users)})


@app.route("/api/forum/post/<post_id>/pin", methods=["POST"])
def forum_pin_post(post_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Forbidden"}), 403
    forum = load_forum()
    post = next((p for p in forum["posts"] if p["id"] == post_id), None)
    if not post:
        return jsonify({"success": False, "error": "Not found"}), 404
    if not is_admin(user) and post.get("author_id") != user["id"]:
        return jsonify({"success": False, "error": "Forbidden"}), 403
    post["pinned"] = not post.get("pinned", False)
    save_forum(forum)
    return jsonify({"success": True, "pinned": post["pinned"]})


@app.route("/api/forum/post/<post_id>/lock", methods=["POST"])
def forum_lock_post(post_id):
    user = get_session_user(request)
    if not user or not is_admin(user):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    forum = load_forum()
    post = next((p for p in forum["posts"] if p["id"] == post_id), None)
    if not post:
        return jsonify({"success": False, "error": "Not found"}), 404
    post["locked"] = not post.get("locked", False)
    save_forum(forum)
    return jsonify({"success": True, "locked": post["locked"]})


@app.route("/api/forum/post/<post_id>/delete", methods=["POST"])
def forum_delete_post(post_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Forbidden"}), 403
    forum = load_forum()
    post = next((p for p in forum["posts"] if p["id"] == post_id), None)
    if not post:
        return jsonify({"success": False, "error": "Not found"}), 404
    if post.get("author_id") != user["id"] and not is_admin(user):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    forum["posts"] = [p for p in forum["posts"] if p["id"] != post_id]
    save_forum(forum)
    return jsonify({"success": True})


@app.route("/api/forum/message/<post_id>/<msg_id>/delete", methods=["POST"])
def forum_delete_message(post_id, msg_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Forbidden"}), 403
    forum = load_forum()
    post = next((p for p in forum["posts"] if p["id"] == post_id), None)
    if not post:
        return jsonify({"success": False, "error": "Not found"}), 404
    msg = next((m for m in post.get("messages", []) if m["id"] == msg_id), None)
    if not msg:
        return jsonify({"success": False, "error": "Not found"}), 404
    is_thread_owner = post.get("author_id") == user["id"]
    if msg.get("author_id") != user["id"] and not is_admin(user) and not is_thread_owner:
        return jsonify({"success": False, "error": "Forbidden"}), 403
    post["messages"] = [m for m in post["messages"] if m["id"] != msg_id]
    save_forum(forum)
    return jsonify({"success": True})


@app.route("/api/forum/reply/<post_id>/<msg_id>/<rep_id>/delete", methods=["POST"])
def forum_delete_reply(post_id, msg_id, rep_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Forbidden"}), 403
    forum = load_forum()
    post = next((p for p in forum["posts"] if p["id"] == post_id), None)
    if not post:
        return jsonify({"success": False, "error": "Not found"}), 404
    msg = next((m for m in post.get("messages", []) if m["id"] == msg_id), None)
    if not msg:
        return jsonify({"success": False, "error": "Not found"}), 404
    rep = next((r for r in msg.get("replies", []) if r["id"] == rep_id), None)
    if not rep:
        return jsonify({"success": False, "error": "Not found"}), 404
    post_author_id = post.get("author", {}).get("id") if isinstance(post.get("author"), dict) else post.get("author_id")
    if rep.get("author_id") != user["id"] and not is_admin(user) and user["id"] != post_author_id:
        return jsonify({"success": False, "error": "Forbidden"}), 403
    msg["replies"] = [r for r in msg.get("replies", []) if r["id"] != rep_id]
    save_forum(forum)
    return jsonify({"success": True})


@app.route("/api/forum/subreply/<post_id>/<msg_id>/<rep_id>/<srep_id>/delete", methods=["POST"])
def forum_delete_subreply(post_id, msg_id, rep_id, srep_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Forbidden"}), 403
    forum = load_forum()
    post = next((p for p in forum["posts"] if p["id"] == post_id), None)
    if not post:
        return jsonify({"success": False, "error": "Not found"}), 404
    msg = next((m for m in post.get("messages", []) if m["id"] == msg_id), None)
    if not msg:
        return jsonify({"success": False, "error": "Not found"}), 404
    rep = next((r for r in msg.get("replies", []) if r["id"] == rep_id), None)
    if not rep:
        return jsonify({"success": False, "error": "Not found"}), 404
    srep = next((s for s in rep.get("replies", []) if s["id"] == srep_id), None)
    if not srep:
        return jsonify({"success": False, "error": "Not found"}), 404
    post_author_id = post.get("author_id")
    if srep.get("author_id") != user["id"] and not is_admin(user) and user["id"] != post_author_id:
        return jsonify({"success": False, "error": "Forbidden"}), 403
    rep["replies"] = [s for s in rep.get("replies", []) if s["id"] != srep_id]
    save_forum(forum)
    return jsonify({"success": True})


@app.route("/api/change-password", methods=["POST"])
def change_password():
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    data = request.get_json(silent=True) or {}
    current_pw = data.get("current_password", "")
    new_pw = data.get("new_password", "")
    confirm_pw = data.get("confirm_password", "")
    otp_code = data.get("otp_code", "").strip()
    if user.get("password"):
        if not check_password_hash(user["password"], current_pw):
            return jsonify({"success": False, "error": "Current password is incorrect"}), 400
    if len(new_pw) < 6:
        return jsonify({"success": False, "error": "New password must be at least 6 characters"}), 400
    if new_pw != confirm_pw:
        return jsonify({"success": False, "error": "Passwords do not match"}), 400
    if user.get("email_verified"):
        email_for_otp = user.get("email", "").strip().lower()
        if not otp_code:
            return jsonify({"success": False, "error": "OTP verification required"}), 400
        if not verify_otp_code(email_for_otp, otp_code, "change_password"):
            return jsonify({"success": False, "error": "Invalid or expired verification code"}), 400
    accounts = load_json("accounts-data.json")
    acc = next((u for u in accounts.get("users", []) if u["id"] == user["id"]), None)
    if not acc:
        return jsonify({"success": False, "error": "User not found"}), 404
    acc["password"] = generate_password_hash(new_pw)
    save_json("accounts-data.json", accounts)
    return jsonify({"success": True})


@app.route("/users/<user_id>/followers")
def user_followers(user_id):
    try:
        current_user = get_session_user(request)
        accounts = load_json("accounts-data.json")
        target = next((u for u in accounts.get("users", []) if u["id"] == str(user_id)), None)
        if not target:
            return jsonify({"success": False, "error": "User not found"}), 404
        follower_ids = target.get("followers", [])
        result = []
        cu_id = current_user["id"] if current_user else None
        for fid in follower_ids:
            u = next((x for x in accounts["users"] if x["id"] == fid), None)
            if u:
                result.append({
                    "id": u["id"],
                    "username": u.get("username", ""),
                    "display_name": u.get("display_name", u.get("username", "")),
                    "avatar": u.get("avatar", ""),
                    "tag": u.get("tag", "user"),
                    "verified": bool(u.get("verified", False)),
                    "is_following": bool(cu_id and cu_id in u.get("followers", []))
                })
        return jsonify({"success": True, "users": result, "total": len(result)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/users/<user_id>/following")
def user_following(user_id):
    try:
        current_user = get_session_user(request)
        accounts = load_json("accounts-data.json")
        target = next((u for u in accounts.get("users", []) if u["id"] == str(user_id)), None)
        if not target:
            return jsonify({"success": False, "error": "User not found"}), 404
        following_ids = target.get("following", [])
        result = []
        cu_id = current_user["id"] if current_user else None
        for fid in following_ids:
            u = next((x for x in accounts["users"] if x["id"] == fid), None)
            if u:
                result.append({
                    "id": u["id"],
                    "username": u.get("username", ""),
                    "display_name": u.get("display_name", u.get("username", "")),
                    "avatar": u.get("avatar", ""),
                    "tag": u.get("tag", "user"),
                    "verified": bool(u.get("verified", False)),
                    "is_following": bool(cu_id and cu_id in u.get("followers", []))
                })
        return jsonify({"success": True, "users": result, "total": len(result)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/v1/auth/admin/verify", methods=["POST"])
def admin_verify_user():
    try:
        current_user = get_session_user(request)
        if not current_user or not is_admin(current_user):
            return jsonify({"success": False, "error": "Forbidden"}), 403
        uid = (request.form.get("user_id") or "").strip()
        if not uid:
            data = request.get_json(silent=True) or {}
            uid = str(data.get("user_id", "")).strip()
        if not uid:
            return jsonify({"success": False, "error": "user_id required"}), 400
        accounts = load_json("accounts-data.json")
        user = next((u for u in accounts.get("users", []) if str(u["id"]) == uid), None)
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404
        user["verified"] = not bool(user.get("verified", False))
        save_json("accounts-data.json", accounts)
        if user.get("email"):
            ntype = "verified_granted" if user["verified"] else "verified_removed"
            subj = ("You've been verified on Lonely Hub" if user["verified"] else "Verified badge removed — Lonely Hub")
            _send_notify_bg(user["email"], subj,
                notify_email_html(ntype, user.get("display_name") or user.get("username", "User")))
        return jsonify({"success": True, "verified": user["verified"]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/forum/post/<post_id>/messages", methods=["GET"])
def api_forum_messages(post_id):
    forum = load_forum()
    post = next((p for p in forum["posts"] if p["id"] == post_id), None)
    if not post:
        return jsonify({"success": False, "error": "Not found"}), 404
    enrich_post(post)
    since = request.args.get("since", "")
    msgs = post.get("messages", [])
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            msgs = [m for m in msgs if datetime.fromisoformat(m["created_at"]) > since_dt]
        except Exception:
            pass
    def msg_to_dict(m):
        return {
            "id": m["id"],
            "author_id": m.get("author_id"),
            "author_name": m.get("author", {}).get("display_name", "Anonymous") if m.get("author") else "Anonymous",
            "author_avatar": m.get("author", {}).get("avatar", "") if m.get("author") else "",
            "author_tag": m.get("author", {}).get("tag", "user") if m.get("author") else "user",
            "content": m.get("content", ""),
            "created_at": m.get("created_at", ""),
            "reply_count": len(m.get("replies", [])),
        }
    return jsonify({"success": True, "messages": [msg_to_dict(m) for m in msgs], "total": len(post.get("messages", []))})


_typing_state = {}

@app.route("/api/forum/post/<post_id>/typing", methods=["POST"])
def api_forum_post_typing_post(post_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False}), 401
    if post_id not in _typing_state:
        _typing_state[post_id] = {}
    _typing_state[post_id][user["id"]] = {
        "name": user.get("display_name") or user.get("username", "Anonymous"),
        "ts": time.time(),
    }
    return jsonify({"success": True})

@app.route("/api/forum/post/<post_id>/typing", methods=["GET"])
def api_forum_post_typing_get(post_id):
    user = get_session_user(request)
    uid = user["id"] if user else None
    now = time.time()
    state = _typing_state.get(post_id, {})
    stale = [k for k, v in state.items() if now - v["ts"] >= 5]
    for k in stale:
        del state[k]
    typers = [v["name"] for k, v in state.items() if k != uid]
    return jsonify({"success": True, "typers": typers})

@app.route("/api/forum/post/<post_id>/state", methods=["GET"])
def api_forum_post_state(post_id):
    forum = load_forum()
    post = next((p for p in forum["posts"] if p["id"] == post_id), None)
    if not post:
        return jsonify({"success": False, "error": "Not found"}), 404
    enrich_post(post)
    user = get_session_user(request)
    uid = user["id"] if user else None
    def rto(reactions, uid):
        out = {}
        for em, ulist in (reactions or {}).items():
            if ulist:
                out[em] = {"count": len(ulist), "active": bool(uid and uid in ulist)}
        return out
    msgs_out = []
    for msg in post.get("messages", []):
        reps_out = []
        for rep in msg.get("replies", []):
            sreps_out = []
            for srep in rep.get("replies", []):
                sreps_out.append({
                    "id": srep["id"],
                    "msg_id": msg["id"],
                    "rep_id": rep["id"],
                    "author_name": (srep.get("author") or {}).get("display_name", "Anonymous"),
                    "author_avatar": (srep.get("author") or {}).get("avatar", ""),
                    "author_id": srep.get("author_id"),
                    "content": srep.get("content", ""),
                    "created_at": srep.get("created_at", ""),
                    "reply_to_content": srep.get("reply_to_content"),
                    "reply_to_author": srep.get("reply_to_author"),
                    "reactions": rto(srep.get("reactions"), uid),
                })
            reps_out.append({
                "id": rep["id"],
                "msg_id": msg["id"],
                "author_name": (rep.get("author") or {}).get("display_name", "Anonymous"),
                "author_avatar": (rep.get("author") or {}).get("avatar", ""),
                "author_id": rep.get("author_id"),
                "content": rep.get("content", ""),
                "created_at": rep.get("created_at", ""),
                "reply_to_content": rep.get("reply_to_content"),
                "reply_to_author": rep.get("reply_to_author"),
                "reactions": rto(rep.get("reactions"), uid),
                "subreplies": sreps_out,
            })
        msgs_out.append({
            "id": msg["id"],
            "reactions": rto(msg.get("reactions"), uid),
            "replies": reps_out,
        })
    return jsonify({"success": True, "messages": msgs_out})


@app.route("/api/mods/<int:mod_id>/comments-state", methods=["GET"])
def api_mod_comments_state(mod_id):
    user = get_session_user(request)
    uid = user["id"] if user else None
    mods_data = load_json("mods-data.json")
    mod = next((m for m in mods_data["mods"] if m["id"] == mod_id), None)
    if not mod:
        return jsonify({"success": False, "error": "Not found"}), 404
    comments_out = []
    for c in mod.get("comments", []):
        reactions = {}
        for em, ulist in (c.get("reactions") or {}).items():
            if ulist:
                reactions[em] = {"count": len(ulist), "active": bool(uid and uid in ulist)}
        comments_out.append({
            "id": c["id"],
            "user_id": c.get("user_id"),
            "display_name": c.get("display_name", "Anonymous"),
            "avatar": c.get("avatar", ""),
            "username": c.get("username", ""),
            "text": c.get("text", ""),
            "created_at": c.get("created_at", ""),
            "reply_to_id": c.get("reply_to_id", ""),
            "reply_to_name": c.get("reply_to_name", ""),
            "reply_to_content": c.get("reply_to_content", ""),
            "reactions": reactions,
        })
    return jsonify({"success": True, "comments": comments_out})


def get_api_rate_limit():
    settings = load_json("settings-data.json")
    return int(settings.get("api_rate_limit", 60))


def check_api_rate_limit(token):
    if not token:
        return None
    limit = get_api_rate_limit()
    now = datetime.now()
    window_start = now - timedelta(seconds=60)
    timestamps = _rate_limit_store.get(token, [])
    timestamps = [t for t in timestamps if t > window_start]
    if len(timestamps) >= limit:
        _rate_limit_store[token] = timestamps
        return jsonify({"success": False, "error": "Rate limit exceeded", "retry_after": 60}), 429
    timestamps.append(now)
    _rate_limit_store[token] = timestamps
    return None

def _get_api_user(token_header):
    token = (token_header or "").strip()
    if not token:
        return None
    accounts = load_json("accounts-data.json")
    user = next((u for u in accounts.get("users", []) if (u.get("api_token") or "").strip() == token), None)
    return user


@app.route("/api/v2/token", methods=["GET", "POST"])
def api_v2_token():
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    accounts = load_json("accounts-data.json")
    acc = next((u for u in accounts["users"] if u["id"] == user["id"]), None)
    if not acc:
        return jsonify({"success": False, "error": "User not found"}), 404
    if not acc.get("api_token"):
        acc["api_token"] = secrets.token_hex(32)
        save_json("accounts-data.json", accounts)
    return jsonify({"success": True, "token": acc["api_token"]})


@app.route("/api/v2/token/regenerate", methods=["POST"])
def api_v2_token_regen():
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    accounts = load_json("accounts-data.json")
    acc = next((u for u in accounts["users"] if u["id"] == user["id"]), None)
    if not acc:
        return jsonify({"success": False, "error": "User not found"}), 404
    acc["api_token"] = secrets.token_hex(32)
    save_json("accounts-data.json", accounts)
    return jsonify({"success": True, "token": acc["api_token"]})


@app.route("/api/v2/upload", methods=["POST"])
def api_v2_upload():
    try:
        token = request.headers.get("X-Token", "").strip()
        uploader = _get_api_user(token)
        if not uploader:
            return jsonify({"success": False, "error": "Invalid or missing token"}), 401
        rl = check_api_rate_limit(token)
        if rl:
            return rl
        upload_type = request.headers.get("X-Type", "").strip().lower()
        if upload_type == "mods":
            upload_type = "mod"
        elif upload_type == "clients":
            upload_type = "client"
        else:
            return jsonify({"success": False, "error": "X-Type must be Mods or Clients"}), 400
        name = request.headers.get("X-Name", "").strip()
        description = request.headers.get("X-Description", "").strip()
        mc_version = request.headers.get("X-MCVersion", "").strip()
        version_raw = request.headers.get("X-Version", "").strip()
        tags_raw = request.headers.get("X-Tag", "").strip()
        download_link = request.headers.get("X-DownloadLink", "").strip()
        images_raw = request.headers.get("X-Image", "").strip()
        loaders_raw = request.headers.get("X-Loaders", "").strip()
        if not name:
            return jsonify({"success": False, "error": "X-Name is required"}), 400
        tags = [t.strip() for t in tags_raw.replace(", ", ",").split(",") if t.strip()][:10]
        images = [i.strip() for i in images_raw.replace(", ", ",").split(",") if i.strip()]
        mc_versions = [v.strip() for v in version_raw.replace(", ", ",").split(",") if v.strip()]
        loaders = [l.strip() for l in loaders_raw.replace(", ", ",").split(",") if l.strip()] if upload_type == "mod" else []
        editions = [mc_version] if mc_version in ("Bedrock", "Java", "All") else []
        mods_data = load_json("mods-data.json")
        global_id = mods_data.get("next_id", len(mods_data["mods"]) + 1)
        new_mod = {
            "id": global_id,
            "name": name,
            "description": description,
            "banner": images[0] if images else "",
            "images": images,
            "download_link": download_link,
            "uploader_id": uploader["id"],
            "uploader_username": uploader["username"],
            "loaders": loaders,
            "mc_versions": mc_versions,
            "editions": editions,
            "tags": tags,
            "type": upload_type,
            "downloads": 0,
            "views": 0,
            "ratings": [],
            "comments": [],
            "daily_stats": {},
            "created_at": datetime.now().isoformat()
        }
        if upload_type == "client":
            client_id = mods_data.get("next_client_id", 1)
            new_mod["client_id"] = client_id
            mods_data["next_client_id"] = client_id + 1
        mods_data["mods"].append(new_mod)
        mods_data["next_id"] = global_id + 1
        save_json("mods-data.json", mods_data)
        display_id = new_mod.get("client_id", global_id) if upload_type == "client" else global_id
        url = f"/clients/{display_id}/info" if upload_type == "client" else f"/mods/{global_id}/info"
        return jsonify({"success": True, "id": display_id, "url": url, "name": name, "type": upload_type})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/v2/edit", methods=["POST"])
def api_v2_edit():
    try:
        token = request.headers.get("X-Token", "").strip()
        editor = _get_api_user(token)
        if not editor:
            return jsonify({"success": False, "error": "Invalid or missing token"}), 401
        rl = check_api_rate_limit(token)
        if rl:
            return rl
        product_type = request.headers.get("X-Type", "").strip().lower()
        if product_type == "mods":
            product_type = "mod"
        elif product_type == "clients":
            product_type = "client"
        raw_id = request.headers.get("X-IdProduct", "").strip()
        if not raw_id:
            return jsonify({"success": False, "error": "X-IdProduct is required"}), 400
        try:
            product_id = int(raw_id)
        except ValueError:
            return jsonify({"success": False, "error": "X-IdProduct must be a number"}), 400
        mods_data = load_json("mods-data.json")
        if product_type == "client":
            mod = next((m for m in mods_data["mods"] if m.get("type") == "client" and m.get("client_id", m["id"]) == product_id), None)
        else:
            mod = next((m for m in mods_data["mods"] if m["id"] == product_id and m.get("type", "mod") == "mod"), None)
        if not mod:
            return jsonify({"success": False, "error": "Product not found"}), 404
        if mod["uploader_id"] != editor["id"] and not is_admin(editor):
            return jsonify({"success": False, "error": "Forbidden"}), 403
        name = request.headers.get("X-Name", "").strip()
        description = request.headers.get("X-Description", "").strip()
        mc_version = request.headers.get("X-MCVersion", "").strip()
        version_raw = request.headers.get("X-Version", "").strip()
        tags_raw = request.headers.get("X-Tag", "").strip()
        download_link = request.headers.get("X-DownloadLink", "").strip()
        images_raw = request.headers.get("X-Image", "").strip()
        loaders_raw = request.headers.get("X-Loaders", "").strip()
        if name:
            mod["name"] = name
        if description:
            mod["description"] = description
        if download_link:
            mod["download_link"] = download_link
        if tags_raw:
            mod["tags"] = [t.strip() for t in tags_raw.replace(", ", ",").split(",") if t.strip()][:10]
        if images_raw:
            imgs = [i.strip() for i in images_raw.replace(", ", ",").split(",") if i.strip()]
            mod["images"] = imgs
            mod["banner"] = imgs[0] if imgs else mod.get("banner", "")
        if version_raw:
            mod["mc_versions"] = [v.strip() for v in version_raw.replace(", ", ",").split(",") if v.strip()]
        if mc_version in ("Bedrock", "Java", "All"):
            mod["editions"] = [mc_version]
        if loaders_raw and mod.get("type") == "mod":
            mod["loaders"] = [l.strip() for l in loaders_raw.replace(", ", ",").split(",") if l.strip()]
        save_json("mods-data.json", mods_data)
        return jsonify({"success": True, "id": product_id, "name": mod["name"]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/v2/delete", methods=["POST"])
def api_v2_delete():
    try:
        token = request.headers.get("X-Token", "").strip()
        deleter = _get_api_user(token)
        if not deleter:
            return jsonify({"success": False, "error": "Invalid or missing token"}), 401
        rl = check_api_rate_limit(token)
        if rl:
            return rl
        product_type = request.headers.get("X-Type", "").strip().lower()
        if product_type == "mods":
            product_type = "mod"
        elif product_type == "clients":
            product_type = "client"
        raw_id = request.headers.get("X-PostId", "").strip()
        if not raw_id:
            return jsonify({"success": False, "error": "X-PostId is required"}), 400
        try:
            product_id = int(raw_id)
        except ValueError:
            return jsonify({"success": False, "error": "X-PostId must be a number"}), 400
        mods_data = load_json("mods-data.json")
        if product_type == "client":
            mod = next((m for m in mods_data["mods"] if m.get("type") == "client" and m.get("client_id", m["id"]) == product_id), None)
        else:
            mod = next((m for m in mods_data["mods"] if m["id"] == product_id), None)
        if not mod:
            return jsonify({"success": False, "error": "Product not found"}), 404
        if mod["uploader_id"] != deleter["id"] and not is_admin(deleter):
            return jsonify({"success": False, "error": "Forbidden"}), 403
        mods_data["mods"] = [m for m in mods_data["mods"] if m["id"] != mod["id"]]
        save_json("mods-data.json", mods_data)
        return jsonify({"success": True, "deleted": product_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/v2/dashboard-data", methods=["GET"])
def api_v2_dashboard_data():
    try:
        token = request.headers.get("X-Token", request.args.get("token", "")).strip()
        accounts = load_json("accounts-data.json")
        user = next((u for u in accounts.get("users", []) if (u.get("api_token") or "").strip() == token), None)
        if not user:
            return jsonify({"success": False, "error": "Invalid token"}), 401
        rl = check_api_rate_limit(token)
        if rl:
            return rl
        mods_data = load_json("mods-data.json")
        user_mods = [m for m in mods_data["mods"] if m.get("uploader_id") == user["id"]]
        today = get_today_str()
        total_views = sum(m.get("views", 0) for m in user_mods)
        total_downloads = sum(m.get("downloads", 0) for m in user_mods)
        views_today = sum(m.get("daily_stats", {}).get(today, {}).get("views", 0) for m in user_mods)
        downloads_today = sum(m.get("daily_stats", {}).get(today, {}).get("downloads", 0) for m in user_mods)
        top_mods = sorted(user_mods, key=lambda m: m.get("views") or 0, reverse=True)[:5]
        hide_follow = request.headers.get("X-HideFollow", "").strip().lower() in ("true", "1")
        followers_count = len(user.get("followers", []))
        following_count = len(user.get("following", []))
        resp = {
            "success": True,
            "username": user.get("username"),
            "display_name": user.get("display_name", user.get("username")),
            "TotalViews": total_views,
            "TotalDownloads": total_downloads,
            "ViewsToday": views_today,
            "DownloadsToday": downloads_today,
            "TotalMods": len(user_mods),
            "Followers": followers_count,
            "Following": following_count,
            "TopMods": [{"id": m["id"], "name": m.get("name", ""), "views": m.get("views", 0), "downloads": m.get("downloads", 0)} for m in top_mods],
        }
        if not hide_follow:
            follower_ids = user.get("followers", [])
            following_ids = user.get("following", [])
            resp["FollowersList"] = [u2.get("username") for u2 in accounts["users"] if u2["id"] in follower_ids]
            resp["FollowingList"] = [u2.get("username") for u2 in accounts["users"] if u2["id"] in following_ids]
        return jsonify(resp)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/v2/profile-edit", methods=["POST"])
def api_v2_profile_edit():
    try:
        token = request.headers.get("X-Token", request.form.get("token", "")).strip()
        accounts = load_json("accounts-data.json")
        user = next((u for u in accounts.get("users", []) if u.get("api_token") == token), None)
        if not user:
            return jsonify({"success": False, "error": "Invalid token"}), 401
        rl = check_api_rate_limit(token)
        if rl:
            return rl
        data = request.get_json(silent=True) or {}
        def g(k): return (data.get(k) or request.form.get(k) or request.headers.get("X-" + k, "")).strip()
        new_pw = g("password") or g("Password")
        new_username = g("username") or g("Username")
        new_display = g("display_name") or g("DisplayName")
        new_avatar = g("avatar") or g("Avatar")
        new_banner = g("banner") or g("Banner")
        hide_follow_raw = request.headers.get("X-HideFollow", "").strip().lower()
        if new_pw:
            if len(new_pw) < 6:
                return jsonify({"success": False, "error": "Password must be at least 6 characters"}), 400
            user["password"] = generate_password_hash(new_pw)
        if new_username and new_username.lower() != user["username"].lower():
            last_changed = user.get("username_last_changed")
            if last_changed:
                if (datetime.now() - datetime.fromisoformat(last_changed)).total_seconds() < 86400:
                    return jsonify({"success": False, "error": "Username can only be changed once every 24 hours"}), 429
            if any(u2["username"].lower() == new_username.lower() for u2 in accounts["users"] if u2["id"] != user["id"]):
                return jsonify({"success": False, "error": "Username already taken"}), 409
            user["username"] = new_username
            user["username_last_changed"] = datetime.now().isoformat()
        if new_display:
            user["display_name"] = new_display[:32]
        if new_avatar:
            user["avatar"] = new_avatar
        if new_banner:
            user["banner"] = new_banner
        if hide_follow_raw in ("true", "1"):
            user["hide_followers"] = True
            user["hide_following"] = True
        elif hide_follow_raw in ("false", "0"):
            user["hide_followers"] = False
            user["hide_following"] = False
        save_json("accounts-data.json", accounts)
        return jsonify({"success": True, "username": user["username"], "display_name": user.get("display_name")})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/v3/edit", methods=["POST"])
def api_v3_edit():
    try:
        token = request.headers.get("X-Token", "").strip()
        admin_user = _get_api_user(token)
        if not admin_user or not is_admin(admin_user):
            return jsonify({"success": False, "error": "Admin token required"}), 403
        rl = check_api_rate_limit(token)
        if rl:
            return rl
        product_type = request.headers.get("X-Type", "").strip().lower()
        if product_type in ("mods",):
            product_type = "mod"
        elif product_type in ("clients",):
            product_type = "client"
        raw_id = request.headers.get("X-PostId", "").strip()
        if not raw_id:
            return jsonify({"success": False, "error": "X-PostId required"}), 400
        product_id = int(raw_id)
        mods_data = load_json("mods-data.json")
        if product_type == "client":
            mod = next((m for m in mods_data["mods"] if m.get("type") == "client" and m.get("client_id", m["id"]) == product_id), None)
        else:
            mod = next((m for m in mods_data["mods"] if m["id"] == product_id), None)
        if not mod:
            return jsonify({"success": False, "error": "Product not found"}), 404
        for field, key in [("X-Name", "name"), ("X-Description", "description"), ("X-DownloadLink", "download_link")]:
            val = request.headers.get(field, "").strip()
            if val:
                mod[key] = val
        tags_raw = request.headers.get("X-Tag", "").strip()
        if tags_raw:
            mod["tags"] = [t.strip() for t in tags_raw.replace(", ", ",").split(",") if t.strip()][:10]
        images_raw = request.headers.get("X-Image", "").strip()
        if images_raw:
            imgs = [i.strip() for i in images_raw.replace(", ", ",").split(",") if i.strip()]
            mod["images"] = imgs
            mod["banner"] = imgs[0] if imgs else mod.get("banner", "")
        save_json("mods-data.json", mods_data)
        return jsonify({"success": True, "id": product_id, "name": mod.get("name")})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/v3/user", methods=["POST"])
def api_v3_user():
    try:
        token = request.headers.get("X-Token", "").strip()
        admin_user = _get_api_user(token)
        if not admin_user or not is_admin(admin_user):
            return jsonify({"success": False, "error": "Admin token required"}), 403
        rl = check_api_rate_limit(token)
        if rl:
            return rl
        data = request.get_json(silent=True) or {}
        def gh(k): return request.headers.get(k, data.get(k.lower().replace("-", "_"), "")).strip()
        target_id = gh("X-UserId")
        action = gh("X-Action")
        accounts = load_json("accounts-data.json")
        target = next((u for u in accounts["users"] if str(u["id"]) == str(target_id)), None)
        if not target:
            return jsonify({"success": False, "error": "User not found"}), 404
        result = {}
        _tname = target.get("display_name") or target.get("username", "User")
        _temail = target.get("email", "")
        if action == "verify":
            target["verified"] = not bool(target.get("verified", False))
            result["verified"] = target["verified"]
            if _temail:
                ntype = "verified_granted" if target["verified"] else "verified_removed"
                subj = ("You've been verified on Lonely Hub" if target["verified"] else "Verified badge removed — Lonely Hub")
                _send_notify_bg(_temail, subj, notify_email_html(ntype, _tname))
        elif action == "ban":
            target["banned"] = not bool(target.get("banned", False))
            result["banned"] = target["banned"]
            if _temail and target["banned"]:
                _send_notify_bg(_temail, "Your account has been banned — Lonely Hub",
                    notify_email_html("banned", _tname, duration_text="Permanent"))
        elif action == "mute":
            hours = int(gh("X-Hours") or data.get("hours", 24) or 24)
            target["muted_until"] = (datetime.now() + timedelta(hours=hours)).isoformat()
            result["muted_until"] = target["muted_until"]
            if _temail:
                _send_notify_bg(_temail, "Your account has been muted — Lonely Hub",
                    notify_email_html("muted", _tname, duration_text=f"{hours} hour{'s' if hours != 1 else ''}"))
        elif action == "unmute":
            target.pop("muted_until", None)
            result["unmuted"] = True
        elif action == "delete":
            accounts["users"] = [u for u in accounts["users"] if u["id"] != target["id"]]
            save_json("accounts-data.json", accounts)
            return jsonify({"success": True, "deleted": target_id})
        elif action == "grant_perm":
            perm = gh("X-Perm") or data.get("perm", "")
            if perm:
                prev_tag = target.get("tag", "user")
                target["tag"] = perm
                result["tag"] = perm
                if _temail:
                    if perm == "admin" and prev_tag != "admin":
                        _send_notify_bg(_temail, "You have been granted Admin access — Lonely Hub",
                            notify_email_html("admin_granted", _tname))
                    elif perm != "admin" and prev_tag == "admin":
                        _send_notify_bg(_temail, "Admin access revoked — Lonely Hub",
                            notify_email_html("admin_removed", _tname))
        elif action == "grant_verify":
            target["verified"] = True
            result["verified"] = True
            if _temail:
                _send_notify_bg(_temail, "You've been verified on Lonely Hub",
                    notify_email_html("verified_granted", _tname))
        else:
            return jsonify({"success": False, "error": "Unknown action. Use: verify, ban, mute, unmute, delete, grant_perm, grant_verify"}), 400
        save_json("accounts-data.json", accounts)
        return jsonify({"success": True, "user_id": target_id, "action": action, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/v3/data", methods=["GET"])
def api_v3_data():
    try:
        token = request.headers.get("X-Token", request.args.get("token", ""))
        admin_user = _get_api_user(token)
        if not admin_user or not is_admin(admin_user):
            return jsonify({"success": False, "error": "Admin token required"}), 403
        rl = check_api_rate_limit(token.strip())
        if rl:
            return rl
        accounts = load_json("accounts-data.json")
        mods_data = load_json("mods-data.json")
        sessions = load_json("sessions-data.json")
        today = get_today_str()
        all_mods = mods_data["mods"]
        return jsonify({
            "success": True,
            "TotalUsers": len(accounts["users"]),
            "TotalMods": len([m for m in all_mods if m.get("type", "mod") == "mod"]),
            "TotalClients": len([m for m in all_mods if m.get("type") == "client"]),
            "TotalViews": sum(m.get("views", 0) for m in all_mods),
            "TotalDownloads": sum(m.get("downloads", 0) for m in all_mods),
            "ViewsToday": sum(m.get("daily_stats", {}).get(today, {}).get("views", 0) for m in all_mods),
            "DownloadsToday": sum(m.get("daily_stats", {}).get(today, {}).get("downloads", 0) for m in all_mods),
            "ActiveSessions": sum(1 for s in sessions.get("sessions", {}).values() if datetime.fromisoformat(s["expires"]) > datetime.now()),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500






@app.route("/api/admin/save-data", methods=["GET"])
def admin_save_data():
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    import pyzipper
    import io
    buf = io.BytesIO()
    with pyzipper.AESZipFile(buf, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
        zf.setpassword(b"LongHip12")
        for fname in DEFAULT_DATA.keys():
            fpath = os.path.join(DATA_DIR, fname)
            if os.path.exists(fpath):
                zf.write(fpath, fname)
    buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        supabase_backup.save_backup(DATA_DIR, DEFAULT_DATA, label="Manual")
    except Exception:
        pass
    from flask import send_file
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"data_backup_{ts}.zip")


@app.route("/api/admin/backup-to-cloud", methods=["POST"])
def admin_backup_to_cloud():
    """Save backup to Supabase only (JSON response, no download)."""
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    try:
        result = supabase_backup.save_backup(DATA_DIR, DEFAULT_DATA, label="Manual")
        return jsonify({"success": True, "backup": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
@app.route("/admin/backup-history")
def admin_backup_history():
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return redirect("/login")
    return render_template("backup_history.html", user=current_user)


@app.route("/api/admin/supabase-status", methods=["GET"])
def admin_supabase_status():
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    return jsonify({"configured": supabase_backup.is_configured()})


@app.route("/api/admin/backups", methods=["GET"])
def admin_list_backups():
    """List all backups from Supabase."""
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    try:
        limit = min(int(request.args.get("limit", 30)), 50)
        backups = supabase_backup.list_backups(limit=limit)
        return jsonify({"success": True, "backups": backups})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/restore/<backup_id>", methods=["POST"])
def admin_restore_backup(backup_id):
    """Restore data from a Supabase backup."""
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    try:
        row = supabase_backup.restore_backup(backup_id, DATA_DIR)
        return jsonify({"success": True, "restored": row.get("created_at"), "label": row.get("label")})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/backup/<backup_id>", methods=["DELETE"])
def admin_delete_backup(backup_id):
    """Delete a backup from Supabase."""
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    try:
        supabase_backup.delete_backup(backup_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/admin/restore-latest", methods=["POST"])
def admin_restore_latest():
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    try:
        row = supabase_backup.restore_latest_backup(DATA_DIR)
        if not row:
            return jsonify({"success": False, "error": "No backups found"}), 404
        return jsonify({"success": True, "restored": row.get("created_at"), "label": row.get("label")})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/rate-limit", methods=["POST"])
def admin_set_rate_limit():
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    data = request.get_json(silent=True) or {}
    val = data.get("api_rate_limit") or request.form.get("api_rate_limit")
    try:
        limit = max(1, int(val))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid value"}), 400
    settings = load_json("settings-data.json")
    settings["api_rate_limit"] = limit
    save_json("settings-data.json", settings)
    _rate_limit_store.clear()
    return jsonify({"success": True, "api_rate_limit": limit})

@app.route("/api/admin/health", methods=["GET"])
def admin_health():
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    import sys, platform
    uptime = datetime.now() - APP_START_TIME
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours}h {minutes}m {seconds}s"
    data_files_info = []
    for fname in DEFAULT_DATA.keys():
        fpath = os.path.join(DATA_DIR, fname)
        try:
            size = os.path.getsize(fpath)
            data = load_json(fname)
            records = None
            if fname == "accounts-data.json":
                records = len(data.get("users", []))
            elif fname == "mods-data.json":
                records = len(data.get("mods", []))
            elif fname == "forum-data.json":
                records = len(data.get("posts", []))
            elif fname == "sessions-data.json":
                sessions_d = data.get("sessions", {})
                active = sum(1 for s in sessions_d.values() if datetime.fromisoformat(s.get("expires", "1970-01-01")) > datetime.now())
                records = f"{active} active / {len(sessions_d)} total"
            data_files_info.append({"name": fname, "size": f"{size/1024:.1f} KB", "records": records, "ok": True})
        except Exception as e:
            data_files_info.append({"name": fname, "size": "—", "records": None, "ok": False, "error": str(e)})
    env_checks = {
        "SESSION_SECRET": bool(os.environ.get("SESSION_SECRET")),
        "SUPABASE_URL": bool(os.environ.get("SUPABASE_URL")),
        "SUPABASE_SERVICE_KEY": bool(os.environ.get("SUPABASE_SERVICE_KEY")),
        "BREVO_API_KEY": bool(os.environ.get("BREVO_API_KEY")),
        "APP_PASSWORD": bool(os.environ.get("APP_PASSWORD")),
        "GOOGLE_CLIENT_ID": bool(os.environ.get("GOOGLE_CLIENT_ID")),
        "GOOGLE_CLIENT_SECRET": bool(os.environ.get("GOOGLE_CLIENT_SECRET")),
        "GOOGLE_REDIRECT_URI": bool(os.environ.get("GOOGLE_REDIRECT_URI")),
        "DISCORD_CLIENT_ID": bool(os.environ.get("DISCORD_CLIENT_ID")),
        "DISCORD_CLIENT_SECRET": bool(os.environ.get("DISCORD_CLIENT_SECRET")),
        "DISCORD_REDIRECT_URI": bool(os.environ.get("DISCORD_REDIRECT_URI")),
        "DISCORD_GUILD_ID": bool(os.environ.get("DISCORD_GUILD_ID")),
        "DISCORD_BOT_TOKEN": bool(os.environ.get("DISCORD_BOT_TOKEN")),
    }
    services = {
        "email_brevo": env_checks["BREVO_API_KEY"],
        "email_smtp": env_checks["APP_PASSWORD"],
        "google_oauth": env_checks["GOOGLE_CLIENT_ID"] and env_checks["GOOGLE_CLIENT_SECRET"],
        "discord_oauth": env_checks["DISCORD_CLIENT_ID"] and env_checks["DISCORD_CLIENT_SECRET"],
        "discord_bot": env_checks["DISCORD_BOT_TOKEN"] and env_checks["DISCORD_GUILD_ID"],
        "supabase_backup": env_checks["SUPABASE_URL"] and env_checks["SUPABASE_SERVICE_KEY"],
    }
    accounts = load_json("accounts-data.json")
    mods_data = load_json("mods-data.json")
    sessions = load_json("sessions-data.json")
    active_sessions = sum(
        1 for s in sessions.get("sessions", {}).values()
        if datetime.fromisoformat(s.get("expires", "1970-01-01")) > datetime.now()
    )
    return jsonify({
        "success": True,
        "uptime": uptime_str,
        "uptime_seconds": int(uptime.total_seconds()),
        "started_at": APP_START_TIME.isoformat(),
        "python_version": sys.version.split()[0],
        "platform": platform.system(),
        "data_files": data_files_info,
        "env_vars": env_checks,
        "services": services,
        "stats": {
            "users": len(accounts.get("users", [])),
            "mods": len(mods_data.get("mods", [])),
            "active_sessions": active_sessions,
            "total_downloads": sum(m.get("downloads", 0) for m in mods_data.get("mods", [])),
        }
    })


@app.route("/status")
def status_page():
    import sys, platform
    uptime = datetime.now() - APP_START_TIME
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours}h {minutes}m {seconds}s"
    env_checks = {
        "Email (Brevo)": bool(os.environ.get("BREVO_API_KEY")),
        "Email (SMTP)": bool(os.environ.get("APP_PASSWORD")),
        "Google OAuth": bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET")),
        "Discord OAuth": bool(os.environ.get("DISCORD_CLIENT_ID") and os.environ.get("DISCORD_CLIENT_SECRET")),
        "Discord Bot": bool(os.environ.get("DISCORD_BOT_TOKEN") and os.environ.get("DISCORD_GUILD_ID")),
        "Supabase Backup": bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY")),
    }
    accounts = load_json("accounts-data.json")
    mods_data = load_json("mods-data.json")
    sessions = load_json("sessions-data.json")
    active_sessions = sum(
        1 for s in sessions.get("sessions", {}).values()
        if datetime.fromisoformat(s.get("expires", "1970-01-01")) > datetime.now()
    )
    stats = {
        "users": len(accounts.get("users", [])),
        "mods": len(mods_data.get("mods", [])),
        "active_sessions": active_sessions,
        "total_downloads": sum(m.get("downloads", 0) for m in mods_data.get("mods", [])),
    }
    now = datetime.now()
    STATUS_HISTORY.append({
        "t": now.isoformat(timespec='seconds'),
        "ts": int(now.timestamp()),
        "all_ok": all(env_checks.values()),
        "services": env_checks,
    })
    if len(STATUS_HISTORY) > 288:
        del STATUS_HISTORY[:-288]
    all_ok = all(env_checks.values())
    started_at = APP_START_TIME.strftime("%Y-%m-%d %H:%M UTC")
    return render_template(
        "status.html",
        all_ok=all_ok,
        services=env_checks,
        uptime_str=uptime_str,
        started_at=started_at,
        stats=stats,
        history=STATUS_HISTORY,
        python_version=sys.version.split()[0],
        platform=platform.system(),
    )


@app.route("/api/docs")
def api_docs():
    user = get_session_user(request)
    accounts = load_json("accounts-data.json")
    acc = next((u for u in accounts["users"] if user and u["id"] == user["id"]), None) if user else None
    is_admin_user = is_admin(user) if user else False
    return render_template("api_docs.html", user=user, is_admin_user=is_admin_user, user_has_token=bool(acc and acc.get("api_token")) if acc else False)



supabase_backup.startup_restore(DATA_DIR)


supabase_backup.start_auto_backup(DATA_DIR, DEFAULT_DATA)


supabase_backup.start_auto_restore(DATA_DIR)

@app.route("/api/admin/logs", methods=["GET"])
def admin_logs():
    current_user = get_session_user(request)
    if not current_user or not is_admin(current_user):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    since = request.args.get("since", "")
    logs = list(LOG_BUFFER)
    if since:
        logs = [l for l in logs if l['t'] > since]
    return jsonify({"success": True, "logs": logs})

from flask import Response, stream_with_context

def _get_system_prompt(model_key):
    cfg = AI_MODELS_CONFIG.get(model_key, {})
    model_name = cfg.get("name", "an advanced model")
    return (
        f"You are Lonely AI, an intelligent assistant developed by Lonely Hub, built on top of {model_name}'s model. "
        "You specialize in Minecraft and gaming topics but can help with anything. "
        f"If asked who you are, say you are Lonely AI developed by Lonely Hub, based on {model_name}'s model. "
        "Be helpful, friendly, and knowledgeable."
    )

AI_MODELS_CONFIG = {
    "gpt-4o-mini": {
        "name": "GPT-4o-mini",
        "thinking": False,
        "image": "https://i.imgur.com/0DwnmdY.jpeg",
        "provider": "openrouter",
        "model_id": "openai/gpt-4o-mini",
        "api_key_env": "OPENROUTER_GPT4O_MINI_KEY",
    },
    "nvidia-nemotron": {
        "name": "Nvidia Nemotron",
        "thinking": True,
        "image": "https://i.imgur.com/DJgiwrh.png",
        "provider": "nvidia",
        "model_id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        "api_key_env": "NVIDIA_NEMOTRON_KEY",
    },
    "deepseek-v4-flash": {
        "name": "DeepSeek V4 Flash",
        "thinking": False,
        "image": "https://i.imgur.com/0BQqhba.png",
        "provider": "nvidia",
        "model_id": "deepseek-ai/deepseek-v4-flash",
        "api_key_env": "NVIDIA_DEEPSEEK_KEY",
    },
    "lonely-ai": {
        "name": "Lonely AI",
        "thinking": True,
        "image": "https://i.imgur.com/xY7M2iE.jpeg",
        "provider": "poolside",
        "model_id": "poolside/laguna-m.1",
        "api_key_env": "POOLSIDE_API_KEY",
    },
    "llama-3.3-70b": {
        "name": "Meta Llama-3.3-70b",
        "thinking": False,
        "image": "https://i.imgur.com/pESTVyY.jpeg",
        "provider": "nvidia",
        "model_id": "meta/llama-3.3-70b-instruct",
        "api_key_env": "NVIDIA_LLAMA_KEY",
    },
    "owl-alpha": {
        "name": "Owl Alpha",
        "thinking": False,
        "image": "https://raw.githubusercontent.com/LongHip12/LonelyHub/refs/heads/main/1775396168046-019d5dda-a645-745b-84a8-830794cde06a-removebg-preview.png",
        "provider": "openrouter",
        "model_id": "openrouter/owl-alpha",
        "api_key_env": "OPENROUTER_GPT4O_MINI_KEY",
    },
    "kimi-k2.6": {
        "name": "Kimi K2.6",
        "thinking": True,
        "image": "https://i.imgur.com/COgMkUi.jpeg",
        "provider": "nvidia",
        "model_id": "moonshotai/kimi-k2.6",
        "api_key_env": "NVIDIA_KIMI_KEY",
    },
}

def _ai_parse_sse(resp):
    thinking_parts = []
    output_parts = []
    for line in resp.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8") if isinstance(line, bytes) else line
        if line in ("data: [DONE]", "[DONE]"):
            break
        if not line.startswith("data: "):
            continue
        try:
            chunk = json.loads(line[6:])
            if not chunk.get("choices"):
                continue
            delta = chunk["choices"][0].get("delta", {})
            rc = delta.get("reasoning_content")
            if rc:
                thinking_parts.append(rc)
            c = delta.get("content")
            if c:
                output_parts.append(c)
        except Exception:
            pass
    return "".join(thinking_parts).strip(), "".join(output_parts).strip()

def _stream_provider(model_key, messages, enable_thinking):
    cfg = AI_MODELS_CONFIG.get(model_key)
    if not cfg:
        raise ValueError(f"Unknown model: {model_key}")
    provider = cfg["provider"]
    sys_msg = {"role": "system", "content": _get_system_prompt(model_key)}
    full_messages = [sys_msg] + messages

    if provider == "nvidia":
        api_key = os.environ.get(cfg.get("api_key_env", ""), "")
        extra = {}
        if model_key == "kimi-k2.6":
            extra["chat_template_kwargs"] = {"thinking": enable_thinking and cfg.get("thinking", False)}
        elif model_key == "llama-3.3-70b":
            extra["max_tokens"] = 1024
            extra["temperature"] = 0.2
            extra["top_p"] = 0.7
        else:
            extra["chat_template_kwargs"] = {"enable_thinking": enable_thinking and cfg.get("thinking", False)}
            extra["reasoning_budget"] = 16384
        payload = {"model": cfg["model_id"], "messages": full_messages, "temperature": 0.6, "top_p": 0.95, "max_tokens": 13579, "stream": False}
        payload.update(extra)
        resp = requests.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload, timeout=180
        )
        resp.raise_for_status()
        try:
            _d = resp.json()
            _msg = _d["choices"][0].get("message", {})
            _rc = _msg.get("reasoning_content") or _msg.get("reasoning") or ""
            _c = _msg.get("content") or ""
            if _rc:
                yield ("thinking", _rc)
            if _c:
                yield ("content", _c)
        except Exception:
            pass

    elif provider == "poolside":
        api_key = os.environ.get(cfg.get("api_key_env", ""), "")
        resp = requests.post(
            "https://inference.poolside.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "poolside/laguna-m.1", "messages": full_messages, "stream": False, "chat_template_kwargs": {"enable_thinking": enable_thinking}},
            timeout=180
        )
        resp.raise_for_status()
        try:
            _d = resp.json()
            _msg = _d["choices"][0].get("message", {})
            _rc = _msg.get("reasoning_content") or _msg.get("reasoning") or ""
            _c = _msg.get("content") or ""
            if _rc:
                yield ("thinking", _rc)
            if _c:
                yield ("content", _c)
        except Exception:
            pass

    elif provider == "openrouter":
        api_key = os.environ.get(cfg.get("api_key_env", ""), "") or os.environ.get("OPENROUTER_API_KEY", "")
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": cfg["model_id"], "messages": full_messages, "stream": False},
            timeout=120
        )
        resp.raise_for_status()
        try:
            _d = resp.json()
            _msg = _d["choices"][0].get("message", {})
            _rc = _msg.get("reasoning_content") or _msg.get("reasoning") or ""
            _c = _msg.get("content") or ""
            if _rc:
                yield ("thinking", _rc)
            if _c:
                yield ("content", _c)
        except Exception:
            pass

    elif provider == "google":
        api_key = os.environ.get(cfg.get("api_key_env", ""), "")
        contents = []
        sys_text = ""
        for m in full_messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "system":
                sys_text = content if isinstance(content, str) else ""
            elif role == "user":
                if isinstance(content, str):
                    contents.append({"role": "user", "parts": [{"text": content}]})
                else:
                    gparts = []
                    for part in content:
                        if part.get("type") == "text":
                            gparts.append({"text": part["text"]})
                        elif part.get("type") == "image_url":
                            url = part["image_url"]["url"]
                            if url.startswith("data:"):
                                mt, b64 = url.split(",", 1)
                                mime = mt.split(":")[1].split(";")[0]
                                gparts.append({"inlineData": {"mimeType": mime, "data": b64}})
                    contents.append({"role": "user", "parts": gparts})
            elif role == "assistant":
                ct = content if isinstance(content, str) else ""
                contents.append({"role": "model", "parts": [{"text": ct}]})
        g_payload = {"contents": contents}
        if sys_text:
            g_payload["systemInstruction"] = {"parts": [{"text": sys_text}]}
        g_resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{cfg['model_id']}:streamGenerateContent?key={api_key}&alt=sse",
            json=g_payload, timeout=120
        )
        g_resp.raise_for_status()
        try:
            _gd = g_resp.json()
            for cand in _gd.get("candidates", []):
                for gpart in cand.get("content", {}).get("parts", []):
                    gt = gpart.get("text", "")
                    if gt:
                        yield ("content", gt)
        except Exception:
            pass

def _ai_call_openrouter(model_id, messages, api_key=None):
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model_id, "messages": messages},
        timeout=120
    )
    resp.raise_for_status()
    data = resp.json()
    return "", data["choices"][0]["message"]["content"]

def _ai_call_nvidia(model_id, api_key, messages, extra=None):
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.6,
        "top_p": 0.95,
        "max_tokens": 13579,
        "stream": False,
    }
    if extra:
        payload.update(extra)
    resp = requests.post(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=180
    )
    resp.raise_for_status()
    return _ai_parse_sse(resp)

def _ai_call_poolside(messages, enable_thinking, api_key=None):
    api_key = api_key or os.environ.get("POOLSIDE_API_KEY", "")
    resp = requests.post(
        "https://inference.poolside.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "poolside/laguna-m.1",
            "messages": messages,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": enable_thinking},
        },
        timeout=180
    )
    resp.raise_for_status()
    _d = resp.json()
    _msg = _d["choices"][0].get("message", {})
    return (_msg.get("reasoning_content") or _msg.get("reasoning") or ""), (_msg.get("content") or "")

def _ai_call_gemini(messages, api_key=None):
    api_key = api_key or os.environ.get("GOOGLE_GEMINI_KEY", "")
    contents = []
    sys_text = ""
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "system":
            sys_text = content if isinstance(content, str) else ""
        elif role == "user":
            if isinstance(content, str):
                contents.append({"role": "user", "parts": [{"text": content}]})
            else:
                parts = []
                for part in content:
                    if part.get("type") == "text":
                        parts.append({"text": part["text"]})
                    elif part.get("type") == "image_url":
                        url = part["image_url"]["url"]
                        if url.startswith("data:"):
                            mt, b64 = url.split(",", 1)
                            mime = mt.split(":")[1].split(";")[0]
                            parts.append({"inlineData": {"mimeType": mime, "data": b64}})
                contents.append({"role": "user", "parts": parts})
        elif role == "assistant":
            ct = content if isinstance(content, str) else ""
            contents.append({"role": "model", "parts": [{"text": ct}]})
    payload = {"contents": contents}
    if sys_text:
        payload["systemInstruction"] = {"parts": [{"text": sys_text}]}
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}",
        json=payload,
        timeout=120
    )
    resp.raise_for_status()
    data = resp.json()
    return "", data["candidates"][0]["content"]["parts"][0]["text"]

def _do_ai_call(model_key, messages, enable_thinking):
    cfg = AI_MODELS_CONFIG.get(model_key)
    if not cfg:
        raise ValueError(f"Unknown model: {model_key}")
    model_api_key = os.environ.get(cfg.get("api_key_env", ""), "")
    sys_msg = {"role": "system", "content": _get_system_prompt(model_key)}
    full_messages = [sys_msg] + messages
    provider = cfg["provider"]
    if provider == "openrouter":
        return _ai_call_openrouter(cfg["model_id"], full_messages, model_api_key)
    elif provider == "nvidia":
        api_key = os.environ.get(cfg.get("api_key_env", ""), "")
        extra = {}
        if model_key == "kimi-k2.6":
            extra["chat_template_kwargs"] = {"thinking": enable_thinking and cfg.get("thinking", False)}
        elif model_key == "llama-3.3-70b":
            extra["max_tokens"] = 1024
            extra["temperature"] = 0.2
            extra["top_p"] = 0.7
        else:
            extra["chat_template_kwargs"] = {"enable_thinking": enable_thinking and cfg.get("thinking", False)}
            extra["reasoning_budget"] = 16384
        return _ai_call_nvidia(cfg["model_id"], api_key, full_messages, extra)
    elif provider == "poolside":
        return _ai_call_poolside(full_messages, enable_thinking and cfg.get("thinking", False), model_api_key)
    elif provider == "google":
        return _ai_call_gemini(full_messages, model_api_key)
    else:
        raise ValueError(f"Unknown provider: {provider}")

def _load_ai_chats():
    data = load_json("ai-chats.json")
    if "chats" not in data:
        data["chats"] = {}
    return data

def _get_user_chats(user_id):
    data = _load_ai_chats()
    return data["chats"].get(str(user_id), [])

def _save_user_chats(user_id, chats):
    data = _load_ai_chats()
    data["chats"][str(user_id)] = chats
    save_json("ai-chats.json", data)

@app.route("/ai-chat")
def ai_chat_page():
    user = get_session_user(request)
    return render_template("ai_chat.html", user=user, models=AI_MODELS_CONFIG)

@app.route("/ai-chat/<chat_id>")
def ai_chat_page_with_id(chat_id):
    user = get_session_user(request)
    return render_template("ai_chat.html", user=user, models=AI_MODELS_CONFIG, open_chat_id=chat_id)

@app.route("/api/ai/models", methods=["GET"])
def api_ai_models():
    return jsonify({"success": True, "models": AI_MODELS_CONFIG})

@app.route("/api/ai/chats", methods=["GET"])
def api_ai_list_chats():
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Login required"}), 401
    chats = _get_user_chats(user["id"])
    summary = [{"id": c["id"], "title": c.get("title", "New Chat"), "pinned": c.get("pinned", False), "updated_at": c.get("updated_at", ""), "model": c.get("model", "gpt-4o-mini")} for c in chats]
    summary.sort(key=lambda x: (not x["pinned"], x["updated_at"]), reverse=True)
    return jsonify({"success": True, "chats": summary})

@app.route("/api/ai/chats/<chat_id>", methods=["GET"])
def api_ai_get_chat(chat_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Login required"}), 401
    chats = _get_user_chats(user["id"])
    chat = next((c for c in chats if c["id"] == chat_id), None)
    if not chat:
        return jsonify({"success": False, "error": "Not found"}), 404
    return jsonify({"success": True, "chat": chat})

@app.route("/api/ai/chats/<chat_id>", methods=["PATCH"])
def api_ai_update_chat(chat_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Login required"}), 401
    data = request.json or {}
    chats = _get_user_chats(user["id"])
    chat = next((c for c in chats if c["id"] == chat_id), None)
    if not chat:
        return jsonify({"success": False, "error": "Not found"}), 404
    if "title" in data:
        chat["title"] = data["title"]
    if "pinned" in data:
        chat["pinned"] = bool(data["pinned"])
    chat["updated_at"] = datetime.now().isoformat()
    _save_user_chats(user["id"], chats)
    return jsonify({"success": True, "chat": chat})


@app.route("/api/ai/backup", methods=["GET"])
def api_ai_backup():
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Login required"}), 401
    chats = _get_user_chats(user["id"])
    import io
    backup_data = json.dumps({
        "user": user["username"],
        "exported_at": datetime.now().isoformat(),
        "chats": chats,
    }, ensure_ascii=False, indent=2)
    buf = io.BytesIO(backup_data.encode("utf-8"))
    buf.seek(0)
    from flask import send_file
    return send_file(buf, mimetype="application/json",
                     as_attachment=True,
                     download_name=f"lonely_ai_backup_{user['username']}.json")

@app.route("/api/ai/chats/<chat_id>", methods=["DELETE"])
def api_ai_delete_chat(chat_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Login required"}), 401
    chats = _get_user_chats(user["id"])
    chats = [c for c in chats if c["id"] != chat_id]
    _save_user_chats(user["id"], chats)
    return jsonify({"success": True})

@app.route("/api/ai/send", methods=["POST"])
def api_ai_send():
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Login required"}), 401
    data = request.json or {}
    chat_id = data.get("chat_id")
    model_key = data.get("model", "gpt-4o-mini")
    user_text = (data.get("message") or "").strip()
    enable_thinking = bool(data.get("thinking", False))
    files_data = data.get("files", [])
    if not user_text and not files_data:
        return jsonify({"success": False, "error": "Empty message"}), 400
    chats = _get_user_chats(user["id"])
    chat = next((c for c in chats if c["id"] == chat_id), None) if chat_id else None
    if not chat:
        chat = {
            "id": str(uuid.uuid4()),
            "title": "New Chat",
            "pinned": False,
            "model": model_key,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "messages": [],
        }
        chats.insert(0, chat)
    vision_ok = model_key in ("gpt-4o-mini",)
    has_images = any(f.get("type", "").startswith("image/") for f in files_data)
    if files_data and vision_ok and has_images:
        parts = []
        if user_text:
            parts.append({"type": "text", "text": user_text})
        for f in files_data:
            if f.get("type", "").startswith("image/"):
                parts.append({"type": "image_url", "image_url": {"url": f"data:{f['type']};base64,{f['data']}"}})
            else:
                parts.append({"type": "text", "text": f"\n[File: {f['name']}]\n{f.get('text_content','(binary)')}"})
        msg_content = parts
    elif files_data:
        extras = []
        for f in files_data:
            if f.get("type", "").startswith("image/"):
                extras.append(f"[Image: {f['name']}]")
            else:
                tc = f.get("text_content", "")
                extras.append(f"\n[File: {f['name']}]\n{tc}" if tc else f"[File: {f['name']}]")
        msg_content = (user_text + "\n" + "\n".join(extras)).strip() if user_text else "\n".join(extras)
    else:
        msg_content = user_text
    chat["messages"].append({"role": "user", "content": msg_content})
    chat["model"] = model_key
    chat["updated_at"] = datetime.now().isoformat()
    _save_user_chats(user["id"], chats)
    api_messages = [{"role": m["role"], "content": m["content"]} for m in chat["messages"]]
    cfg_model = AI_MODELS_CONFIG.get(model_key, {})
    def generate():
        thinking_parts = []
        output_parts = []
        t0 = time.time()
        yield f"data: {json.dumps({'type': 'start', 'chat_id': chat['id'], 'model_name': cfg_model.get('name', 'AI'), 'model_image': cfg_model.get('image', '')})}\n\n"
        try:
            for kind, chunk in _stream_provider(model_key, api_messages, enable_thinking):
                if kind == "thinking":
                    thinking_parts.append(chunk)
                    yield f"data: {json.dumps({'type': 'thinking', 'chunk': chunk})}\n\n"
                elif kind == "content":
                    output_parts.append(chunk)
                    yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
            return
        thinking = "".join(thinking_parts).strip()
        output = "".join(output_parts).strip()
        thinking_time = int(time.time() - t0)
        chat["messages"].append({"role": "assistant", "content": output, "thinking": thinking, "thinking_time": thinking_time, "model": model_key})
        chat["updated_at"] = datetime.now().isoformat()
        if len(chat["messages"]) == 2:
            try:
                _, title_text = _do_ai_call("gpt-4o-mini", [{"role": "user", "content": f"Generate a very short title (max 5 words, no quotes, no end punctuation) for a chat starting with: {user_text[:200] if user_text else 'file'}"}], False)
                chat["title"] = title_text.strip().strip("\"'").strip()[:60]
            except Exception:
                pass
        _save_user_chats(user["id"], chats)
        yield f"data: {json.dumps({'type': 'done', 'thinking_time': thinking_time, 'title': chat.get('title', 'New Chat')})}\n\n"
    return Response(stream_with_context(generate()), mimetype="text/event-stream", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})
@app.route("/api/ai/send/<chat_id>/retry", methods=["POST"])
def api_ai_retry(chat_id):
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Login required"}), 401
    chats = _get_user_chats(user["id"])
    chat = next((c for c in chats if c["id"] == chat_id), None)
    if not chat:
        return jsonify({"success": False, "error": "Not found"}), 404
    if chat["messages"] and chat["messages"][-1]["role"] == "assistant":
        chat["messages"].pop()
    if not chat["messages"]:
        return jsonify({"success": False, "error": "Nothing to retry"}), 400
    _save_user_chats(user["id"], chats)
    model_key = chat.get("model", "gpt-4o-mini")
    payload = request.json or {}
    enable_thinking = bool(payload.get("thinking", False))
    api_messages = [{"role": m["role"], "content": m["content"]} for m in chat["messages"]]
    cfg_model = AI_MODELS_CONFIG.get(model_key, {})
    def generate():
        thinking_parts = []
        output_parts = []
        t0 = time.time()
        yield f"data: {json.dumps({'type': 'start', 'model_name': cfg_model.get('name', 'AI'), 'model_image': cfg_model.get('image', '')})}\n\n"
        try:
            for kind, chunk in _stream_provider(model_key, api_messages, enable_thinking):
                if kind == "thinking":
                    thinking_parts.append(chunk)
                    yield f"data: {json.dumps({'type': 'thinking', 'chunk': chunk})}\n\n"
                elif kind == "content":
                    output_parts.append(chunk)
                    yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
            return
        thinking = "".join(thinking_parts).strip()
        output = "".join(output_parts).strip()
        thinking_time = int(time.time() - t0)
        chat["messages"].append({"role": "assistant", "content": output, "thinking": thinking, "thinking_time": thinking_time, "model": model_key})
        chat["updated_at"] = datetime.now().isoformat()
        _save_user_chats(user["id"], chats)
        yield f"data: {json.dumps({'type': 'done', 'thinking_time': thinking_time})}\n\n"
    return Response(stream_with_context(generate()), mimetype="text/event-stream", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})
@app.route("/api/v2/chat/ai", methods=["POST"])
def api_v2_chat_ai():
    x_token = (request.headers.get("X-Token") or "").strip()
    if not x_token:
        return jsonify({"success": False, "error": "X-Token header required"}), 401
    accounts = load_json("accounts-data.json")
    auth_user = next((u for u in accounts.get("users", []) if (u.get("api_token") or "").strip() == x_token), None)
    if not auth_user:
        return jsonify({"success": False, "error": "Invalid token"}), 401
    data = request.json or {}
    model_key = data.get("model", "gpt-4o-mini")
    messages = data.get("messages", [])
    enable_thinking = bool(data.get("thinking", False))
    stream_mode = bool(data.get("stream", False))
    cfg = AI_MODELS_CONFIG.get(model_key)
    if not cfg:
        return jsonify({"success": False, "error": f"Unknown model. Available: {list(AI_MODELS_CONFIG.keys())}"}), 400
    if stream_mode:
        def generate():
            try:
                thinking_out, output = _do_ai_call(model_key, messages, enable_thinking)
                if thinking_out:
                    yield f"data: {json.dumps({'type': 'thinking', 'content': thinking_out})}\n\n"
                for i in range(0, len(output), 4):
                    yield f"data: {json.dumps({'type': 'content', 'content': output[i:i+4]})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        return Response(stream_with_context(generate()), mimetype="text/event-stream")
    try:
        thinking_out, output = _do_ai_call(model_key, messages, enable_thinking)
        return jsonify({"success": True, "thinking": thinking_out, "output": output, "model": model_key})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
