import asyncio
from playwright.async_api import async_playwright
OUT = "capturas/out/"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for nome, w, h, dpr, path, extra in [("d", 1440, 1000, 1, "/", None), ("d-recolhido", 1440, 1000, 1, "/", "recolher"),
                                             ("m", 390, 844, 2, "/", None), ("m-menu", 390, 844, 2, "/", "menu"),
                                             ("pares", 1440, 1000, 1, "/pares", None), ("credito", 1440, 1000, 1, "/credito", None),
                                             ("resultados", 1440, 1000, 1, "/resultados", None)]:
            pg = await b.new_page(viewport={"width": w, "height": h}, device_scale_factor=dpr)
            r = await pg.goto("http://127.0.0.1:3000" + path, wait_until="networkidle", timeout=120000)
            await pg.wait_for_timeout(1500)
            if extra == "recolher": await pg.click(".collapse-btn"); await pg.wait_for_timeout(500)
            if extra == "menu": await pg.click(".bn-item:last-child"); await pg.wait_for_timeout(500)
            print(nome, r.status, await pg.title(), flush=True)
            await pg.screenshot(path=f"{OUT}{nome}.png", full_page=(extra != "menu"))
        await b.close()
asyncio.run(main())
