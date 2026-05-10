from web3 import Web3
from loguru import logger
from config import config

class GasManager:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(config.RPC_URL))
        self.matic_to_usd = 0.7 # Mock price, should be fetched dynamically in production

    def get_gas_estimate_usd(self, gas_limit: int = 300000) -> float:
        try:
            # EIP-1559 Gas calculation
            base_fee = self.w3.eth.get_block('latest')['baseFeePerGas']
            priority_fee = self.w3.eth.max_priority_fee
            
            # G_limit = Current Base Fee * 1.2 + Priority Fee
            max_fee_per_gas = int(base_fee * 1.2) + priority_fee
            
            total_gas_cost_wei = max_fee_per_gas * gas_limit
            total_gas_cost_matic = self.w3.from_wei(total_gas_cost_wei, 'ether')
            
            gas_cost_usd = float(total_gas_cost_matic) * self.matic_to_usd
            return gas_cost_usd
        except Exception as e:
            logger.error(f"Error estimating gas: {e}")
            return 0.05 # Fallback estimate

    def check_gas_viability(self, expected_gross_profit: float) -> bool:
        gas_cost_usd = self.get_gas_estimate_usd()
        
        if expected_gross_profit <= 0:
            return False
            
        gas_ratio = gas_cost_usd / expected_gross_profit
        
        if gas_ratio > config.MAX_GAS_FEE_RATIO:
            logger.warning(f"Gas ratio too high: {gas_ratio:.2%} (Cost: ${gas_cost_usd:.3f}, Profit: ${expected_gross_profit:.3f}). Entering Observation Mode.")
            return False
            
        return True
