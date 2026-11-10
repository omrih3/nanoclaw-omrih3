#!/usr/bin/env python3
"""Receipts helper: Gmail read-only scan + Google Drive filing + state file.

Credentials are injected by the OneCLI gateway; this script never sees tokens.
State lives in /workspace/agent/receipts-state.json.
Commands (all print JSON):
  gmail-list [--since EPOCH] [--max N]   candidate receipt emails since watermark
  gmail-get ID --out DIR                 save attachments + body of one email
  upload FILE --category C --date YYYY-MM-DD --vendor V [--total T --currency C
         --source telegram|gmail --gmail-id ID --ocr-file F]
  mark-seen ID                           mark an email as handled (not a receipt)
  scan-commit                            advance the watermark (after a clean scan)
  categories                             list categories with file counts
  state                                  show state summary
"""
import argparse, base64, hashlib, json, os, re, subprocess, sys, time, urllib.parse, uuid

STATE = os.environ.get("RECEIPTS_STATE", "/workspace/agent/receipts-state.json")
ROOT_NAME = "Receipts"
MAX_CATEGORIES = 20
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
DRIVE = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
KEYWORDS = ('(receipt OR invoice OR "tax invoice" OR "order confirmation" OR "payment received" '
            'OR "your order" OR "payment confirmation" OR קבלה OR חשבונית OR "חשבונית מס" OR "אישור תשלום")')
FILE_TYPES = {".pdf", ".png", ".jpg", ".jpeg", ".heic", ".webp"}


def load():
    try:
        return json.load(open(STATE))
    except FileNotFoundError:
        return {"root_id": None, "categories": {}, "hashes": {}, "gmail_seen": [], "watermark": None, "pending_watermark": None}


def save(s):
    tmp = STATE + ".tmp"
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(s, open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


def out(o):
    print(json.dumps(o, ensure_ascii=False))


def curl(method, url, json_body=None, data_file=None, ctype=None, raw=False):
    cmd = ["curl", "-sS", "--max-time", "120", "-X", method, url]
    if json_body is not None:
        cmd += ["-H", "Content-Type: application/json", "--data-binary", json.dumps(json_body)]
    if data_file:
        cmd += ["-H", f"Content-Type: {ctype}", "--data-binary", f"@{data_file}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"curl failed: {r.stderr.strip()}")
    try:
        j = json.loads(r.stdout)
    except ValueError:
        sys.exit(f"non-JSON response: {r.stdout[:300]}")
    if isinstance(j, dict) and "error" in j:
        sys.exit(f"API error: {json.dumps(j['error'], ensure_ascii=False)[:500]}")
    return j


def q(s):
    return urllib.parse.quote(s, safe="")


def esc(s):
    return s.replace("\\", "\\\\").replace("'", "\\'")


def folder(s, name, parent):
    query = f"name='{esc(name)}' and mimeType='application/vnd.google-apps.folder' and '{parent}' in parents and trashed=false"
    r = curl("GET", f"{DRIVE}/files?q={q(query)}&fields=files(id,name)&pageSize=1")
    if r.get("files"):
        return r["files"][0]["id"]
    r = curl("POST", f"{DRIVE}/files?fields=id", {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent]})
    return r["id"]


def safe(s, n=60):
    return re.sub(r"[^\w֐-׿.\- ]+", "", s).strip().replace(" ", "-")[:n] or "unknown"


def cmd_upload(a):
    s = load()
    cat = a.category.strip()
    if cat not in s["categories"] and len(s["categories"]) >= MAX_CATEGORIES:
        sys.exit(f"category limit ({MAX_CATEGORIES}) reached; reuse one of: {', '.join(s['categories'])}")
    data = open(a.file, "rb").read()
    h = hashlib.sha256(data).hexdigest()
    if h in s["hashes"]:
        out({"duplicate": True, "fileId": s["hashes"][h]}); return
    if not s["root_id"]:
        s["root_id"] = folder(s, ROOT_NAME, "root")
    if cat not in s["categories"]:
        s["categories"][cat] = {"id": folder(s, cat, s["root_id"]), "count": 0}
    ext = os.path.splitext(a.file)[1].lower() or ".bin"
    name = f"{a.date}_{safe(a.vendor)}_{safe(a.total or 'na', 20)}{('-' + safe(a.currency, 5)) if a.currency else ''}{ext}"
    ocr = open(a.ocr_file, encoding="utf-8", errors="replace").read() if a.ocr_file else ""
    desc = f"{a.vendor} | {a.date} | {a.total or ''} {a.currency or ''} | {cat}\n{re.sub(chr(10)+'+', chr(10), ocr)}".strip()[:3500]
    props = {"date": a.date, "vendor": a.vendor[:50], "total": (a.total or "")[:20], "cur": (a.currency or "")[:5], "src": a.source or ""}
    if a.gmail_id:
        props["gmid"] = a.gmail_id
    meta = {"name": name, "parents": [s["categories"][cat]["id"]], "description": desc, "appProperties": props}
    mime = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".heic": "image/heic"}.get(ext, "application/octet-stream")
    b = uuid.uuid4().hex
    body = (f"--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta, ensure_ascii=False)}\r\n--{b}\r\nContent-Type: {mime}\r\n\r\n").encode() + data + f"\r\n--{b}--".encode()
    tmp = f"{STATE}.upload"
    open(tmp, "wb").write(body)
    try:
        r = curl("POST", f"{UPLOAD}?uploadType=multipart&fields=id,name,webViewLink", data_file=tmp, ctype=f"multipart/related; boundary={b}")
    finally:
        os.remove(tmp)
    s["hashes"][h] = r["id"]
    s["categories"][cat]["count"] += 1
    if a.gmail_id and a.gmail_id not in s["gmail_seen"]:
        s["gmail_seen"].append(a.gmail_id)
    save(s)
    out({"ok": True, "id": r["id"], "name": r["name"], "category": cat, "link": r.get("webViewLink")})


def walk(parts):
    for p in parts or []:
        yield p
        yield from walk(p.get("parts"))


def cmd_list(a):
    s = load()
    since = a.since or s["watermark"] or int(time.time()) - 30 * 86400
    s["pending_watermark"] = int(time.time()) - 3600  # 1h overlap; dedupe handles repeats
    save(s)
    query = f"after:{since} -in:chats {KEYWORDS}"
    ids, tok = [], ""
    while len(ids) < a.max:
        r = curl("GET", f"{GMAIL}/messages?q={q(query)}&maxResults=100{('&pageToken=' + tok) if tok else ''}")
        ids += [m["id"] for m in r.get("messages", [])]
        tok = r.get("nextPageToken", "")
        if not tok:
            break
    res = []
    for i in ids[: a.max]:
        if i in s["gmail_seen"]:
            continue
        m = curl("GET", f"{GMAIL}/messages/{i}?format=full")
        h = {x["name"].lower(): x["value"] for x in m["payload"].get("headers", [])}
        atts = [{"filename": p["filename"], "mime": p["mimeType"], "size": p["body"].get("size", 0)}
                for p in walk([m["payload"]]) if p.get("filename") and p["body"].get("attachmentId")]
        res.append({"id": i, "from": h.get("from"), "subject": h.get("subject"), "date": h.get("date"), "snippet": m.get("snippet"), "attachments": atts})
    out({"since": since, "count": len(res), "messages": res})


def cmd_get(a):
    m = curl("GET", f"{GMAIL}/messages/{a.id}?format=full")
    os.makedirs(a.out, exist_ok=True)
    saved = []
    for p in walk([m["payload"]]):
        fn, body = p.get("filename"), p.get("body", {})
        if fn and body.get("attachmentId") and os.path.splitext(fn)[1].lower() in FILE_TYPES:
            d = curl("GET", f"{GMAIL}/messages/{a.id}/attachments/{body['attachmentId']}")["data"]
            path = os.path.join(a.out, os.path.basename(fn))
            open(path, "wb").write(base64.urlsafe_b64decode(d + "=" * (-len(d) % 4)))
            saved.append(path)
        elif p.get("mimeType") in ("text/html", "text/plain") and body.get("data") and not fn:
            d = body["data"]
            path = os.path.join(a.out, "body." + ("html" if p["mimeType"] == "text/html" else "txt"))
            open(path, "wb").write(base64.urlsafe_b64decode(d + "=" * (-len(d) % 4)))
            saved.append(path)
    out({"saved": saved})


def cmd_seen(a):
    s = load()
    if a.id not in s["gmail_seen"]:
        s["gmail_seen"].append(a.id)
    s["gmail_seen"] = s["gmail_seen"][-5000:]
    save(s); out({"ok": True})


def cmd_commit(a):
    s = load()
    if not s.get("pending_watermark"):
        sys.exit("no pending watermark; run gmail-list first")
    s["watermark"], s["pending_watermark"] = s["pending_watermark"], None
    save(s); out({"watermark": s["watermark"], "iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s["watermark"]))})


def cmd_cats(a):
    out({k: v["count"] for k, v in load()["categories"].items()})


def cmd_state(a):
    s = load()
    out({"root_id": s["root_id"], "categories": len(s["categories"]), "files": len(s["hashes"]), "gmail_seen": len(s["gmail_seen"]), "watermark": s["watermark"]})


p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sp = p.add_subparsers(dest="c", required=True)
x = sp.add_parser("gmail-list"); x.add_argument("--since", type=int); x.add_argument("--max", type=int, default=100); x.set_defaults(f=cmd_list)
x = sp.add_parser("gmail-get"); x.add_argument("id"); x.add_argument("--out", required=True); x.set_defaults(f=cmd_get)
x = sp.add_parser("upload"); x.add_argument("file")
for k in ("category", "date", "vendor"): x.add_argument("--" + k, required=True)
for k in ("total", "currency", "source", "gmail-id", "ocr-file"): x.add_argument("--" + k)
x.set_defaults(f=cmd_upload)
x = sp.add_parser("mark-seen"); x.add_argument("id"); x.set_defaults(f=cmd_seen)
sp.add_parser("scan-commit").set_defaults(f=cmd_commit)
sp.add_parser("categories").set_defaults(f=cmd_cats)
sp.add_parser("state").set_defaults(f=cmd_state)
a = p.parse_args()
a.f(a)
