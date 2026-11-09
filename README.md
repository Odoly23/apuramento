# Apuramentu Eleisaun Timor-Leste

Sistema Django ba apuramentu (tally) eleisaun **Prezidensiál + Parlamentu Nasionál**: fiskál hatama rezultadu husi
sentru votasaun ho prova foto; organizasaun (MDI, ONG, nain-partidu) haree diretu; verifikadór kontrola no audit.
Interface: **Tetun · Português · English · Bahasa Indonesia**.

> Dadus `seed_demo` hotu **fiktisiu** (partidu, kandidatu, rezultadu). La'ós rezultadu loloos.

## Dalan lais

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo --reset --password 'Troka-Password-10+'
python manage.py runserver
```
Tama iha http://localhost:8000 ho: `admin` / `verifikador` (verifikadór), `mdi` (monitór), `pau_nain` (nain-partidu),
`fiskal_dl_1` (fiskál Dili) — password hanesan ne'ebé ita define.

Teste: `python manage.py test` (22 teste).

## Papél
| Papél | Bele halo |
|---|---|
| **Fiskál** | Hatama/atualiza rezultadu + foto ba sentru ne'ebé atribui de'it |
| **Monitór** (MDI, ONG, nain-partidu) | Haree painel diretu, komparasaun, export CSV, relatóriu no foto — **la bele muda** |
| **Verifikadór/Admin** | Verifika/rejeita relatóriu, rezolve konflitu, haree audit log, admin Django |

## Funsionalidade
1. **Hatama dadus fiskál**: total votante, brankus, nulu, votu kada kandidatu/lista + 1–6 foto ata. Soma tenke los
   (validasaun iha browser no server), votante ≤ eleitór rejistadu, foto verifika konteúdu loloos (Pillow), SHA-256.
2. **Painel diretu** (atualiza 10s): progresu sentru, partisipasaun, votu, konflitu, mapa munisípiu, feed atividade.
3. **Komparasaun** tuir munisípiu / postu / suku: tabela bele sort, head-to-head partidu rua, lider kada rejiaun.
4. **Akurasia**: konsolidasaun ba sentru — *verifikadu* > *konsensu* (fiskál 2+ hanesan) > *provizóriu*;
   fiskál oioin la hanesan = *konflitu* (la konta to'o admin verifika). Alerta automátiku (partisipasaun >95%,
   nulu/brankus >10%, kandidatu >95%).
5. **Seguransa**: papél ketak, hash SHA-256 ba relatóriu + foto, verifika integridade molok verifika, audit log
   **korrente hash** (muda ida = korrente kuak, hatudu iha `/audit/`), relatóriu verifikadu bloke, login lock
   (5 tentativa/15 min), CSP, HSTS/cookie seguru bainhira `DJANGO_DEBUG=False`, foto la públiku (view proteje),
   `Cache-Control: no-store`, rate limit chat, export CSV protejidu husi formula injection.
6. **Asistente tanya-jawab** (ikon 💬): komprende lian 4; resposta husi dadus diretu (sé lidera, partisipasaun,
   rezultadu [munisípiu], [partidu], konflitu, progresu) no panduan sistema (oinsá hatama, foto, seguransa, papél).
   Baseia ba regra — la haruka dadus ba servisu externu.

## Produksaun
Define environment: `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`,
`DATABASE_URL=postgres://user:pass@host:5432/db` (instala `psycopg[binary]`), `MEDIA_ROOT` (disk seguru, backup).
Servi ho gunicorn + HTTPS reverse-proxy; `python manage.py collectstatic`. Iha PostgreSQL, **hasai permisaun
UPDATE/DELETE** husi tabela `eleisaun_auditlog` ba user aplikasaun hodi proteje audit log iha nivel database.
Troka cache ba Redis/Memcached bainhira iha prosesu barak (rate-limit no cache painel).

## Limite no passu tuir mai
Seidauk iha: 2FA (TOTP), notifikasaun, mapa jeográfiku (GeoJSON), import lista sentru husi CSV, tradusaun Tetun
nian kleur liu husi falante nativu (revee teksto iha `eleisaun/i18n.py` no `chatbot.py`). Sistema ida-ne'e ajuda
transparénsia, maibé rezultadu ofisiál sei depende de autoridade eleitorál.
