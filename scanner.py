import asyncio
import ccxt.async_support as ccxt

async def test():
    # 尝试三个不同的 API 接入点
    nodes = ['https://api.binance.com', 'https://api1.binance.com', 'https://api3.binance.com']
    for node in nodes:
        ex = ccxt.binance({'urls': {'api': {'public': f'{node}/api/v3'}}})
        try:
            print(f"测试节点 {node} ...")
            res = await ex.fetch_status()
            print(f"✅ 成功！状态: {res['status']}")
            await ex.close()
            return
        except Exception as e:
            print(f"❌ 失败: {e}")
            await ex.close()

asyncio.run(test())
