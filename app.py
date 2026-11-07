import os
import sqlite3
import uuid
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "fish_marketplace.db"
UPLOAD_FOLDER = BASE_DIR / "static" / "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-before-deployment")
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ChangeMe123!")
WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "")  # International format, digits only, e.g. 201001234567


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DATABASE) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS fish (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                food TEXT NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                image TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                address TEXT NOT NULL,
                notes TEXT,
                items TEXT NOT NULL,
                total REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'New',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        existing = db.execute("SELECT id FROM admins WHERE username = ?", (ADMIN_USERNAME,)).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
                (ADMIN_USERNAME, generate_password_hash(ADMIN_PASSWORD))
            )
        db.commit()


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_image(file):
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        raise ValueError("Please upload a JPG, PNG, WEBP, or GIF image.")
    extension = secure_filename(file.filename).rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{extension}"
    file.save(UPLOAD_FOLDER / filename)
    return filename


@app.route("/")
def home():
    fish = get_db().execute("SELECT * FROM fish WHERE quantity > 0 ORDER BY created_at DESC").fetchall()
    return render_template("index.html", fish=fish)


@app.route("/fish/<int:fish_id>")
def fish_details(fish_id):
    item = get_db().execute("SELECT * FROM fish WHERE id = ?", (fish_id,)).fetchone()
    if not item:
        abort(404)
    return render_template("fish_details.html", item=item, whatsapp=WHATSAPP_NUMBER)


@app.route("/search")
def search():
    term = request.args.get("q", "").strip()
    fish = get_db().execute(
        "SELECT * FROM fish WHERE quantity > 0 AND (name LIKE ? OR description LIKE ? OR food LIKE ?) ORDER BY name",
        (f"%{term}%", f"%{term}%", f"%{term}%")
    ).fetchall()
    return render_template("index.html", fish=fish, search_term=term)


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("customer_name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        notes = request.form.get("notes", "").strip()
        cart_ids = request.form.getlist("fish_id")
        if not name or not phone or not address or not cart_ids:
            flash("Please complete your details and add at least one fish.", "error")
            return redirect(url_for("checkout"))
        order_items = []
        total = 0
        selected_quantities = []
        for fish_id in cart_ids:
            try:
                qty = max(1, int(request.form.get(f"quantity_{fish_id}", "1")))
                fish_id_int = int(fish_id)
            except ValueError:
                continue
            item = db.execute("SELECT * FROM fish WHERE id = ?", (fish_id_int,)).fetchone()
            if not item or item["quantity"] < qty:
                flash("One of the selected fish is no longer available in that quantity.", "error")
                return redirect(url_for("checkout"))
            subtotal = item["price"] * qty
            total += subtotal
            selected_quantities.append((fish_id_int, qty))
            order_items.append(f'{item["name"]} x {qty} (EGP {subtotal:.2f})')
        if not order_items:
            flash("Your cart is empty.", "error")
            return redirect(url_for("checkout"))
        for fish_id_int, qty in selected_quantities:
            db.execute("UPDATE fish SET quantity = quantity - ? WHERE id = ?", (qty, fish_id_int))
        cursor = db.execute(
            "INSERT INTO orders (customer_name, phone, address, notes, items, total) VALUES (?, ?, ?, ?, ?, ?)",
            (name, phone, address, notes, "; ".join(order_items), total)
        )
        order_id = cursor.lastrowid
        db.commit()
        session["last_order_id"] = order_id
        return redirect(url_for("order_success", order_id=order_id))
    return render_template("checkout.html", fish=db.execute("SELECT * FROM fish WHERE quantity > 0 ORDER BY name").fetchall())


@app.route("/order-success/<int:order_id>")
def order_success(order_id):
    order = get_db().execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        abort(404)
    return render_template("order_success.html", order=order, whatsapp=WHATSAPP_NUMBER)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        admin = get_db().execute("SELECT * FROM admins WHERE username = ?", (username,)).fetchone()
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect username or password.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
@admin_required
def admin_logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    fish = db.execute("SELECT * FROM fish ORDER BY created_at DESC").fetchall()
    orders = db.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 20").fetchall()
    return render_template("admin_dashboard.html", fish=fish, orders=orders)


@app.route("/admin/fish/add", methods=["GET", "POST"])
@admin_required
def add_fish():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        food = request.form.get("food", "").strip()
        try:
            price = float(request.form.get("price", "0"))
            quantity = int(request.form.get("quantity", "0"))
            if price < 0 or quantity < 0:
                raise ValueError
        except ValueError:
            flash("Enter a valid non-negative price and quantity.", "error")
            return render_template("fish_form.html", item=None)
        if not name or not description or not food:
            flash("Please complete all required fields.", "error")
            return render_template("fish_form.html", item=None)
        try:
            image = save_image(request.files.get("image"))
        except ValueError as error:
            flash(str(error), "error")
            return render_template("fish_form.html", item=None)
        get_db().execute(
            "INSERT INTO fish (name, description, food, price, quantity, image) VALUES (?, ?, ?, ?, ?, ?)",
            (name, description, food, price, quantity, image)
        )
        get_db().commit()
        flash("Fish added successfully.", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("fish_form.html", item=None)


@app.route("/admin/fish/<int:fish_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_fish(fish_id):
    db = get_db()
    item = db.execute("SELECT * FROM fish WHERE id = ?", (fish_id,)).fetchone()
    if not item:
        abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        food = request.form.get("food", "").strip()
        try:
            price = float(request.form.get("price", "0"))
            quantity = int(request.form.get("quantity", "0"))
            if price < 0 or quantity < 0:
                raise ValueError
        except ValueError:
            flash("Enter a valid non-negative price and quantity.", "error")
            return render_template("fish_form.html", item=item)
        image = item["image"]
        try:
            new_image = save_image(request.files.get("image"))
            if new_image:
                image = new_image
        except ValueError as error:
            flash(str(error), "error")
            return render_template("fish_form.html", item=item)
        db.execute(
            "UPDATE fish SET name=?, description=?, food=?, price=?, quantity=?, image=? WHERE id=?",
            (name, description, food, price, quantity, image, fish_id)
        )
        db.commit()
        flash("Fish updated successfully.", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("fish_form.html", item=item)


@app.route("/admin/fish/<int:fish_id>/delete", methods=["POST"])
@admin_required
def delete_fish(fish_id):
    db = get_db()
    item = db.execute("SELECT image FROM fish WHERE id = ?", (fish_id,)).fetchone()
    if item:
        db.execute("DELETE FROM fish WHERE id = ?", (fish_id,))
        db.commit()
        if item["image"]:
            image_path = UPLOAD_FOLDER / item["image"]
            if image_path.exists():
                image_path.unlink()
    flash("Fish deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def update_order_status(order_id):
    status = request.form.get("status", "New")
    if status not in {"New", "Processing", "Completed", "Cancelled"}:
        abort(400)
    get_db().execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    get_db().commit()
    return redirect(url_for("admin_dashboard"))


@app.errorhandler(413)
def file_too_large(error):
    flash("Image is too large. Maximum upload size is 8 MB.", "error")
    return redirect(request.referrer or url_for("admin_dashboard"))


UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
init_db()

if __name__ == "__main__":
    app.run(debug=True)
