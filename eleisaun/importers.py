"""Impor sentru votasaun husi CSV (jeografia + diáspora). Validasaun lubuk ida molok grava; atomik."""
import csv
import io
import re
import unicodedata

from django.db import transaction

from .models import Aldeia, AdministrativePost, Centre, Municipality, Nasaun, Village

MAX_ROWS = 20000
MAX_BYTES = 3 * 1024 * 1024

# naran kolona kanónika -> alias (Tetun / Português / English / Indonesia)
ALIASES = {
    "code": ["code", "kodigu", "codigo", "kode", "centre_code", "sentru_kodigu"],
    "name": ["name", "naran", "nome", "nama", "centre_name", "sentru"],
    "voters": ["voters", "registered_voters", "eleitor", "eleitores", "pemilih", "registered", "eleitor_rejistadu"],
    "municipality": ["municipality", "munisipiu", "municipio", "kabupaten"],
    "municipality_code": ["municipality_code", "munisipiu_kodigu"],
    "hckey": ["hckey", "hc_key", "hc-key"],
    "post": ["post", "postu", "posto", "administrativepost", "administrative_post", "kecamatan"],
    "village": ["village", "suku", "suco", "desa"],
    "aldeia": ["aldeia", "dusun"],
    "nasaun": ["nasaun", "country", "pais", "negara", "diaspora"],
}
REQUIRED = ["code", "name", "voters"]
TEMPLATE = (
    "code,name,voters,municipality,post,village,aldeia,nasaun,municipality_code,hckey\n"
    "DL-0001,Eskola Dili 1,850,Dili,Dom Aleixo,Comoro,Aldeia 1,,DL,tl-dl\n"
    "DL-0002,Eskola Dili 2,640,Dili,Dom Aleixo,Comoro,,,DL,tl-dl\n"
    "DP-0001,Sentru Lisboa,1200,,,,,Portugal,,\n"
)


def _norm(s):
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return re.sub(r"[^a-z0-9_\-]+", "_", "".join(c for c in s if not unicodedata.combining(c))).strip("_")


class Rollback(Exception):
    pass


def decode(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError("size")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("encoding")


def parse(text):
    """Return (rows[list of dict kanónika], errors[list])."""
    errors = []
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rd = csv.reader(io.StringIO(text), dialect)
    try:
        header = next(rd)
    except StopIteration:
        return [], [(0, "File mamuk.")]
    alias_map = {}
    for canon, als in ALIASES.items():
        for a in als:
            alias_map[_norm(a)] = canon
    cols = {}
    for i, h in enumerate(header):
        c = alias_map.get(_norm(h))
        if c and c not in cols:
            cols[c] = i
    missing = [c for c in REQUIRED if c not in cols]
    if missing:
        return [], [(1, f"Kolona la hetan: {', '.join(missing)}. Kolona ne'ebé iha: {', '.join(header)}")]
    rows = []
    for n, rec in enumerate(rd, start=2):
        if not any(x.strip() for x in rec):
            continue
        if len(rows) >= MAX_ROWS:
            errors.append((n, f"Liu limite {MAX_ROWS} linha."))
            break
        rows.append({"_line": n, **{c: (rec[i].strip() if i < len(rec) else "") for c, i in cols.items()}})
    return rows, errors


def import_centres(text, apply=False):
    """Valida (no grava se apply=True no la iha error). Return dict relatóriu."""
    rows, errors = parse(text)
    rep = {"rows": len(rows), "errors": list(errors), "applied": False,
           "new": {"centre": 0, "municipality": 0, "post": 0, "village": 0, "aldeia": 0, "nasaun": 0},
           "updated": 0, "unchanged": 0, "preview": []}
    if errors and not rows:
        return rep

    seen = {}
    try:
        with transaction.atomic():
            for r in rows:
                n = r["_line"]
                code = r.get("code", "")
                if not code or len(code) > 20:
                    rep["errors"].append((n, "Kódigu mamuk ka naruk liu (maks 20)."))
                    continue
                if code in seen:
                    rep["errors"].append((n, f"Kódigu {code} duplikadu (linha {seen[code]})."))
                    continue
                seen[code] = n
                name = r.get("name", "")
                if not name or len(name) > 120:
                    rep["errors"].append((n, "Naran mamuk ka naruk liu."))
                    continue
                try:
                    voters = int(r.get("voters", "").replace(".", "").replace(" ", ""))
                    if voters < 0:
                        raise ValueError
                except ValueError:
                    rep["errors"].append((n, f"Eleitór rejistadu la válidu: '{r.get('voters', '')}'."))
                    continue
                nas, mun, post, vil = (r.get(k, "") for k in ("nasaun", "municipality", "post", "village"))
                if nas and (mun or post or vil):
                    rep["errors"].append((n, "Hili nasaun (diáspora) ka munisípiu/postu/suku — la bele rua."))
                    continue
                if not nas and not (mun and post and vil):
                    rep["errors"].append((n, "Presiza munisípiu + postu + suku (ka nasaun ba diáspora)."))
                    continue
                if any(len(x) > 100 for x in (nas, mun, post, vil, r.get("aldeia", ""))):
                    rep["errors"].append((n, "Naran jeográfiku naruk liu."))
                    continue
                if mun and len(mun) > 50:
                    rep["errors"].append((n, "Naran munisípiu naruk liu (maks 50)."))
                    continue

                village = aldeia = nasaun = None
                if nas:
                    nasaun = Nasaun.objects.filter(name__iexact=nas).first()
                    if not nasaun:
                        nasaun = Nasaun.objects.create(name=nas); rep["new"]["nasaun"] += 1
                else:
                    m = Municipality.objects.filter(name__iexact=mun).first()
                    if not m:
                        m = Municipality.objects.create(name=mun, code=r.get("municipality_code") or None,
                                                        hckey=r.get("hckey") or None)
                        rep["new"]["municipality"] += 1
                    else:
                        ch = False
                        if r.get("hckey") and m.hckey != r["hckey"]:
                            m.hckey, ch = r["hckey"], True
                        if r.get("municipality_code") and m.code != r["municipality_code"]:
                            m.code, ch = r["municipality_code"], True
                        if ch:
                            m.save()
                    p = AdministrativePost.objects.filter(municipality=m, name__iexact=post).first()
                    if not p:
                        p = AdministrativePost.objects.create(municipality=m, name=post); rep["new"]["post"] += 1
                    village = Village.objects.filter(administrativepost=p, name__iexact=vil).first()
                    if not village:
                        village = Village.objects.create(administrativepost=p, name=vil); rep["new"]["village"] += 1
                    if r.get("aldeia"):
                        aldeia = Aldeia.objects.filter(village=village, name__iexact=r["aldeia"]).first()
                        if not aldeia:
                            aldeia = Aldeia.objects.create(village=village, name=r["aldeia"]); rep["new"]["aldeia"] += 1

                existing = Centre.objects.filter(code=code).first()
                if existing:
                    same_loc = (existing.village_id == (village.id if village else None)
                                and existing.nasaun_id == (nasaun.id if nasaun else None))
                    if existing.reports.exists() and (not same_loc or existing.registered_voters != voters):
                        rep["errors"].append((n, f"Sentru {code} iha relatóriu ona — la bele muda fatin/eleitór."))
                        continue
                    changed = (not same_loc or existing.name != name or existing.registered_voters != voters
                               or existing.aldeia_id != (aldeia.id if aldeia else None))
                    if changed:
                        existing.village, existing.nasaun, existing.aldeia = village, nasaun, aldeia
                        existing.name, existing.registered_voters = name, voters
                        existing.save()
                        rep["updated"] += 1
                        kind = "update"
                    else:
                        rep["unchanged"] += 1
                        kind = "same"
                else:
                    Centre.objects.create(code=code, name=name, registered_voters=voters, village=village,
                                          aldeia=aldeia, nasaun=nasaun)
                    rep["new"]["centre"] += 1
                    kind = "new"
                if len(rep["preview"]) < 15:
                    rep["preview"].append({"code": code, "name": name, "voters": voters, "kind": kind,
                                           "where": f"Diáspora · {nas}" if nas else f"{vil} · {post} · {mun}"})
            if rep["errors"] or not apply:
                raise Rollback
            rep["applied"] = True
    except Rollback:
        pass
    return rep
