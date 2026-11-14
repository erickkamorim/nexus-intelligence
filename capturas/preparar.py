# Monta um site de teste: página nova + api do site publicado + placar e agenda gerados agora.
import json, os, shutil, sys, urllib.request
from pathlib import Path
import psycopg
sys.path.insert(0, "src")
os.environ.setdefault("DATABASE_URL", "")
SITE = Path("teste_site"); (SITE / "api").mkdir(parents=True, exist_ok=True)
for f in Path("web").glob("*.html"): shutil.copy(f, SITE / f.name)
BASE = "https://erickkamorim.github.io/nexus-intelligence/api/"
for n in ["resumo", "series", "copom", "qualidade", "previsoes", "moedas"]:
    (SITE / "api" / n).write_bytes(urllib.request.urlopen(BASE + n, timeout=30).read())
with psycopg.connect(os.environ["DATABASE_URL"]) as c:
    r = c.execute(Path("sql/api/placar.sql").read_text(encoding="utf-8")).fetchone()[0]
import build_static
(SITE / "api" / "placar").write_text(json.dumps(r, default=build_static.serializar, ensure_ascii=False), encoding="utf-8")
(SITE / "api" / "agenda").write_text(json.dumps(build_static.montar_agenda(), ensure_ascii=False), encoding="utf-8")
print("placar:", json.dumps(r, default=str)[:1500])
