class Stats:
    def __init__(self):
        self.trades = 0
        self.balance = 0
        self.wins = 0

    def record(self, profit):
        self.trades += 1
        self.balance += profit
        if profit > 0:
            self.wins += 1

    def summary(self):
        win_rate = self.wins / self.trades if self.trades > 0 else 0
        # ROI 计算：总收益 / (总下注金额)
        roi = (self.balance / (self.trades * 10)) + 1 if self.trades > 0 else 0
        return {
            "trades": self.trades,
            "win_rate": win_rate,
            "balance": self.balance,
            "roi": roi
        }
