"""
测试 Playwright 能否正确识别 Polymarket 下单界面元素
"""
import asyncio
from playwright.async_api import async_playwright

async def test_ui():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        print("打开 Polymarket BTC 5分钟市场...")
        await page.goto('https://polymarket.com/crypto/5M')
        await page.wait_for_load_state('networkidle')
        
        # 查找市场链接
        btc_links = await page.locator('text="Bitcoin Up or Down"').all()
        print(f"找到 BTC 市场链接: {len(btc_links)} 个")
        
        if btc_links:
            await btc_links[0].click()
            await page.wait_for_load_state('networkidle')
            print(f"当前 URL: {page.url}")
            
            # 截图
            await page.screenshot(path='/home/ubuntu/Polymarket-bot/test_ui.png')
            print("截图已保存: test_ui.png")
            
            # 查找下单相关元素
            yes_btn = page.locator('button:has-text("Yes"), button:has-text("Up")')
            no_btn = page.locator('button:has-text("No"), button:has-text("Down")')
            buy_btn = page.locator('button:has-text("Buy")')
            amount_input = page.locator('input[placeholder="0"], input[type="number"]')
            
            print(f"Yes/Up 按钮: {await yes_btn.count()} 个")
            print(f"No/Down 按钮: {await no_btn.count()} 个")
            print(f"Buy 按钮: {await buy_btn.count()} 个")
            print(f"金额输入框: {await amount_input.count()} 个")
        
        await browser.close()

asyncio.run(test_ui())
