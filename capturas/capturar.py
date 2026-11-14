# Tira as capturas de tela do NEXUS publicado (uso temporário).
import asyncio
from playwright.async_api import async_playwright
BASE = "https://erickkamorim.github.io/nexus-intelligence/"
OUT = "capturas/out/"

async def pagina(b, w, h, menu, url=BASE, dpr=2):
    ctx = await b.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr, color_scheme="dark")
    await ctx.add_init_script(f"try{{localStorage.setItem('nexus-menu','{menu}')}}catch(e){{}}")
    pg = await ctx.new_page()
    await pg.goto(url, wait_until="networkidle")
    await pg.wait_for_timeout(3500)
    return ctx, pg

async def secao(pg, sel, nome, extra=0):
    # posiciona a seção logo abaixo da faixa congelada
    await pg.evaluate("""([s, extra]) => {
      const el = document.querySelector(s);
      const faixa = document.getElementById('congelado');
      window.scrollTo(0, el.getBoundingClientRect().top + scrollY - 90 + extra);
    }""", [sel, extra])
    await pg.wait_for_timeout(500)
    await pg.evaluate("window.dispatchEvent(new Event('scroll'))")
    await pg.wait_for_timeout(2500)
    await pg.screenshot(path=OUT + nome)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        # menu aberto (capa)
        ctx, pg = await pagina(b, 1366, 768, "aberto")
        await pg.screenshot(path=OUT + "dashboard.png"); await ctx.close()
        # menu recolhido (padrão)
        ctx, pg = await pagina(b, 1366, 768, "recolhido")
        await pg.screenshot(path=OUT + "visao-geral.png")
        await secao(pg, "#juros", "juros.png")
        await secao(pg, "#inflacao", "inflacao.png")
        await secao(pg, "#cambio", "cambio.png")
        await secao(pg, "#previsoes", "previsoes.png")
        await secao(pg, "#dados", "qualidade.png")
        await ctx.close()
        ctx, pg = await pagina(b, 1366, 768, "recolhido", BASE + "metodologia.html")
        await pg.screenshot(path=OUT + "metodologia.png"); await ctx.close()
        # celular
        ctx, pg = await pagina(b, 375, 680, "recolhido", dpr=3)
        await pg.screenshot(path=OUT + "mobile.png"); await ctx.close()
        await b.close()

asyncio.run(main())
