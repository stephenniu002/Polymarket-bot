import asyncio
import time
import json
import httpx
from loguru import logger
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import OrderArgs, OrderType
from config import config
from gas_manager import GasManager

class PolymarketTrader:
    def __init__(self):
        self.client = self._init_client()
        self.gas_manager = GasManager()
        self.active_orders = {}
        
    def _init_client(self):
        if not config.WALLET_PRIVATE_KEY or config.WALLET_PRIVATE_KEY == "your_wallet_private_key":
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

    async def get_current_market_tokens(self, coin: str):
        """Get the current 5m market tokens for a specific coin"""
        now = int(time.time())
        window_ts = now - (now % 300)
        slug = f"{coin.lower()}-updown-5m-{window_ts}"
        
        url = f"https://gamma-api.polymarket.com/events?slug={slug}"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=5.0)
                events = response.json()
                
                if events and len(events) > 0:
                    markets = events[0].get("markets", [])
                    if markets:
                        market = markets[0]
                        clob_token_ids = json.loads(market.get("clobTokenIds", "[]"))
                        if len(clob_token_ids) >= 2:
                            return {
                                "market_id": market.get("conditionId"),
                                "yes_token": clob_token_ids[0],
                                "no_token": clob_token_ids[1],
                                "title": events[0].get("title")
                            }
        except Exception as e:
            logger.error(f"Error fetching market tokens for {coin}: {e}")
            
        return None

    async def get_orderbook(self, token_id: str):
        """Fetch real orderbook from CLOB API"""
        url = f"https://clob.polymarket.com/book?token_id={token_id}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=5.0)
                return response.json()
        except Exception as e:
            logger.error(f"Error fetching orderbook for {token_id}: {e}")
            return {"bids": [], "asks": []}

    async def check_liquidity(self, orderbook: dict, target_size: float) -> bool:
        if not orderbook.get("asks"):
            return False
            
        best_ask_size = float(orderbook["asks"][0]["size"])
        
        # If target size is > 10% of best ask size, we need iceberg orders
        if target_size > best_ask_size * 0.1:
            logger.warning(f"Target size {target_size} exceeds 10% of L1 depth ({best_ask_size}). Iceberg order required.")
            return False # Simplified for now
            
        return True

    async def execute_arbitrage(self, coin: str):
        """Main arbitrage logic for a specific coin"""
        market_data = await self.get_current_market_tokens(coin)
        if not market_data:
            return False, 0.0
            
        yes_token = market_data["yes_token"]
        no_token = market_data["no_token"]
        
        # Fetch orderbooks concurrently
        yes_ob, no_ob = await asyncio.gather(
            self.get_orderbook(yes_token),
            self.get_orderbook(no_token)
        )
        
        if not yes_ob.get("asks") or not no_ob.get("asks"):
            return False, 0.0
            
        yes_price = float(yes_ob["asks"][0]["price"])
        no_price = float(no_ob["asks"][0]["price"])
        
        total_cost = yes_price + no_price
        expected_gross_profit = 1.0 - total_cost
        
        # 1. Check basic profitability
        if expected_gross_profit <= 0:
            return False, 0.0
            
        # 2. Calculate trade size based on config
        trade_size = config.TRADE_AMOUNT_USD
        expected_net_profit = (expected_gross_profit * trade_size)
        
        # 3. Gas and cost filter
        gas_cost = self.gas_manager.get_gas_estimate_usd() * 2 # Buy YES and NO
        slippage_tolerance = config.HYPE_SLIPPAGE_TOLERANCE if "HYPE" in coin else config.MAX_PRICE_IMPACT
        slippage_cost = trade_size * slippage_tolerance
        
        final_net_profit = expected_net_profit - gas_cost - slippage_cost
        
        if final_net_profit < config.MIN_PROFIT_USD:
            logger.debug(f"[{coin}] Profit too low: ${final_net_profit:.3f} (Cost: ${total_cost:.3f}, Gas: ${gas_cost:.3f})")
            return False, 0.0
            
        if not self.gas_manager.check_gas_viability(expected_net_profit):
            return False, 0.0
            
        logger.info(f"🚀 [{coin}] Arbitrage Opportunity Found! Expected Net Profit: ${final_net_profit:.3f}")
        
        if config.DRY_RUN:
            logger.info(f"🧪 [DRY RUN] Would execute buy for {coin}. YES: {yes_price}, NO: {no_price}")
            return True, final_net_profit
            
        # Real execution logic
        if self.client:
            try:
                # Place YES order
                yes_order = OrderArgs(
                    token_id=yes_token,
                    price=yes_price,
                    size=trade_size / yes_price,
                    side="BUY"
                )
                signed_yes = self.client.create_order(yes_order)
                self.client.post_order(signed_yes, OrderType.FOK)
                
                # Place NO order
                no_order = OrderArgs(
                    token_id=no_token,
                    price=no_price,
                    size=trade_size / no_price,
                    side="BUY"
                )
                signed_no = self.client.create_order(no_order)
                self.client.post_order(signed_no, OrderType.FOK)
                
                return True, final_net_profit
            except Exception as e:
                logger.error(f"Error executing trade: {e}")
                
        return False, 0.0
