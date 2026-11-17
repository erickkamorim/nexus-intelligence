import asyncio
from playwright.async_api import async_playwright
URL = "https://bb-intelligence-git-identidade-azul-2112e4-erickamorim0111-6144.vercel.app"
OUT = "capturas/out/"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for nome, w, h, dpr, path in [("d", 1440, 1000, 1, "/"), ("m", 390, 844, 2, "/"), ("pares", 1440, 1000, 1, "/pares"), ("credito", 1440, 1000, 1, "/credito")]:
            pg = await b.new_page(viewport={"width": w, "height": h}, device_scale_factor=dpr)
            r = await pg.goto(URL + path, wait_until="networkidle", timeout=120000)
            await pg.wait_for_timeout(4000)
            print(nome, r.status, await pg.title())
            await pg.screenshot(path=f"{OUT}{nome}.png", full_page=True)
        await b.close()
asyncio.run(main())
