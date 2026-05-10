import time
from loguru import logger

class DirectionalStrategy:
    def __init__(self):
        # The threshold for price delta to trigger a trade (e.g., 0.02%)
        self.delta_threshold = 0.02
        
    def analyze(self, delta_percentage: float) -> str:
        """
        Analyzes the price delta and returns the predicted direction.
        Returns "YES" (Up), "NO" (Down), or "NEUTRAL" (No clear direction)
        """
        if delta_percentage > self.delta_threshold:
            return "YES"
        elif delta_percentage < -self.delta_threshold:
            return "NO"
        else:
            return "NEUTRAL"
            
    def get_time_to_close(self) -> int:
        """Returns seconds remaining until the current 5-minute window closes"""
        now = int(time.time())
        return 300 - (now % 300)
        
    def is_snipe_window(self) -> bool:
        """
        Returns True if we are in the T-15 to T-5 seconds window.
        This is the optimal time to place a trade based on Binance data.
        """
        ttc = self.get_time_to_close()
        return 5 <= ttc <= 15
