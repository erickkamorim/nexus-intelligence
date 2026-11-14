# Teste no celular: o menu flutuante acompanha a rolagem e cabe na tela?
import asyncio
from playwright.async_api import async_playwright
BASE = "https://erickkamorim.github.io/nexus-intelligence/"
OUT = "capturas/out/"
async def rodar(p, b, html, rotulo):
    ctx = await b.new_context(**p.devices["iPhone 13"])
    pg = await ctx.new_page()
    if html:
        for u in (BASE, BASE + "index.html"):
            await pg.route(u, lambda r: r.fulfill(body=html, content_type="text/html; charset=utf-8"))
    await pg.goto(BASE, wait_until="networkidle"); await pg.wait_for_timeout(3500)
    alt = await pg.evaluate("document.body.scrollHeight")
    for i, y in enumerate([0, 0.2, 0.4, 0.6, 0.8, 1.0]):
        await pg.evaluate(f"window.scrollTo(0, {int(alt*y)})"); await pg.wait_for_timeout(900)
        r = await pg.evaluate("""() => {
          const a = document.querySelector('aside').getBoundingClientRect();
          const on = document.querySelector('#menu a.on');
          return {aside: [Math.round(a.left), Math.round(a.right), Math.round(a.top), Math.round(a.bottom)],
                  tela: [innerWidth, innerHeight], ativo: on ? on.getAttribute('href') : null,
                  status_visivel: getComputedStyle(document.querySelector('.side-status')).display};
        }""")
        print(rotulo, y, r, flush=True)
        await pg.screenshot(path=f"{OUT}{rotulo}_mob_{i}.png")
    # clicar no menu
    for sec in ["juros", "cambio", "dados"]:
        await pg.click(f'#menu a[href="#{sec}"]'); await pg.wait_for_timeout(1500)
        r = await pg.evaluate("s => [Math.round(document.querySelector('#'+s+' .sec-title').getBoundingClientRect().top), document.querySelector('#menu a.on')?.getAttribute('href')]", sec)
        print(rotulo, "clique", sec, r, flush=True)
    await ctx.close()
async def main():
    html = open("capturas/teste_index.html", encoding="utf-8").read()
    async with async_playwright() as p:
        b = await p.chromium.launch()
        await rodar(p, b, None, "antes")
        await rodar(p, b, html, "depois")
        await b.close()
asyncio.run(main())
