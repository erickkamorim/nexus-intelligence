# Teste: clicar em cada item do menu e medir onde o título da seção para.
import asyncio
from playwright.async_api import async_playwright
BASE = "https://erickkamorim.github.io/nexus-intelligence/"
OUT = "capturas/out/"
async def rodar(b, html, rotulo, w, h):
    ctx = await b.new_context(viewport={"width": w, "height": h})
    pg = await ctx.new_page()
    if html:
        await pg.route(BASE, lambda r: r.fulfill(body=html, content_type="text/html; charset=utf-8"))
        await pg.route(BASE + "index.html", lambda r: r.fulfill(body=html, content_type="text/html; charset=utf-8"))
    await pg.goto(BASE, wait_until="networkidle"); await pg.wait_for_timeout(3500)
    for sec in ["juros", "inflacao", "cambio", "previsoes", "dados", "juros"]:
        await pg.click(f'#menu a[href="#{sec}"]'); await pg.wait_for_timeout(1800)
        r = await pg.evaluate("""s => {
          const t = document.querySelector('#'+s+' .sec-title').getBoundingClientRect().top;
          const c = document.getElementById('congelado');
          const fb = c.classList.contains('on') ? c.getBoundingClientRect().bottom : 0;
          return {titulo: Math.round(t), faixa_fim: Math.round(fb), folga: Math.round(t-fb)};
        }""", sec)
        print(rotulo, w, sec, r, flush=True)
        await pg.screenshot(path=f"{OUT}{rotulo}_{w}_{sec}.png")
    await ctx.close()
async def main():
    html = open("capturas/teste_index.html", encoding="utf-8").read()
    async with async_playwright() as p:
        b = await p.chromium.launch()
        await rodar(b, None, "antes", 1366, 768)
        await rodar(b, html, "depois", 1366, 768)
        await rodar(b, html, "depois", 1920, 1080)
        await rodar(b, html, "depois", 390, 800)
        await b.close()
asyncio.run(main())
