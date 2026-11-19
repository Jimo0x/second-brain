import os, sys, pathlib, tempfile
ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
os.environ["BRAIN_DB"] = tempfile.mktemp(suffix=".db"); os.environ.pop("ANTHROPIC_API_KEY", None); os.environ.pop("OPENAI_API_KEY", None)
from app import app, brain
from brain.core import chunk_text

def setup_module():
    assert app.test_client().post("/api/examples").json["added"] == 10

def test_search_finds_right_note():
    top = brain.search("comment stocker un mot de passe de façon sûre", k=3)[0]
    assert top["title"] == "Hachage des mots de passe"

def test_ask_cites_sources():
    r = app.test_client().post("/api/ask", json={"question": "Qu'est-ce que la similarité cosinus ?"}).json
    assert r["mode"] == "extractif" and "[1]" in r["answer"] and r["sources"][0]["title"] in ("Embeddings", "RAG")

def test_graph_has_wikilinks_and_semantic_links():
    g = app.test_client().get("/api/graph").json
    assert len(g["nodes"]) == 10 and any(l["kind"] == "lien" for l in g["links"]) and any(l["kind"] == "sens" for l in g["links"])

def test_related_and_backlinks():
    rag = next(n for n in brain.notes() if n["title"] == "RAG")
    d = brain.note(rag["id"]); assert any(b["title"] == "Embeddings" for b in d["backlinks"])

def test_chunking():
    parts = chunk_text("\n\n".join(["Paragraphe numéro %d avec du texte." % i * 5 for i in range(40)]), 300)
    assert len(parts) > 5 and all(len(p) < 700 for p in parts)
