from strategy.base_signal import BaseSignal
from utils.constants import Transaction, HAMTaskManifest, HAMStrengthData

class HeikenAshiMartingale(BaseSignal):
    
    sha_lt_length = 9
    sha_lt_type = 'RMA'
    hedge = 1
    
    def __init__(self, path):
        super().__init__(path)

    def __recur_fibo(self, n):
        if n <= 1:
            return n
        else:
            return(self.__recur_fibo(n-1) + self.__recur_fibo(n-2))

    def __get_fibo_based_on_count(self, qty_count, times) -> int:
        fib = [self.__recur_fibo(i) for i in range(25)][2:]
        try:
            return fib[qty_count] * times
        except ValueError:
            return times
        
    def calculate_signal(self, symbol, analysis, analysis_time, mt5adapter, times):
        print(f"\n╔═══════════════════════════════════════════╗")
        print(f"║  🎯 HAM SIGNAL CALCULATION               ║")
        print(f"╠═══════════════════════════════════════════╣")
        print(f"║  Symbol: {symbol:<31} ║")
        print(f"║  Hedge: {times:<32} ║")
        print(f"╚═══════════════════════════════════════════╝")
        
        buy_profit = 0
        buy_volume = 0
        buy_count = 0
        buy_first_profit = 0
        buy_first_volume = 0
        buy_last_profit = 0
        buy_last_volume = 0
        sell_profit = 0
        sell_volume = 0
        sell_count = 0
        sell_first_profit = 0
        sell_first_volume = 0
        sell_last_profit = 0
        sell_last_volume = 0
        self.hedge = times
        buy_status = Transaction.DO_NOTHING
        sell_status = Transaction.DO_NOTHING
        buy_position = mt5adapter.fetch_buy_position_details(symbol = symbol)
        sell_position = mt5adapter.fetch_sell_position_details(symbol = symbol)

        print(f"\n├─ 📊 POSITION STATUS ─────────────────────┤")
        if buy_position != -1:
            buy_profit = buy_position['profit']
            buy_volume = buy_position['volume']
            buy_first_profit = buy_position['first_profit']
            buy_first_volume = buy_position['first_volume']
            buy_last_profit = buy_position['last_profit']
            buy_last_volume = buy_position['last_volume']
            buy_count = buy_position['count']
            profit_emoji = "🟢" if buy_profit > 0 else "🔴" if buy_profit < 0 else "⚪"
            print(f"│  {profit_emoji} BUY: Vol={buy_volume:.2f} | P/L={buy_profit:.2f} | Cnt={buy_count}")
        else:
            print(f"│  ⚪ BUY: No open position")

        if sell_position != -1:
            sell_profit = sell_position['profit']
            sell_volume = sell_position['volume']
            sell_first_profit = sell_position['first_profit']
            sell_first_volume = sell_position['first_volume']
            sell_last_profit = sell_position['last_profit']
            sell_last_volume = sell_position['last_volume']
            sell_count = sell_position['count']
            profit_emoji = "🟢" if sell_profit > 0 else "🔴" if sell_profit < 0 else "⚪"
            print(f"│  {profit_emoji} SELL: Vol={sell_volume:.2f} | P/L={sell_profit:.2f} | Cnt={sell_count}")
        else:
            print(f"│  ⚪ SELL: No open position")
        print(f"└───────────────────────────────────────────┘\n")

        lt_buy_power = 0
        ct_buy_power = 0
        lt_sell_power = 0
        ct_sell_power = 0
        ct_power_list = []
        lt_sha_power_list = []
        crossover = []

        sha_threshold = 0

        for key, value in analysis.items():
            # Logic for lt values
            sha_LT = 0
            if (value['lt_sha_diff']/(value['lt_sha_high'] - value['lt_sha_low'])) >= sha_threshold:
                lt_buy_power += 1
                lt_sha_power_list.append(1)
                sha_LT = 1
            else:
                lt_sell_power += 1
                lt_sha_power_list.append(0)
                sha_LT = 0
            
            # Logic for ct values
            if (value['ct_p_diff']/(value['ct_p_high'] - value['ct_p_low'])) >= sha_threshold:
                ct_buy_power += 1
                ct_power_list.append(1)
            else:
                ct_sell_power += 1
                ct_power_list.append(0)
            
            if (sha_LT == 1):
                if value['ct_p_low'] >= value['lt_sha_high']:
                    crossover.append(3)
                elif value['ct_p_high'] <= value['lt_sha_low']:
                    crossover.append(1)
                else:
                    crossover.append(2)
            elif (sha_LT == 0):
                if value['ct_p_high'] <= value['lt_sha_low']:
                    crossover.append(-3)
                elif value['ct_p_low'] >= value['lt_sha_high']:
                    crossover.append(-1)
                else:
                    crossover.append(-2)

        print(f"├─ 🔬 POWER ANALYSIS ──────────────────────┤")
        print(f"│  📈 LT Buy Power: {lt_buy_power} | LT Sell Power: {lt_sell_power}")
        print(f"│  📊 CT Buy Power: {ct_buy_power} | CT Sell Power: {ct_sell_power}")
        print(f"│  🎲 Crossover[0]: {crossover[0] if crossover else 'N/A'}")
        print(f"│  📋 LT SHA List: {lt_sha_power_list[:3]}...")
        print(f"│  📋 CT Power List: {ct_power_list[:3]}...")
        print(f"└───────────────────────────────────────────┘\n")

        if (buy_count == 0) and (sell_count == 0):
            if (lt_sha_power_list[0] == 1) and (crossover[0] == 3):
                buy_status = Transaction.BUY
            elif (lt_sha_power_list[0] == 0) and (crossover[0] == -3):
                sell_status = Transaction.SELL
        
        elif (buy_count > 0) and (sell_count == 0):
            if buy_profit > self.hedge:
                buy_status = Transaction.CLOSE_BUY
                sell_status = Transaction.DO_NOTHING
            else:
                if (crossover[0] == -1) or (crossover[0] == -2) or (crossover[0] == -3) or (crossover[0] == 1):
                    buy_status = Transaction.CLOSE_BUY
                    sell_status = Transaction.DO_NOTHING
                elif buy_first_profit < -(self.__get_fibo_based_on_count(buy_count, times) ** 3):
                    buy_status = Transaction.BUY_WITH_SPECIFIC_VOLUME
                    sell_status = Transaction.DO_NOTHING
                else:
                    buy_status = Transaction.DO_NOTHING
                    sell_status = Transaction.DO_NOTHING
        
        elif (buy_count == 0) and (sell_count > 0):
            if sell_profit > self.hedge:
                sell_status = Transaction.CLOSE_SELL
                buy_status = Transaction.DO_NOTHING
            else:
                if (crossover[0] == -1) or (crossover[0] == 1) or (crossover[0] == 2) or (crossover[0] == 3):
                    buy_status = Transaction.DO_NOTHING
                    sell_status = Transaction.CLOSE_SELL
                elif sell_first_profit < -(self.__get_fibo_based_on_count(sell_count, times) ** 3):
                    sell_status = Transaction.SELL_WITH_SPECIFIC_VOLUME
                    buy_status = Transaction.DO_NOTHING
                else:
                    buy_status = Transaction.DO_NOTHING
                    sell_status = Transaction.DO_NOTHING

        # Log final decision
        print(f"╔═══════════════════════════════════════════╗")
        print(f"║  ⚡ TRADING DECISION                      ║")
        print(f"╠═══════════════════════════════════════════╣")
        buy_emoji = "🟢" if buy_status == Transaction.BUY else "🔴" if buy_status == Transaction.CLOSE_BUY else "➕" if buy_status == Transaction.BUY_WITH_SPECIFIC_VOLUME else "⏸️"
        sell_emoji = "🔴" if sell_status == Transaction.SELL else "🟢" if sell_status == Transaction.CLOSE_SELL else "➕" if sell_status == Transaction.SELL_WITH_SPECIFIC_VOLUME else "⏸️"
        print(f"║  {buy_emoji} BUY:  {str(buy_status.name):<31} ║")
        print(f"║  {sell_emoji} SELL: {str(sell_status.name):<31} ║")
        print(f"╚═══════════════════════════════════════════╝\n")

        return (
            HAMStrengthData(
                lt_buy_power = lt_buy_power,
                ct_buy_power = ct_buy_power,
                lt_sell_power = lt_sell_power,
                ct_sell_power = ct_sell_power,
                ct_power_list = ct_power_list,
                lt_sha_power_list = lt_sha_power_list,
            ),
            HAMTaskManifest(
                buy_volume=buy_volume,
                buy_profit=buy_profit,
                buy_status=buy_status,
                buy_count=buy_count,
                buy_first_profit=buy_first_profit,
                buy_first_volume=buy_first_volume,
                buy_last_profit=buy_last_profit,
                buy_last_volume=buy_last_volume,
                sell_volume=sell_volume,
                sell_profit=sell_profit,
                sell_status=sell_status,
                sell_count=sell_count,
                sell_first_profit=sell_first_profit,
                sell_first_volume=sell_first_volume,
                sell_last_profit=sell_last_profit,
                sell_last_volume=sell_last_volume,
            ),
        )
                
    def get_signal(self, mt5adapter, symbol, path, times):
        print(f"\n{'='*50}")
        print(f"🚀 HAM STRATEGY - {symbol}")
        print(f"{'='*50}")
        print(f"⏰ Loading historical data...")
        
        self.data_list = self.load_data(symbol, path)

        ct_data = self.data_list[2]
        lt_data = self.data_list[2]
        
        print(f"✅ Data loaded: CT={len(ct_data)} bars | LT={len(lt_data)} bars")
        print(f"🔧 Computing SHA indicators...")

        lt_sha = self.smoothed_heiken_ashi_v3(df = lt_data, smooth_length=self.sha_lt_length, smooth_ma_type=self.sha_lt_type, after_smooth_length=self.sha_lt_length, after_smooth_ma_type=self.sha_lt_type)

        print(f"✅ SHA computed: LT(len={self.sha_lt_length},type={self.sha_lt_type})")
        print(f"📊 Building analysis dataset...\n")

        analysis = {}
        analysis_time = {}
        analysis_time['ct_time'] = str(ct_data.index[Transaction.LAST_VALUE.value])
        analysis_time['lt_time'] = str(lt_data.index[Transaction.LAST_VALUE.value])
        
        print(f"├─ ⏱️  TIMESTAMPS ─────────────────────────┤")
        print(f"│  CT: {analysis_time['ct_time']}")
        print(f"│  LT: {analysis_time['lt_time']}")
        print(f"└───────────────────────────────────────────┘\n")
        
        datasets = {
            "ct_p": ct_data,
            "lt_p": lt_data,
            "lt_sha": lt_sha,
        }

        for i, v in enumerate(range(-1, -8, -1)):
            analysis[str(i)] = {}
            for prefix, df in datasets.items():
                analysis[str(i)][f"{prefix}_open"] = df["Open"].iloc[v]
                analysis[str(i)][f"{prefix}_high"] = df["High"].iloc[v]
                analysis[str(i)][f"{prefix}_low"] = df["Low"].iloc[v]
                analysis[str(i)][f"{prefix}_close"] = df["Close"].iloc[v]
                analysis[str(i)][f"{prefix}_diff"] = df["Close"].iloc[v] - df["Open"].iloc[v]
                analysis[str(i)][f"{prefix}_center"] = (
                    df["Open"].iloc[v] + df["High"].iloc[v] +
                    df["Low"].iloc[v] + df["Close"].iloc[v]
                ) / 4.0

        return self.calculate_signal(symbol, analysis, analysis_time, mt5adapter, times)