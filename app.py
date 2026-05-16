import os
import json
from dotenv import load_dotenv
load_dotenv()
import uuid
import secrets
import mimetypes
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify, make_response, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import supabase_backup

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET") or secrets.token_hex(32)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
FORUM_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "forum_uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
HCAPTCHA_SECRET = os.environ.get("SECRET", "")
HCAPTCHA_SITE_KEY = os.environ.get("KEY", "")
MAX_FILE_SIZE = 10 * 1024 * 1024
FORUM_MAX_FILE_SIZE = 50 * 1024 * 1024

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, "modbanner"), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, "avatars"), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, "banners"), exist_ok=True)
os.makedirs(FORUM_UPLOAD_DIR, exist_ok=True)

DEFAULT_DATA = {
    "accounts-data.json": {"users": []},
    "mods-data.json": {"mods": [], "next_id": 1, "next_client_id": 1},
    "sessions-data.json": {"sessions": {}},
    "forum-data.json": {"posts": []},
    "settings-data.json": {"api_rate_limit": 60},
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
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
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
    if not token:
        return None
    sessions = load_json("sessions-data.json")
    session = sessions.get("sessions", {}).get(token)
    if not session:
        return None
    try:
        expires = datetime.fromisoformat(session["expires"])
    except (KeyError, ValueError):
        return None
    if datetime.now() > expires:
        sessions["sessions"].pop(token, None)
        save_json("sessions-data.json", sessions)
        return None
    accounts = load_json("accounts-data.json")
    return next((u for u in accounts.get("users", []) if u["id"] == session["user_id"]), None)


def create_session(user_id, remember=False):
    token = secrets.token_hex(32)
    expires = datetime.now() + (timedelta(days=30) if remember else timedelta(hours=2))
    sessions = load_json("sessions-data.json")
    sessions.setdefault("sessions", {})[token] = {
        "user_id": user_id,
        "expires": expires.isoformat()
    }
    save_json("sessions-data.json", sessions)
    return token, expires


def verify_hcaptcha(token):
    if not token:
        return False
    try:
        resp = requests.post("https://hcaptcha.com/siteverify", data={
            "secret": HCAPTCHA_SECRET,
            "response": token
        }, timeout=5)
        return resp.json().get("success", False)
    except Exception:
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
    data = request.get_json()
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
            found = next((u for u in accounts["users"] if u["username"].lower() == username.lower()), None)
            if found and check_password_hash(found["password"], password):
                token, expires = create_session(found["id"], remember)
                next_url = request.args.get("next", url_for("index"))
                resp = make_response(jsonify({"success": True, "redirect": next_url}))
                resp.set_cookie("session_token", token, expires=expires, httponly=True, secure=True, samesite="Lax")
                return resp
            else:
                error = "Invalid username or password"
        return jsonify({"success": False, "error": error})
    next_url = request.args.get("next", "")
    return render_template("login.html", user=None, error=error, next_url=next_url, hcaptcha_site_key=HCAPTCHA_SITE_KEY)


@app.route("/register", methods=["GET", "POST"])
def register():
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
        elif len(username) < 3 or len(username) > 20:
            error = "Username must be 3-20 characters"
        elif not username.replace("_", "").replace("-", "").isalnum():
            error = "Username can only contain letters, numbers, - and _"
        elif len(password) < 6:
            error = "Password must be at least 6 characters"
        else:
            accounts = load_json("accounts-data.json")
            if any(u["username"].lower() == username.lower() for u in accounts["users"]):
                error = "Username already taken"
            else:
                new_id = str(uuid.uuid4())
                accounts["users"].append({
                    "id": new_id,
                    "username": username,
                    "display_name": username,
                    "password": generate_password_hash(password),
                    "tag": "user",
                    "avatar": "",
                    "banner": "",
                    "description": "",
                    "followers": [],
                    "following": [],
                    "created_at": datetime.now().isoformat(),
                    "username_last_changed": None,
                    "muted_until": None,
                    "banned_until": None,
                    "admin_until": None
                })
                save_json("accounts-data.json", accounts)
                token, expires = create_session(new_id, remember)
                next_url = request.args.get("next", url_for("index"))
                resp = make_response(jsonify({"success": True, "redirect": next_url}))
                resp.set_cookie("session_token", token, expires=expires, httponly=True, samesite="Lax")
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
    resp = make_response(redirect(url_for("index")))
    resp.delete_cookie("session_token")
    return resp


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
    mods_data["mods"] = [m for m in mods_data["mods"] if m["id"] != mod_id]
    save_json("mods-data.json", mods_data)
    return redirect(url_for("admin_pages"))


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
        image_url = ""
        if "image" in request.files:
            file = request.files["image"]
            if file and file.filename and allowed_file(file.filename):
                ext = file.filename.rsplit(".", 1)[1].lower()
                fname = f"{uuid.uuid4()}.{ext}"
                file.save(os.path.join(UPLOAD_DIR, "modbanner", fname))
                image_url = f"/static/uploads/modbanner/{fname}"
    else:
        data = request.get_json() or {}
        text = data.get("text", "").strip()
        reply_to_id = data.get("reply_to_id", "")
        reply_to_name = data.get("reply_to_name", "")
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
    data = request.get_json() or {}
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
    user = get_session_user(request)
    return redirect(f"/error?code=404&msg=Page+not+found")


@app.errorhandler(403)
def forbidden(e):
    user = get_session_user(request)
    return redirect(f"/error?code=403&msg=Access+forbidden")


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
    if content or files:
        attachments = save_forum_files(files)
        msg.setdefault("replies", []).append({
            "id": str(uuid.uuid4()),
            "author_id": user["id"] if user else None,
            "content": content,
            "created_at": datetime.now().isoformat(),
            "reply_to_id": msg_id,
            "attachments": attachments,
        })
        save_forum(forum)
    redir = url_for("forum_post", post_id=post_id) + "#msg-" + msg_id
    return jsonify({"success": True, "redirect": redir})


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


@app.route("/api/change-password", methods=["POST"])
def change_password():
    user = get_session_user(request)
    if not user:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    data = request.get_json(silent=True) or {}
    current_pw = data.get("current_password", "")
    new_pw = data.get("new_password", "")
    confirm_pw = data.get("confirm_password", "")
    if not check_password_hash(user.get("password", ""), current_pw):
        return jsonify({"success": False, "error": "Current password is incorrect"}), 400
    if len(new_pw) < 6:
        return jsonify({"success": False, "error": "New password must be at least 6 characters"}), 400
    if new_pw != confirm_pw:
        return jsonify({"success": False, "error": "Passwords do not match"}), 400
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
        if action == "verify":
            target["verified"] = not bool(target.get("verified", False))
            result["verified"] = target["verified"]
        elif action == "ban":
            target["banned"] = not bool(target.get("banned", False))
            result["banned"] = target["banned"]
        elif action == "mute":
            hours = int(gh("X-Hours") or data.get("hours", 24) or 24)
            target["muted_until"] = (datetime.now() + timedelta(hours=hours)).isoformat()
            result["muted_until"] = target["muted_until"]
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
                target["tag"] = perm
                result["tag"] = perm
        elif action == "grant_verify":
            target["verified"] = True
            result["verified"] = True
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
    # Also save to Supabase (non-blocking, best-effort)
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

@app.route("/api/docs")
def api_docs():
    user = get_session_user(request)
    accounts = load_json("accounts-data.json")
    acc = next((u for u in accounts["users"] if user and u["id"] == user["id"]), None) if user else None
    is_admin_user = is_admin(user) if user else False
    return render_template("api_docs.html", user=user, is_admin_user=is_admin_user, user_has_token=bool(acc and acc.get("api_token")) if acc else False)


# Startup: restore from Supabase if local data is empty
supabase_backup.startup_restore(DATA_DIR)

# Start Supabase auto-backup every 5 minutes
supabase_backup.start_auto_backup(DATA_DIR, DEFAULT_DATA)

# Start Supabase auto-restore every 15 minutes
supabase_backup.start_auto_restore(DATA_DIR)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
