import csv
import io
import sqlite3
from datetime import date
from datetime import datetime
import os
from PIL import Image, ImageOps
from flask import Flask, Response, redirect, render_template_string, request, url_for
import scanner

app = Flask(__name__)
DB = "collection.db"


def get_db():
    # one connection per request: SQLite connections should not be shared across threads
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row          # rows behave like dictionaries
    conn.execute("PRAGMA foreign_keys = ON")  # off by default in SQLite
    return conn


NAV = """
<!doctype html><meta name=viewport content="width=device-width, initial-scale=1">
<title>Collection</title>
<style>body{font:16px system-ui;max-width:640px;margin:1rem auto;padding:0 1rem}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ccc;padding:4px;text-align:left}</style>
<p><a href="{{ url_for('search') }}">Search</a> | <a href="{{ url_for('collection') }}">Collection</a> | <a href="{{ url_for('scan') }}">Scan</a></p>
"""

SEARCH = NAV + """
<h1>Add a card</h1>
<form><input name="q" value="{{ q }}" autofocus> <button>Search</button></form>
<ul>{% for r in rows %}
<li><a href="{{ url_for('add', set_code=r.set_code, set_no=r.set_no) }}">
{{ r.name }}{% if r.color %} ({{ r.color }}){% endif %} - {{ r.set_code }}{{ r.set_no }}</a></li>
{% endfor %}</ul>
"""

ADD = NAV + """
<h1>{{ card.name }}{% if card.color %} ({{ card.color }}){% endif %}</h1>
<p>{{ card.set_code }}{{ card.set_no }}</p>
{% if error %}<p style="color:#c00">{{ error }}</p>{% endif %}
<form method="post">
  <p>Finish<br><select name="printing_id">
  {% for p in printings %}<option value="{{ p.printing_id }}">{{ p.finish }} - edition {{ p.edition }}{% if p.art_variations %} - {{ p.art_variations }}{% endif %}</option>{% endfor %}
  </select></p>
  <p>Quantity<br><input name="qty" value="1"></p>
  <p>Price paid per copy (optional)<br><input name="price" placeholder="4.50"></p>
  <p>Purchase date<br><input name="when" value="{{ today }}"></p>
  <p>Notes (optional)<br><input name="notes" placeholder="armoury packs, gift, etc."></p>
  <button>Save</button>
</form>
"""

COLLECTION = NAV + """
<h1>My collection</h1>
<p>{{ totals.copies or 0 }} copies, spent {{ '%.2f' % ((totals.spent or 0) / 100) }}
 | <a href="{{ url_for('export') }}">Export CSV</a></p>
<table><tr><th>Card</th><th>Set</th><th>Finish</th><th>Qty</th><th>Paid</th><th>Date</th><th>Notes</th></tr>
{% for r in rows %}<tr><td>{{ r.name }}{% if r.color %} ({{ r.color }}){% endif %}</td>
<td>{{ r.set_code }}{{ r.set_no }}</td><td>{{ r.finish }}</td><td>{{ r.quantity }}</td>
<td>{% if r.price_pence is not none %}{{ '%.2f' % (r.price_pence / 100) }}{% endif %}</td><td>{{ r.purchase_date }}</td>
<td>{% if r.notes is not none %}{{ r.notes }}{% endif %}</td></tr>
{% endfor %}</table>
"""


@app.route("/")
def search():
    q = request.args.get("q", "").strip()
    rows = []
    if q:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT DISTINCT name, color, pitch, set_code, set_no FROM printings "
                "WHERE name LIKE ? ORDER BY name, set_code, set_no LIMIT 50",
                (f"%{q}%",)).fetchall()
    return render_template_string(SEARCH, q=q, rows=rows)


def parse_entry(form):
    """Check the form on the server and return (quantity, price in pence, date)."""
    try:
        qty = int(form["qty"])
    except ValueError:
        raise ValueError("Quantity must be a whole number.")
    if qty < 1:
        raise ValueError("Quantity must be at least 1.")
    price = form["price"].strip()
    try:
        pence = round(float(price) * 100) if price else None
    except ValueError:
        raise ValueError("Price must be a number such as 4.50.")
    if pence is not None and pence < 0:
        raise ValueError("Price can't be negative.")
    try:
        when = date.fromisoformat(form["when"]).isoformat()
    except ValueError:
        raise ValueError("Date must look like 2026-10-17.")
    try:
        notes = form["notes"].strip()
    except ValueError:
        raise ValueError("")
    return qty, pence, when, notes


@app.route("/add/<set_code>/<int:set_no>", methods=["GET", "POST"])
def add(set_code, set_no):
    conn = get_db()
    printings = conn.execute(
        "SELECT * FROM printings WHERE set_code = ? AND set_no = ? ORDER BY finish, edition",
        (set_code, set_no)).fetchall()
    if not printings:
        return "No such card", 404
    error = ""
    if request.method == "POST":
        try:
            qty, pence, when, notes = parse_entry(request.form)
            with conn:
                conn.execute(
                    "INSERT INTO collection (printing_id, quantity, price_pence, purchase_date, notes) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (request.form["printing_id"], qty, pence, when, notes))
            return redirect(url_for("collection"))
        except ValueError as e:
            error = str(e)
        except sqlite3.IntegrityError:
            error = "That printing isn't in the catalogue."
    return render_template_string(ADD, card=printings[0], printings=printings,
                                  today=date.today().isoformat(), error=error)


COLLECTION_SQL = """
                 SELECT p.name, p.color, p.set_code, p.set_no, p.finish, p.edition,
                        c.quantity, c.price_pence, c.purchase_date, c.notes
                 FROM collection c JOIN printings p ON p.printing_id = c.printing_id
                 ORDER BY p.name, p.set_code, p.set_no \
                 """

@app.route("/collection")
def collection():
    conn = get_db()
    rows = conn.execute(COLLECTION_SQL).fetchall()
    totals = conn.execute(
        "SELECT SUM(quantity) AS copies, SUM(quantity * price_pence) AS spent FROM collection").fetchone()
    return render_template_string(COLLECTION, rows=rows, totals=totals)


@app.route("/export.csv")
def export():
    rows = get_db().execute(COLLECTION_SQL).fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["name", "colour", "set", "set_number", "finish", "edition",
                "quantity", "price_paid_each", "purchase_date"])
    for r in rows:
        paid = "" if r["price_pence"] is None else f"{r['price_pence'] / 100:.2f}"
        w.writerow([r["name"], r["color"] or "", r["set_code"], r["set_no"], r["finish"],
                    r["edition"], r["quantity"], paid, r["purchase_date"]])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=collection.csv"})

os.makedirs("photos", exist_ok=True)

SCAN_FORM = """
<form method="POST" enctype="multipart/form-data">
    <input type="file" name="photo" accept="image/*" required>
    <button type="submit">Scan</button>
</form>
"""

@app.route("/scan", methods=["GET", "POST"])        # replaces the scan function from Step 13
def scan():
    print ("entered scan page")
    if request.method == "POST":
        name = datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".jpg"
        path = os.path.join("photos", name)
        request.files["photo"].save(path)
        print ("took photo. saved to path: " + path)

        conn = get_db()
        valid = {r[0] for r in conn.execute("SELECT DISTINCT set_code FROM printings")}
        text = " ".join(scanner.read_text(scanner.strip_of(path, 0.75, 1.0)))
        print("text read by ocr: " + text)
        found = scanner.parse_code(text, valid)
        if found:
            print("found")
            exists = conn.execute(
                "SELECT 1 FROM printings WHERE set_code = ? AND set_no = ? LIMIT 1", found).fetchone()
            if exists:       # the add page IS the confirmation step: you check, then save
                return redirect(url_for("add", set_code=found[0], set_no=found[1]))
        return redirect(url_for("search"))           # couldn't read it: fall back to manual search
    return SCAN_FORM