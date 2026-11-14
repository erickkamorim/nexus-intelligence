import asyncio
from playwright.async_api import async_playwright
BASE = "https://erickkamorim.github.io/nexus-intelligence/"
OUT = "capturas/out/"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1366, "height": 768}, device_scale_factor=2, timezone_id="America/Sao_Paulo")
        await ctx.add_init_script("try{localStorage.setItem('nexus-menu','recolhido')}catch(e){}")
        pg = await ctx.new_page(); erros = []
        pg.on("pageerror", lambda e: erros.append(str(e)))
        await pg.goto(BASE + "?v=2", wait_until="networkidle"); await pg.wait_for_timeout(4000)
        print("tem comparador:", await pg.evaluate("!!document.getElementById('comparar')"),
              "agenda visível:", await pg.evaluate("!document.getElementById('agenda').hidden"),
              "placar visível:", await pg.evaluate("!document.getElementById('placar').hidden"))
        await pg.evaluate("window.scrollTo(0, 230)"); await pg.wait_for_timeout(1500)
        await pg.screenshot(path=OUT + "visao-geral.png")
        await pg.evaluate("document.querySelectorAll('.reveal').forEach(e => e.classList.add('in'))")
        for sel, arq in [("#comparar .card", "comparador.png"), ("#placar", "placar.png")]:
            e = await pg.query_selector(sel); await e.scroll_into_view_if_needed(); await pg.wait_for_timeout(2500)
            await e.screenshot(path=OUT + arq)
        print("erros:", erros)
        await b.close()
asyncio.run(main())
