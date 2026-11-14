import asyncio, json
from playwright.async_api import async_playwright
OUT = "capturas/out/"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for nome, kw in [("d", dict(viewport={"width": 1440, "height": 900}, device_scale_factor=1)),
                         ("m", dict(**p.devices["iPhone 13"]))]:
            ctx = await b.new_context(**kw, accept_downloads=True, timezone_id="America/Sao_Paulo")
            pg = await ctx.new_page()
            erros = []
            pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.on("console", lambda m: m.type == "error" and erros.append(m.text))
            await pg.goto("http://localhost:8000/", wait_until="networkidle"); await pg.wait_for_timeout(3000)
            await pg.evaluate("document.querySelectorAll('.reveal').forEach(e => e.classList.add('in'))")
            print(nome, "erros:", erros)
            for sel, arq in [("#visao", "visao"), ("#comparar", "comparar"), ("#placar", "placar")]:
                e = await pg.query_selector(sel)
                await e.scroll_into_view_if_needed(); await pg.wait_for_timeout(1800)
                await e.screenshot(path=f"{OUT}{nome}_{arq}.png")
            if nome == "d":
                # modo R$ 100, seleção e CSV
                await pg.click('#cmp-modo button[data-modo="base100"]'); await pg.wait_for_timeout(1800)
                e = await pg.query_selector("#comparar"); await e.screenshot(path=f"{OUT}d_comparar_r100.png")
                async with pg.expect_download() as dl:
                    await pg.click("#cmp-csv")
                d = await dl.value; await d.save_as(OUT + "teste.csv"); print("csv:", d.suggested_filename)
                await pg.click('#cmp-series .cmp-chip[data-id="dolar"]'); await pg.wait_for_timeout(600)
                await pg.select_option("#cmp-de", index=0); await pg.wait_for_timeout(800)
                e = await pg.query_selector("#comparar"); await e.screenshot(path=f"{OUT}d_comparar_r100b.png")
                print("menu itens:", await pg.evaluate("[...document.querySelectorAll('#menu a')].length"))
            else:
                a = await pg.evaluate("(() => { const r = document.querySelector('aside').getBoundingClientRect(); return [r.left, r.right, innerWidth]; })()")
                print("menu celular:", a, "rolagem lateral:", await pg.evaluate("document.documentElement.scrollWidth"))
                await pg.screenshot(path=f"{OUT}m_menu.png")
            print(nome, "erros finais:", erros)
            await ctx.close()
        await b.close()
asyncio.run(main())
