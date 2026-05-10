import asyncio
from loguru import logger
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import OrderArgs
from config import config
from gas_manager import GasManager

class PolymarketTrader:
    def __init__(self):
        self.client = self._init_client()
        self.gas_manager = GasManager()
        self.active_orders = {}
        
    def _init_client(self):
        if not config.WALLET_PRIVATE_KEY:
            logger.warning("Wallet private key not set. Running in limited mode.")
            return None
            
        try:
            pk = config.WALLET_PRIVATE_KEY.replace("0x", "")
            client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=POLYGON)
            client.set_api_creds({
                "key": config.POLY_API_KEY,
                "secret": config.POLY_API_SECRET,
                "passphrase": config.POLY_API_PASSPHRASE
            })
            return client
        except Exception as e:
            logger.error(f"Failed to initialize Polymarket client: {e}")
            return None

    async def get_orderbook(self, token_id: str):
        # In a real implementation, this would use the client to fetch the orderbook
        # For now, we mock it for the dry run
        await asyncio.sleep(0.1)
        return {
            "bids": [{"price": "0.48", "size": "1000"}],
            "asks": [{"price": "0.50", "size": "1000"}]
        }

    async def check_liquidity(self, orderbook: dict, target_size: float) -> bool:
        if not orderbook.get("asks") or not orderbook.get("bids"):
            return False
            
        best_ask_size = float(orderbook["asks"][0]["size"])
        
        # If target size is > 10% of best ask size, we need iceberg orders
        if target_size > best_ask_size * 0.1:
            logger.warning(f"Target size {target_size} exceeds 10% of L1 depth ({best_ask_size}). Iceberg order required.")
            return False # Simplified for now, would implement iceberg logic here
            
        return True

    async def execute_arbitrage(self, market_id: str, yes_token: str, no_token: str, yes_price: float, no_price: float):
        total_cost = yes_price + no_price
        expected_gross_profit = 1.0 - total_cost
        
        # 1. Check basic profitability
        if expected_gross_profit <= 0:
            return False
            
        # 2. Calculate trade size based on config
        trade_size = config.TRADE_AMOUNT_USD
        expected_net_profit = (expected_gross_profit * trade_size)
        
        # 3. Gas and cost filter
        gas_cost = self.gas_manager.get_gas_estimate_usd() * 2 # Buy YES and NO
        slippage_tolerance = config.HYPE_SLIPPAGE_TOLERANCE if "HYPE" in market_id else config.MAX_PRICE_IMPACT
        slippage_cost = trade_size * slippage_tolerance
        
        final_net_profit = expected_net_profit - gas_cost - slippage_cost
        
        if final_net_profit < config.MIN_PROFIT_USD:
            logger.debug(f"[{market_id}] Profit too low: ${final_net_profit:.3f} (Cost: ${total_cost:.3f}, Gas: ${gas_cost:.3f})")
            return False
            
        if not self.gas_manager.check_gas_viability(expected_net_profit):
            return False
            
        logger.info(f"🚀 [{market_id}] Arbitrage Opportunity Found! Expected Net Profit: ${final_net_profit:.3f}")
        
        if config.DRY_RUN:
            logger.info(f"🧪 [DRY RUN] Would execute buy for {market_id}. YES: {yes_price}, NO: {no_price}")
            return True
            
        # Real execution logic would go here
        # self.client.create_and_post_order(...)
        return True
