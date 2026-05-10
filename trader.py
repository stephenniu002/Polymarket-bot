import asyncio
import time
import json
import httpx
from loguru import logger
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import OrderArgs, OrderType
from config import config

class PolymarketTrader:
    def __init__(self):
        self.client = self._init_client()
        
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

    async def execute_directional_trade(self, coin: str, direction: str):
        """Execute a directional trade (YES or NO) based on Binance signal"""
        market_data = await self.get_current_market_tokens(coin)
        if not market_data:
            return False, 0.0
            
        target_token = market_data["yes_token"] if direction == "YES" else market_data["no_token"]
        
        # Fetch orderbook for the target token
        ob = await self.get_orderbook(target_token)
        
        if not ob.get("asks"):
            logger.warning(f"[{coin}] No liquidity for {direction} token")
            return False, 0.0
            
        best_ask = float(ob["asks"][0]["price"])
        
        # If the price is already too high (e.g., > 0.95), the market has fully priced it in
        if best_ask > 0.95:
            logger.info(f"[{coin}] {direction} price too high ({best_ask}). Market already priced in.")
            return False, 0.0
            
        trade_size = config.TRADE_AMOUNT_USD
        expected_profit = (1.0 - best_ask) * (trade_size / best_ask)
        
        logger.info(f"🚀 [{coin}] Snipe Opportunity! Buying {direction} at {best_ask}. Expected Profit: ${expected_profit:.2f}")
        
        if config.DRY_RUN:
            logger.info(f"🧪 [DRY RUN] Would execute BUY {direction} for {coin} at {best_ask}")
            return True, expected_profit
            
        # Real execution logic
        if self.client:
            try:
                order = OrderArgs(
                    token_id=target_token,
                    price=best_ask,
                    size=trade_size / best_ask,
                    side="BUY"
                )
                # Note: In a real production bot, you MUST include feeRateBps in the signature
                # as per the new Polymarket rules (Feb 2026).
                # The py-clob-client should handle this if updated to the latest version.
                signed_order = self.client.create_order(order)
                self.client.post_order(signed_order, OrderType.FOK)
                
                return True, expected_profit
            except Exception as e:
                logger.error(f"Error executing trade: {e}")
                
        return False, 0.0
