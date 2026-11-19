"""Second Brain — stockage, index vectoriel, liens entre idées et réponses (RAG)."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import threading
import urllib.request
from dataclasses import dataclass

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

STOP = """a à afin ai alors au aussi autre aux avec avoir bien c ça car ce cela celle celui ces cet cette ceux chaque comme comment d dans de des
du donc dont elle elles en encore entre est et été être eux fait faire faut il ils j je l la le les leur leurs lui m ma mais me même mes moi mon
n ne ni nos notre nous on ont ou où par pas peu peut plus pour pourquoi qu que quel quelle quels qui quoi s sa sans se ses si son sont sous sur
ta te tes toi ton tous tout toute toutes très tu un une vos votre vous y the a an and are as at be by for from has have how in is it its of on
or that the this to was were what when where which who why will with you your can not but if then than so do does""".split()


_STOPSET = set(STOP)


def stem(w: str) -> str:
    """Racinisation légère FR/EN : on retire les terminaisons courantes puis on tronque."""
    for suf in ("ements", "ement", "ations", "ation", "ités", "ité", "euses", "euse", "eurs", "eur", "ives", "ive", "ing", "ies", "es", "s", "e"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            w = w[: -len(suf)]
            break
    return w[:7]


def analyzer(text: str) -> list[str]:
    toks = [t for t in re.findall(r"[a-zà-ÿ][a-zà-ÿ0-9-]+", text.lower()) if t not in _STOPSET and len(t) > 2]
    st = [stem(t) for t in toks]
    return st + [f"{a}_{b}" for a, b in zip(st, st[1:])]


@dataclass
class Chunk:
    note_id: int
    title: str
    text: str
    pos: int


def read_file(name: str, data: bytes) -> str:
    ext = os.path.splitext(name)[1].lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
            import io
            return "\n\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
        except ImportError:
            try:
                return subprocess.run(["pdftotext", "-layout", "-", "-"], input=data, capture_output=True, check=True).stdout.decode("utf-8", "ignore")
            except Exception as e:  # pragma: no cover
                raise ValueError("Pour importer des PDF : pip install pypdf") from e
    return data.decode("utf-8", errors="ignore")


def chunk_text(text: str, size: int = 700) -> list[str]:
    """Découpe en passages d'environ `size` caractères en respectant les paragraphes."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        if len(p) > size * 1.5:  # paragraphe géant : découpe par phrases
            for s in re.split(r"(?<=[.!?])\s+", p):
                if len(cur) + len(s) > size and cur:
                    out.append(cur.strip())
                    cur = ""
                cur += " " + s
            continue
        if len(cur) + len(p) > size and cur:
            out.append(cur.strip())
            cur = ""
        cur += "\n\n" + p
    if cur.strip():
        out.append(cur.strip())
    return out or [text[:size]]


class Brain:
    def __init__(self, path: str):
        self.path = path
        self.lock = threading.RLock()
        con = self._con()
        con.executescript("""CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY, title TEXT, body TEXT, source TEXT,
                             created TEXT DEFAULT CURRENT_TIMESTAMP, tags TEXT DEFAULT '[]');""")
        con.close()
        self.rebuild()

    def _con(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    # ── notes
    def add(self, title: str, body: str, source: str = "manuel") -> int:
        tags = sorted(set(re.findall(r"(?<!\w)#([\wÀ-ÿ-]{2,30})", body)))
        with self.lock:
            con = self._con()
            nid = con.execute("INSERT INTO notes(title, body, source, tags) VALUES(?,?,?,?)", (title, body, source, json.dumps(tags))).lastrowid
            con.commit()
            con.close()
            self.rebuild()
        return nid

    def update(self, nid: int, title: str, body: str) -> None:
        tags = sorted(set(re.findall(r"(?<!\w)#([\wÀ-ÿ-]{2,30})", body)))
        with self.lock:
            con = self._con()
            con.execute("UPDATE notes SET title=?, body=?, tags=? WHERE id=?", (title, body, json.dumps(tags), nid))
            con.commit()
            con.close()
            self.rebuild()

    def delete(self, nid: int) -> None:
        with self.lock:
            con = self._con()
            con.execute("DELETE FROM notes WHERE id=?", (nid,))
            con.commit()
            con.close()
            self.rebuild()

    def notes(self) -> list[dict]:
        con = self._con()
        rows = [dict(r) for r in con.execute("SELECT id, title, source, created, tags, length(body) AS size FROM notes ORDER BY id DESC")]
        con.close()
        for r in rows:
            r["tags"] = json.loads(r["tags"])
        return rows

    def note(self, nid: int) -> dict | None:
        con = self._con()
        r = con.execute("SELECT * FROM notes WHERE id=?", (nid,)).fetchone()
        con.close()
        if not r:
            return None
        d = dict(r)
        d["tags"] = json.loads(d["tags"])
        d["related"] = self.related(nid)
        d["backlinks"] = [n for n in self._all() if re.search(r"\[\[" + re.escape(d["title"]) + r"\]\]", n["body"], re.I) and n["id"] != nid]
        d["backlinks"] = [{"id": n["id"], "title": n["title"]} for n in d["backlinks"]]
        return d

    def _all(self) -> list[dict]:
        con = self._con()
        rows = [dict(r) for r in con.execute("SELECT id, title, body, tags FROM notes ORDER BY id")]
        con.close()
        return rows

    # ── index vectoriel (TF-IDF + LSA) reconstruit à chaque modification
    def rebuild(self) -> None:
        with self.lock:
            self.rows = self._all()
            self.chunks = [Chunk(n["id"], n["title"], t, i) for n in self.rows for i, t in enumerate(chunk_text(n["title"] + "\n\n" + n["body"]))]
            self.vec = self.svd = None
            if not self.chunks:
                return
            self.vec = TfidfVectorizer(analyzer=analyzer, sublinear_tf=True, min_df=1)
            from collections import Counter
            words = Counter(t for c in self.chunks for t in re.findall(r"[a-zà-ÿ][a-zà-ÿ0-9-]+", c.text.lower()) if t not in _STOPSET and len(t) > 2)
            self.stem_word = {}
            for w, _ in words.most_common():
                self.stem_word.setdefault(stem(w), w)
            X = self.vec.fit_transform([c.text for c in self.chunks])
            k = min(64, X.shape[1] - 1, X.shape[0] - 1)
            if k >= 8:  # LSA : rapproche les passages qui partagent des concepts sans partager les mots exacts
                self.svd = TruncatedSVD(k, random_state=0)
                Z = self.svd.fit_transform(X)
                Z /= np.linalg.norm(Z, axis=1, keepdims=True) + 1e-9
                Xd = X.toarray()
                Xd /= np.linalg.norm(Xd, axis=1, keepdims=True) + 1e-9
                self.M = np.hstack([Xd * 0.6 ** 0.5, Z * 0.4 ** 0.5])
            else:
                Xd = X.toarray()
                self.M = Xd / (np.linalg.norm(Xd, axis=1, keepdims=True) + 1e-9)
            ids = [n["id"] for n in self.rows]
            self.note_ids = ids
            self.NM = np.array([self.M[[i for i, c in enumerate(self.chunks) if c.note_id == nid]].mean(0) for nid in ids])
            self.NM /= np.linalg.norm(self.NM, axis=1, keepdims=True) + 1e-9

    def _embed(self, q: str) -> np.ndarray:
        x = self.vec.transform([q])
        xd = x.toarray()
        xd /= np.linalg.norm(xd) + 1e-9
        if self.svd is not None:
            z = self.svd.transform(x)
            z /= np.linalg.norm(z) + 1e-9
            return np.hstack([xd * 0.6 ** 0.5, z * 0.4 ** 0.5])[0]
        return xd[0]

    def search(self, q: str, k: int = 6) -> list[dict]:
        with self.lock:
            if not self.chunks or self.vec is None:
                return []
            sims = self.M @ self._embed(q)
            out, seen = [], set()
            for i in np.argsort(-sims):
                if sims[i] <= 0.05 or len(out) >= k:
                    break
                c = self.chunks[i]
                if (c.note_id, c.pos) in seen:
                    continue
                seen.add((c.note_id, c.pos))
                out.append({"note_id": c.note_id, "title": c.title, "text": c.text, "score": round(float(sims[i]), 3)})
            return out

    def related(self, nid: int, k: int = 5) -> list[dict]:
        with self.lock:
            if self.vec is None or nid not in self.note_ids:
                return []
            i = self.note_ids.index(nid)
            sims = self.NM @ self.NM[i]
            return [{"id": self.note_ids[j], "title": self.rows[j]["title"], "score": round(float(sims[j]), 3)}
                    for j in np.argsort(-sims) if j != i and sims[j] > 0.04][:k]

    def graph(self, threshold: float = 0.06) -> dict:
        """Nœuds = notes ; liens = similarité sémantique, [[wikiliens]] ou tags communs."""
        with self.lock:
            nodes = [{"id": n["id"], "title": n["title"], "tags": json.loads(n["tags"]), "size": len(n["body"])} for n in self.rows]
            links: dict[tuple, dict] = {}
            if self.vec is not None and len(self.rows) > 1:
                S = self.NM @ self.NM.T
                terms = np.array(self.vec.get_feature_names_out())
                for a in range(len(self.rows)):
                    for b in np.argsort(-S[a])[1:4]:
                        if S[a, b] >= threshold:
                            key = tuple(sorted((self.rows[a]["id"], self.rows[b]["id"])))
                            if key not in links:
                                links[key] = {"source": key[0], "target": key[1], "w": round(float(S[a, b]), 3), "kind": "sens",
                                              "why": self._shared_terms(a, b, terms)}
            tags = {n["id"]: set(json.loads(n["tags"])) for n in self.rows}
            ids = list(tags)
            for i, a in enumerate(ids):
                for b in ids[i + 1:]:
                    common = tags[a] & tags[b]
                    if common and (a, b) not in links:
                        links[(a, b)] = {"source": a, "target": b, "w": 0.25, "kind": "tag", "why": ["#" + t for t in sorted(common)]}
            by_title = {n["title"].lower(): n["id"] for n in self.rows}
            for n in self.rows:
                for t in re.findall(r"\[\[([^\]]+)\]\]", n["body"]):
                    if t.lower() in by_title and by_title[t.lower()] != n["id"]:
                        key = tuple(sorted((n["id"], by_title[t.lower()])))
                        links[key] = {"source": key[0], "target": key[1], "w": 1.0, "kind": "lien", "why": ["[[" + t + "]]"]}
            return {"nodes": nodes, "links": list(links.values())}

    def _shared_terms(self, a: int, b: int, terms) -> list[str]:
        va = self.vec.transform([self.rows[a]["body"]]).toarray()[0]
        vb = self.vec.transform([self.rows[b]["body"]]).toarray()[0]
        idx = np.argsort(-(va * vb))[:3]
        nice = lambda t: " ".join(self.stem_word.get(p, p) for p in t.split("_"))
        return [nice(terms[i]) for i in idx if va[i] * vb[i] > 0]

    # ── questions / réponses
    def ask(self, question: str) -> dict:
        hits = self.search(question, k=5)
        if not hits:
            return {"answer": "Je ne trouve rien dans vos notes à ce sujet.", "sources": [], "mode": "extractif"}
        llm = _llm(question, hits)
        if llm:
            return {"answer": llm, "sources": hits, "mode": "llm"}
        return {"answer": self._extractive(question, hits), "sources": hits, "mode": "extractif"}

    def _extractive(self, question: str, hits: list[dict]) -> str:
        """Sélectionne les phrases des meilleurs passages les plus proches de la question."""
        qv = self._embed(question)
        cands, titles = [], {h["title"].strip().lower() for h in hits}
        for h_i, h in enumerate(hits[:3]):
            for s in re.split(r"(?<=[.!?])\s+|\n+", h["text"]):
                s = s.strip(" -*#")
                if len(s) < 25 or s.lower() in titles:
                    continue
                cands.append((float(self._embed(s) @ qv) + 0.05 * (3 - h_i), h_i, s))
        best = sorted(cands, reverse=True)[:3]
        if not best:
            return hits[0]["text"][:400]
        return " ".join(f"{s} [{i + 1}]" for _, i, s in best)


def _llm(question: str, hits: list[dict]) -> str | None:
    """Génération optionnelle si une clé ANTHROPIC_API_KEY ou OPENAI_API_KEY est définie."""
    ctx = "\n\n".join(f"[{i + 1}] ({h['title']})\n{h['text']}" for i, h in enumerate(hits))
    prompt = (f"Réponds à la question en t'appuyant UNIQUEMENT sur les extraits de notes ci-dessous. Cite les sources entre crochets [n]. "
              f"Si l'information manque, dis-le.\n\n{ctx}\n\nQuestion : {question}")
    try:
        if os.environ.get("ANTHROPIC_API_KEY"):
            req = urllib.request.Request("https://api.anthropic.com/v1/messages", method="POST",
                                         headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"},
                                         data=json.dumps({"model": os.environ.get("BRAIN_MODEL", "claude-haiku-5-5"), "max_tokens": 600,
                                                          "messages": [{"role": "user", "content": prompt}]}).encode())
            return json.loads(urllib.request.urlopen(req, timeout=60).read())["content"][0]["text"]
        if os.environ.get("OPENAI_API_KEY"):
            req = urllib.request.Request("https://api.openai.com/v1/chat/completions", method="POST",
                                         headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"], "content-type": "application/json"},
                                         data=json.dumps({"model": os.environ.get("BRAIN_MODEL", "gpt-4o-mini"),
                                                          "messages": [{"role": "user", "content": prompt}]}).encode())
            return json.loads(urllib.request.urlopen(req, timeout=60).read())["choices"][0]["message"]["content"]
    except Exception as e:  # pragma: no cover
        print("LLM indisponible :", e)
    return None
