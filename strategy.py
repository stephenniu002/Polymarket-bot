import time

class TailStrategy:
    def __init__(self):
        self.prices = []
        self.active_trades = []  # 存放待判定的交易 [(触发价格, 触发时间), ...]

    def update_price(self, price):
        self.prices.append(price)
        if len(self.prices) > 600: # 扩大缓存，存10分钟数据
            self.prices.pop(0)

    def check_signal(self):
        if len(self.prices) < 300: return False
        
        window = self.prices[-300:] # 最近5分钟
        low = min(window)
        current = self.prices[-1]
        
        # 信号条件：跌得够深(接近5分新低)，且当前开始有勾头迹象
        distance_to_low = (current - low) / low
        if distance_to_low < 0.002: # 离最低点 0.2% 以内
            return True
        return False

    def process_pending_trades(self, current_price, current_time):
        """
        核心 V2 判定：检查之前的下注在 60 秒后是赚是亏
        """
        results = []
        # 遍历所有还没到 60 秒的交易
        for trade in self.active_trades[:]:
            entry_price, entry_time = trade
            
            # 如果时间到了 60 秒
            if current_time - entry_time >= 60:
                # 判定标准：收盘价是否比入场价高出 1% (模拟 100 倍赔率的获胜空间)
                rebound = (current_price - entry_price) / entry_price
                if rebound > 0.01: # 只要涨 1% 就算 100 倍暴利
                    results.append(1000) # $10 * 100
                else:
                    results.append(-10)  # 亏掉本金 $10
                self.active_trades.remove(trade)
        return results
