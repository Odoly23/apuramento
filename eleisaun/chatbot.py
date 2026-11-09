"""Asistente tanya-jawab (baseia ba regra + dadus diretu, la presiza API externu).

Hatene lian 4: tet, pt, en, id. Jawab husi dadus real-time no panduan sistema.
"""
import re
import unicodedata

from .models import Municipality
from .services import build_snapshot

_ORDER = ("tet", "pt", "en", "id")


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9%\s]", " ", s)


# intent -> kata-xave (tet/pt/en/id mistura)
INTENTS = {
    "greet": ["bondia", "botarde", "boanoite", "hello", "hi", "hola", "ola", "halo", "selamat", "bom dia", "boa tarde"],
    "how_submit": ["oinsa hatama", "hatama", "submit", "enviar", "introduzir", "kirim", "input", "isi data",
                   "cara input", "how to enter", "how do i", "como", "hatama dadus", "fiskal", "fiskais", "fiscal"],
    "photo": ["foto", "prova", "photo", "evidence", "bukti", "ata", "imagem", "gambar", "upload"],
    "security": ["seguransa", "seguranca", "segur", "aman", "keamanan", "secure", "security", "hash", "audit",
                 "hack", "peritu", "kriptograf", "tamper", "dalan", "fraud", "fraude", "kecurangan", "manipul"],
    "leader": ["lidera", "lider", "leads", "lead", "leader", "unggul", "ganha", "venser", "vence", "leading", "winner", "wins", "menang",
               "unggul", "pemimpin", "iha oin", "first", "primeiro", "hira", "klasifika", "ranking"],
    "turnout": ["partisipasaun", "partisipacao", "turnout", "participation", "partisipasi", "komparese"],
    "progress": ["progresu", "progresso", "progress", "kemajuan", "sentru", "centro", "centre", "pusat", "relata",
                 "reportad", "melapor", "porsentu", "kontadu", "counted", "contados", "dihitung"],
    "conflict": ["konflitu", "conflito", "conflict", "konflik", "diferensa", "diferenca", "bertentangan"],
    "verify": ["verifika", "verific", "verify", "verifikasi", "konfirma", "confirm"],
    "roles": ["papel", "papél", "role", "peran", "hakat", "permissao", "permiss", "akses", "access", "mdi",
              "monitor", "partidu nain", "pemilik partai"],
    "invalid": ["nulu", "nulo", "brankus", "branco", "invalid", "blank", "kosong", "tidak sah"],
    "total": ["total", "votu hotu", "votos", "suara", "votes"],
    "language": ["lian", "idioma", "language", "bahasa", "tetun", "portugues", "english", "indonesia"],
    "help": ["ajuda", "help", "bantuan", "bantu", "tulun", "funsaun", "funcao", "function", "fungsi", "uza", "usar"],
}

R = {
    "greet": ("Bondia! Husu mai kona-ba rezultadu (ez. 'sé lidera?', 'rezultadu Dili'), partidu, partisipasaun, ka oinsá uza sistema.",
              "Olá! Pergunte sobre resultados (ex. 'quem lidera?', 'resultados Dili'), partidos, participação ou como usar o sistema.",
              "Hello! Ask about results (e.g. 'who leads?', 'results Dili'), parties, turnout or how to use the system.",
              "Halo! Tanya soal hasil (mis. 'siapa unggul?', 'hasil Dili'), partai, partisipasi, atau cara memakai sistem."),
    "how_submit": ("Pasu ba fiskál: 1) Tama ho ita-nia konta. 2) Hili sentru iha 'Ha'u-nia sentru'. 3) Hatama total eleitór ne'ebé vota, votu brankus, nulu no votu kada kandidatu/lista — soma tenke hanesan. 4) Hasai foto ata rezultadu (to'o 6). 5) Klik 'Haruka'. Sistema rai hash SHA-256 ba relatóriu ida-idak.",
                   "Passos do fiscal: 1) Entre. 2) Escolha o centro em 'Os meus centros'. 3) Introduza votantes, brancos, nulos e votos por candidato/lista — a soma deve coincidir. 4) Fotografe a ata (até 6). 5) Clique em 'Enviar'. O sistema guarda um hash SHA-256 de cada relatório.",
                   "Monitor steps: 1) Sign in. 2) Pick a centre under 'My centres'. 3) Enter total voters, blank, invalid and votes per candidate/list — the sum must match. 4) Photograph the result sheet (up to 6). 5) Press 'Submit'. The system stores a SHA-256 hash for every report.",
                   "Langkah fiskal: 1) Masuk. 2) Pilih pusat di 'Pusat saya'. 3) Isi total pemilih, kosong, tidak sah, dan suara tiap kandidat/daftar — jumlah harus cocok. 4) Foto berita acara (maks 6). 5) Klik 'Kirim'. Sistem menyimpan hash SHA-256 tiap laporan."),
    "photo": ("Foto prova obrigatóriu: foto klaru husi ata rezultadu (JPG/PNG/WEBP, to'o 8 MB, to'o 6 foto). Sistema verifika konteúdu foto, rai SHA-256 no la bele troka maske hafoin verifikadu. Foto sira la públiku: de'it ema ne'ebé iha direitu bele haree.",
              "Foto obrigatória: imagem nítida da ata (JPG/PNG/WEBP, até 8 MB, até 6). O sistema valida o conteúdo, guarda o SHA-256 e bloqueia alterações após a verificação. As fotos não são públicas.",
              "A photo is mandatory: a clear picture of the result sheet (JPG/PNG/WEBP, up to 8 MB, up to 6). The system validates content, stores a SHA-256 and locks it after verification. Photos are never public.",
              "Foto wajib: gambar jelas berita acara (JPG/PNG/WEBP, maks 8 MB, maks 6). Sistem memvalidasi isi, menyimpan SHA-256, dan mengunci setelah verifikasi. Foto tidak publik."),
    "security": ("Seguransa: (1) Papél ketak — fiskál, monitór, verifikadór. (2) Foto no relatóriu iha hash SHA-256. (3) Audit log ho korrente hash — se ema muda, korrente kuak no sistema hatudu. (4) Bloku login depois tentativa 5. (5) HTTPS, CSP, cookie seguru. (6) Relatóriu verifikadu la bele muda.",
                 "Segurança: (1) Papéis separados — fiscal, monitor, verificador. (2) Fotos e relatórios com hash SHA-256. (3) Auditoria com cadeia de hashes — qualquer alteração quebra a cadeia. (4) Bloqueio após 5 tentativas. (5) HTTPS, CSP, cookies seguros. (6) Relatórios verificados são imutáveis.",
                 "Security: (1) Separate roles — monitor, observer, verifier. (2) Photos and reports carry SHA-256 hashes. (3) Hash-chained audit log — any tampering breaks the chain and is shown. (4) Lock-out after 5 failed logins. (5) HTTPS, CSP, secure cookies. (6) Verified reports are immutable.",
                 "Keamanan: (1) Peran terpisah — fiskal, pemantau, verifikator. (2) Foto & laporan ber-hash SHA-256. (3) Log audit berantai hash — perubahan apa pun memutus rantai. (4) Kunci login setelah 5 gagal. (5) HTTPS, CSP, cookie aman. (6) Laporan terverifikasi tak dapat diubah."),
    "roles": ("Papél: FISKÁL hatama dadus ba sentru ne'ebé atribui. MONITÓR (ez. MDI, nain-partidu) haree dadus diretu, komparasaun, hasai CSV — la bele muda. VERIFIKADÓR/ADMIN verifika relatóriu, rezolve konflitu, haree audit.",
              "Papéis: FISCAL introduz dados dos centros atribuídos. MONITOR (ex. MDI, dono de partido) vê dados em direto, comparações e exporta CSV — sem editar. VERIFICADOR/ADMIN verifica relatórios, resolve conflitos e vê a auditoria.",
              "Roles: MONITOR (fiskal) enters data for assigned centres. OBSERVER (e.g. MDI, party owners) views live data, comparisons and exports CSV — read-only. VERIFIER/ADMIN verifies reports, resolves conflicts and reads the audit log.",
              "Peran: FISKAL mengisi data pusat yang ditugaskan. PEMANTAU (mis. MDI, pemilik partai) melihat data langsung, perbandingan, ekspor CSV — hanya baca. VERIFIKATOR/ADMIN memverifikasi laporan, menyelesaikan konflik, melihat audit."),
    "conflict": ("Se fiskál oioin hatama númeru la hanesan ba sentru ida, estadu 'konflitu': sentru ne'e la konta to'o admin verifika. Se relatóriu rua ka liu hanesan = 'konsensu'. Agora iha %(n)s konflitu.",
                 "Se vários fiscais registarem números diferentes, o estado é 'conflito': o centro não conta até o admin verificar. Dois ou mais iguais = 'consenso'. Há %(n)s conflitos.",
                 "If monitors enter different numbers for a centre it becomes a 'conflict' and is excluded until an admin verifies. Two or more identical = 'consensus'. There are %(n)s conflicts now.",
                 "Jika fiskal memasukkan angka berbeda untuk satu pusat, statusnya 'konflik' dan tidak dihitung sampai admin memverifikasi. Dua atau lebih sama = 'konsensus'. Saat ini ada %(n)s konflik."),
    "verify": ("Admin haree relatóriu ho foto, kompara ho fiskál seluk, depois 'Verifika' ka 'Rejeita' ho razaun. Relatóriu verifikadu prevalese no la bele muda.",
               "O admin vê o relatório e as fotos, compara com outros fiscais e 'Verifica' ou 'Rejeita' com motivo. O verificado prevalece e fica bloqueado.",
               "An admin reviews the report and photos, compares with other monitors, then 'Verify' or 'Reject' with a reason. Verified reports prevail and are locked.",
               "Admin memeriksa laporan dan foto, membandingkan dengan fiskal lain, lalu 'Verifikasi' atau 'Tolak' beserta alasan. Laporan terverifikasi diutamakan dan terkunci."),
    "invalid": ("Votu brankus: %(blank)s · votu nulu: %(invalid)s (husi sentru %(rep)s ne'ebé relata).",
                "Votos em branco: %(blank)s · nulos: %(invalid)s (de %(rep)s centros reportados).",
                "Blank votes: %(blank)s · invalid: %(invalid)s (from %(rep)s reporting centres).",
                "Suara kosong: %(blank)s · tidak sah: %(invalid)s (dari %(rep)s pusat yang melapor)."),
    "language": ("Troka lian iha menu leten-sorin los (Tetun, Português, English, Indonesia). Ha'u mós hatene lian 4 ne'e.",
                 "Mude o idioma no menu superior (Tetun, Português, English, Indonesia). Também entendo estes 4 idiomas.",
                 "Switch language in the top menu (Tetun, Português, English, Indonesia). I understand all four too.",
                 "Ganti bahasa di menu atas (Tetun, Português, English, Indonesia). Saya juga paham keempatnya."),
    "help": ("Ha'u bele responde: 'sé lidera', 'partisipasaun', 'progresu', 'rezultadu [munisípiu]', '[partidu]', 'konflitu', 'seguransa', 'oinsá hatama dadus', 'foto', 'papél'.",
             "Posso responder: 'quem lidera', 'participação', 'progresso', 'resultados [município]', '[partido]', 'conflitos', 'segurança', 'como introduzir dados', 'foto', 'papéis'.",
             "I can answer: 'who leads', 'turnout', 'progress', 'results [municipality]', '[party]', 'conflicts', 'security', 'how to enter data', 'photo', 'roles'.",
             "Saya bisa menjawab: 'siapa unggul', 'partisipasi', 'kemajuan', 'hasil [kabupaten]', '[partai]', 'konflik', 'keamanan', 'cara input data', 'foto', 'peran'."),
    "unknown": ("Ha'u la komprende. Koko: 'sé lidera?', 'rezultadu Baucau', 'partisipasaun', 'seguransa' ka 'ajuda'.",
                "Não percebi. Tente: 'quem lidera?', 'resultados Baucau', 'participação', 'segurança' ou 'ajuda'.",
                "I didn't get that. Try: 'who leads?', 'results Baucau', 'turnout', 'security' or 'help'.",
                "Saya kurang paham. Coba: 'siapa unggul?', 'hasil Baucau', 'partisipasi', 'keamanan' atau 'bantuan'."),
    "no_access": ("Ita-nia papél la iha asesu ba dadus rezultadu. Ha'u bele ajuda de'it kona-ba oinsá uza sistema.",
                  "O seu papel não tem acesso aos resultados. Só posso ajudar a usar o sistema.",
                  "Your role has no access to results data. I can only help with how to use the system.",
                  "Peran Anda tidak punya akses ke data hasil. Saya hanya bisa membantu cara memakai sistem."),
    "no_results": ("Seidauk iha rezultadu ne'ebé kontadu.", "Ainda não há resultados contados.",
                   "No counted results yet.", "Belum ada hasil yang dihitung."),
    "leader": ("Agora lidera: %(top)s ho %(share)s%% (%(votes)s votu). Segundu: %(second)s ho %(share2)s%%. Sentru relata: %(rep)s/%(tot)s (%(prog)s%%).",
               "Lidera: %(top)s com %(share)s%% (%(votes)s votos). Segundo: %(second)s com %(share2)s%%. Centros reportados: %(rep)s/%(tot)s (%(prog)s%%).",
               "Leading: %(top)s with %(share)s%% (%(votes)s votes). Second: %(second)s with %(share2)s%%. Centres reporting: %(rep)s/%(tot)s (%(prog)s%%).",
               "Unggul: %(top)s dengan %(share)s%% (%(votes)s suara). Kedua: %(second)s dengan %(share2)s%%. Pusat melapor: %(rep)s/%(tot)s (%(prog)s%%)."),
    "turnout": ("Partisipasaun nasionál: %(t)s%% (%(v)s husi %(r)s eleitór iha sentru ne'ebé relata).",
                "Participação nacional: %(t)s%% (%(v)s de %(r)s eleitores nos centros reportados).",
                "National turnout: %(t)s%% (%(v)s of %(r)s voters in reporting centres).",
                "Partisipasi nasional: %(t)s%% (%(v)s dari %(r)s pemilih di pusat yang melapor)."),
    "progress": ("Progresu: sentru %(rep)s husi %(tot)s relata (%(prog)s%%). Verifikadu: %(ver)s · konsensu: %(con)s · provizóriu: %(pro)s · konflitu: %(cf)s.",
                 "Progresso: %(rep)s de %(tot)s centros (%(prog)s%%). Verificados: %(ver)s · consenso: %(con)s · provisórios: %(pro)s · conflitos: %(cf)s.",
                 "Progress: %(rep)s of %(tot)s centres (%(prog)s%%). Verified: %(ver)s · consensus: %(con)s · provisional: %(pro)s · conflicts: %(cf)s.",
                 "Kemajuan: %(rep)s dari %(tot)s pusat (%(prog)s%%). Terverifikasi: %(ver)s · konsensus: %(con)s · sementara: %(pro)s · konflik: %(cf)s."),
    "region": ("%(name)s: sentru %(rep)s/%(tot)s · partisipasaun %(t)s%% · lidera %(top)s (%(share)s%%). Seluk: %(rest)s.",
               "%(name)s: centros %(rep)s/%(tot)s · participação %(t)s%% · lidera %(top)s (%(share)s%%). Outros: %(rest)s.",
               "%(name)s: centres %(rep)s/%(tot)s · turnout %(t)s%% · leader %(top)s (%(share)s%%). Others: %(rest)s.",
               "%(name)s: pusat %(rep)s/%(tot)s · partisipasi %(t)s%% · unggul %(top)s (%(share)s%%). Lainnya: %(rest)s."),
    "party": ("%(name)s: %(votes)s votu (%(share)s%% nasionál), pozisaun #%(pos)s. Munisípiu forte liu: %(best)s (%(bshare)s%%).",
              "%(name)s: %(votes)s votos (%(share)s%% nacional), posição #%(pos)s. Melhor município: %(best)s (%(bshare)s%%).",
              "%(name)s: %(votes)s votes (%(share)s%% nationally), rank #%(pos)s. Strongest municipality: %(best)s (%(bshare)s%%).",
              "%(name)s: %(votes)s suara (%(share)s%% nasional), peringkat #%(pos)s. Kabupaten terkuat: %(best)s (%(bshare)s%%)."),
    "total": ("Total votu válidu: %(v)s · votu brankus: %(b)s · nulu: %(i)s · eleitór ne'ebé vota: %(voted)s.",
              "Votos válidos: %(v)s · brancos: %(b)s · nulos: %(i)s · votantes: %(voted)s.",
              "Valid votes: %(v)s · blank: %(b)s · invalid: %(i)s · voters: %(voted)s.",
              "Suara sah: %(v)s · kosong: %(b)s · tidak sah: %(i)s · pemilih: %(voted)s."),
}

DATA_INTENTS = {"leader", "turnout", "progress", "total", "invalid", "conflict", "region", "party"}


def _t(key, lang):
    return R[key][_ORDER.index(lang) if lang in _ORDER else 0]


def _fmt(n):
    return f"{n:,}".replace(",", ".")


def detect(text):
    t = " " + norm(text) + " "
    scores = {}
    for intent, kws in INTENTS.items():
        sc = 0
        for kw in kws:
            k = norm(kw).strip()
            if k and (f" {k} " in t or (len(k) > 4 and k in t)):
                sc += 1 + len(k) / 20
        if sc:
            scores[intent] = sc
    return scores


def answer(text, lang, user_profile, election):
    t = norm(text)
    can_data = bool(user_profile and user_profile.can_monitor)
    snap = build_snapshot(election) if (can_data and election) else None

    # Entidade spesífiku (munisípiu/partidu) -> prioridade ba dadus
    if snap and snap["national"]["valid"] >= 0:
        names = {norm(m["name"]).strip(): m for m in snap["municipalities"]}
        for key, m in sorted(names.items(), key=lambda kv: -len(kv[0])):
            if key and re.search(rf"\b{re.escape(key)}\b", t):
                return _region_answer(m, snap, lang)
        for c in snap["contestants"]:
            keys = {norm(c["short"]).strip(), norm(c["name"]).strip()}
            if any(k and re.search(rf"\b{re.escape(k)}\b", t) for k in keys):
                return _party_answer(c, snap, lang)

    scores = detect(text)
    if not scores:
        return _t("unknown", lang)
    intent = max(scores, key=scores.get)

    if intent in DATA_INTENTS:
        if not snap:
            return _t("no_access", lang)
        return _data_answer(intent, snap, lang)
    return _t(intent, lang)


def _name(snap, cid):
    for c in snap["contestants"]:
        if c["id"] == cid:
            return c["short"] if c["short"] else c["name"]
    return "?"


def _ranked(node, snap):
    return sorted(((int(k), v) for k, v in node["votes"].items()), key=lambda kv: -kv[1])


def _data_answer(intent, snap, lang):
    n = snap["national"]
    st = snap["states"]
    if intent == "conflict":
        return _t("conflict", lang) % {"n": st.get("conflict", 0)}
    if n["centres_reporting"] == 0 and intent != "progress":
        return _t("no_results", lang)
    if intent == "leader":
        r = _ranked(n, snap)
        if not r:
            return _t("no_results", lang)
        v = n["valid"] or 1
        second = r[1] if len(r) > 1 else (0, 0)
        return _t("leader", lang) % {
            "top": _name(snap, r[0][0]), "share": round(100 * r[0][1] / v, 2), "votes": _fmt(r[0][1]),
            "second": _name(snap, second[0]) if second[0] else "-", "share2": round(100 * second[1] / v, 2),
            "rep": n["centres_reporting"], "tot": n["centres_total"], "prog": n["progress"],
        }
    if intent == "turnout":
        reg = round(n["voted"] / n["turnout"] * 100) if n["turnout"] else 0
        return _t("turnout", lang) % {"t": n["turnout"], "v": _fmt(n["voted"]), "r": _fmt(reg)}
    if intent == "progress":
        return _t("progress", lang) % {
            "rep": n["centres_reporting"], "tot": n["centres_total"], "prog": n["progress"],
            "ver": st.get("verified", 0), "con": st.get("consensus", 0), "pro": st.get("provisional", 0),
            "cf": st.get("conflict", 0),
        }
    if intent == "invalid":
        return _t("invalid", lang) % {"blank": _fmt(n["blank"]), "invalid": _fmt(n["invalid"]),
                                        "rep": n["centres_reporting"]}
    if intent == "total":
        return _t("total", lang) % {"v": _fmt(n["valid"]), "b": _fmt(n["blank"]), "i": _fmt(n["invalid"]),
                                      "voted": _fmt(n["voted"])}
    return _t("unknown", lang)


def _region_answer(m, snap, lang):
    r = _ranked(m, snap)
    if not r:
        return _t("no_results", lang)
    v = m["valid"] or 1
    rest = ", ".join(f"{_name(snap, cid)} {round(100 * val / v, 1)}%" for cid, val in r[1:4]) or "-"
    return _t("region", lang) % {
        "name": m["name"], "rep": m["centres_reporting"], "tot": m["centres_total"], "t": m["turnout"],
        "top": _name(snap, r[0][0]), "share": round(100 * r[0][1] / v, 2), "rest": rest,
    }


def _party_answer(c, snap, lang):
    n = snap["national"]
    r = _ranked(n, snap)
    pos = next((i + 1 for i, (cid, _) in enumerate(r) if cid == c["id"]), "-")
    votes = n["votes"].get(str(c["id"]), 0)
    share = n["shares"].get(str(c["id"]), 0)
    best, bshare = "-", 0
    for m in snap["municipalities"]:
        s = m["shares"].get(str(c["id"]), 0)
        if s > bshare:
            best, bshare = m["name"], s
    return _t("party", lang) % {"name": f'{c["short"]} · {c["name"]}', "votes": _fmt(votes), "share": share,
                                 "pos": pos, "best": best, "bshare": bshare}
