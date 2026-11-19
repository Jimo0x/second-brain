"""Second Brain — serveur Flask."""
import glob
import os

from flask import Flask, jsonify, request, send_from_directory

from brain.core import Brain, read_file

HERE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
brain = Brain(os.environ.get("BRAIN_DB", os.path.join(HERE, "brain.db")))


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/notes")
def notes():
    return jsonify(brain.notes())


@app.get("/api/notes/<int:nid>")
def note(nid):
    n = brain.note(nid)
    return jsonify(n) if n else (jsonify({"error": "introuvable"}), 404)


@app.post("/api/notes")
def create():
    d = request.get_json() or {}
    if not d.get("body", "").strip():
        return jsonify({"error": "Note vide"}), 400
    return jsonify({"id": brain.add(d.get("title") or d["body"].strip().split("\n")[0][:60], d["body"])})


@app.put("/api/notes/<int:nid>")
def update(nid):
    d = request.get_json() or {}
    brain.update(nid, d.get("title", "Sans titre"), d.get("body", ""))
    return jsonify({"ok": True})


@app.delete("/api/notes/<int:nid>")
def delete(nid):
    brain.delete(nid)
    return jsonify({"ok": True})


@app.post("/api/import")
def import_files():
    added, errors = [], []
    for f in request.files.getlist("files"):
        try:
            text = read_file(f.filename, f.read())
            if text.strip():
                title = os.path.splitext(os.path.basename(f.filename))[0]
                added.append(brain.add(title, text, source=f.filename))
        except ValueError as e:
            errors.append(f"{f.filename} : {e}")
    return jsonify({"added": added, "errors": errors})


@app.post("/api/examples")
def examples():
    existing = {n["title"] for n in brain.notes()}
    n = 0
    for p in sorted(glob.glob(os.path.join(HERE, "examples", "*.md"))):
        title = os.path.splitext(os.path.basename(p))[0]
        if title not in existing:
            body = open(p, encoding="utf-8").read()
            brain.add(title, "\n".join(body.split("\n")[1:]).strip(), source="exemple")
            n += 1
    return jsonify({"added": n})


@app.get("/api/search")
def search():
    return jsonify(brain.search(request.args.get("q", ""), k=8))


@app.post("/api/ask")
def ask():
    q = (request.get_json() or {}).get("question", "").strip()
    if not q:
        return jsonify({"error": "Question vide"}), 400
    return jsonify(brain.ask(q))


@app.get("/api/graph")
def graph():
    return jsonify(brain.graph(float(request.args.get("t", 0.06))))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5005))
    print(f"Second Brain → http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, threaded=True)
