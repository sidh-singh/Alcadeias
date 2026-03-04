//+------------------------------------------------------------------+
//|                                              AlcadeiasEA.mq5      |
//|                         Alcadeias - SHA Martingale Strategy EA     |
//+------------------------------------------------------------------+
//  Exact replica of the Alcadeias Python Trading Bot
//  (strategy.py + indicator.py + constants.py)
//
//  Smoothed Heiken Ashi v3 (SHA) with dual-indicator system:
//    • Signal SHA  (fast, default L=11 RMA)
//    • Trend SHA   (slow, default L=90 RMA)
//
//  Entry:  Signal + Trend agree, gap in range, convergence OK
//  Exit:   Profit target OR opposite signal/trend flip
//  DCA:    RSI oversold/overbought with position count limit
//
//  Attach to M1 chart for faithful reproduction of the Python bot.
//  All key hyper-parameters are exposed as inputs for optimization.
//+------------------------------------------------------------------+
#property copyright "Alcadeias"
#property link      ""
#property version   "1.00"
#property strict
#property description "Smoothed Heiken Ashi Martingale Strategy EA"
#property description "Dual SHA + Gap + Convergence + Fibo DCA"
#property description "Attach to M1 chart for exact Python bot replica"

#include <Trade\Trade.mqh>

//+------------------------------------------------------------------+
//| Enumerations                                                      |
//+------------------------------------------------------------------+
enum ENUM_SHA_MA_TYPE
{
   SHA_MA_SMA  = 0,   // SMA - Simple Moving Average
   SHA_MA_EMA  = 1,   // EMA - Exponential Moving Average
   SHA_MA_RMA  = 2,   // RMA - Running Moving Average (Wilder's)
   SHA_MA_WMA  = 3,   // WMA - Weighted Moving Average
   SHA_MA_SMMA = 4,   // SMMA - Smoothed MA (first-value seed)
   SHA_MA_HMA  = 5,   // HMA - Hull Moving Average
};

enum ENUM_CONV_STATE
{
   CONV_UNKNOWN    = 0,  // UNKNOWN
   CONV_CLOSE      = 1,  // CLOSE
   CONV_CONVERGING = 2,  // CONVERGING
   CONV_DIVERGING  = 3,  // DIVERGING
   CONV_PARALLEL   = 4,  // PARALLEL
};

//+------------------------------------------------------------------+
//| Input Parameters — all optimisable from MT5 Strategy Tester       |
//+------------------------------------------------------------------+

//--- SHA Signal Indicator (fast)
input group           "═══ SHA Signal Indicator ═══"
input int              Inp_SHA_Sig_Len  = 11;             // Signal SHA Smoothing Length
input ENUM_SHA_MA_TYPE Inp_SHA_Sig_MA   = SHA_MA_RMA;     // Signal SHA MA Type

//--- SHA Trend Indicator (slow)
input group           "═══ SHA Trend Indicator ═══"
input int              Inp_SHA_Trd_Len  = 90;             // Trend SHA Smoothing Length
input ENUM_SHA_MA_TYPE Inp_SHA_Trd_MA   = SHA_MA_RMA;     // Trend SHA MA Type

//--- SHA Gap between Signal & Trend
input group           "═══ SHA Gap ═══"
input double Inp_Gap_Min = 0.001;                          // Gap Min (raw ratio, e.g. 0.001 = 0.1%)
input double Inp_Gap_Max = 0.003;                          // Gap Max (raw ratio, e.g. 0.003 = 0.3%)

//--- SHA Convergence / Divergence detector
input group           "═══ SHA Convergence ═══"
input int    Inp_Conv_LB      = 5;                         // Lookback Bars
input double Inp_Conv_CloseTh = 0.0003;                    // Close Threshold (gap < this → CLOSE)
input double Inp_Conv_DeadZ   = 0.0001;                    // Dead Zone (|δ| < this → PARALLEL)

//--- Strategy core parameters
input group           "═══ Strategy ═══"
input int    Inp_Lookback     = 7;                         // Analysis Lookback (bars)
input double Inp_SHA_Thr      = 0.0;                       // Min (close-open)/range for Bullish
input int    Inp_Fibo_Power   = 3;                         // DCA Fibo Power Exponent
input double Inp_Close_Profit = 2.0;                       // Profit Close Threshold ($)
input int    Inp_Fibo_SeqLen  = 25;                        // Fibonacci Sequence Length

//--- RSI Indicator
input group           "═══ RSI Indicator ═══"
input int              Inp_RSI_Len       = 14;             // RSI Period
input ENUM_SHA_MA_TYPE Inp_RSI_MA        = SHA_MA_RMA;     // RSI MA Type (RMA = Wilder's)
input double           Inp_RSI_Oversold  = 30.0;           // RSI Oversold (BUY_MORE when <=)
input double           Inp_RSI_Overbought = 70.0;          // RSI Overbought (SELL_MORE when >=)
input int              Inp_RSI_DCA_Max   = 1;              // Max DCA positions via RSI signal

//--- Lot sizing
input group           "═══ Lots ═══"
input double Inp_Lot_Size = 0.01;                          // Base Lot (mtqty)
input double Inp_Times    = 1.0;                           // Times / Hedge Multiplier
input bool   Inp_Brake    = false;                         // Brake — block new entries

//--- General
input group           "═══ General ═══"
input long   Inp_Magic     = 123456;                       // Magic Number
input int    Inp_Bar_Count = 1000;                         // Bars to load for SHA warmup

//+------------------------------------------------------------------+
//| Globals                                                           |
//+------------------------------------------------------------------+
CTrade   g_trade;           // MQL5 trade helper
datetime g_lastBar = 0;     // New-bar detection
int      g_fibo[];          // Fibonacci cache (first 2 dropped)
int      g_fiboLen = 0;     // Length of usable fibo array

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
{
   // Trade object setup
   g_trade.SetExpertMagicNumber(Inp_Magic);
   g_trade.SetDeviationInPoints(50);

   // Auto-detect best filling mode for this broker / symbol
   long fm = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if(fm & SYMBOL_FILLING_FOK)        g_trade.SetTypeFilling(ORDER_FILLING_FOK);
   else if(fm & SYMBOL_FILLING_IOC)   g_trade.SetTypeFilling(ORDER_FILLING_IOC);
   else                                g_trade.SetTypeFilling(ORDER_FILLING_RETURN);

   // Build fibonacci sequence once
   BuildFibo();

   // Log config
   PrintFormat("[Alcadeias] Signal SHA(%d, %s) | Trend SHA(%d, %s)",
               Inp_SHA_Sig_Len, EnumToString(Inp_SHA_Sig_MA),
               Inp_SHA_Trd_Len, EnumToString(Inp_SHA_Trd_MA));
   PrintFormat("[Alcadeias] Gap [%.4f – %.4f] | Conv(lb=%d, cl=%.4f, dz=%.4f)",
               Inp_Gap_Min, Inp_Gap_Max,
               Inp_Conv_LB, Inp_Conv_CloseTh, Inp_Conv_DeadZ);
   PrintFormat("[Alcadeias] Lookback=%d | SHA_Thr=%.2f | FiboPow=%d | CloseProfit=$%.1f",
               Inp_Lookback, Inp_SHA_Thr, Inp_Fibo_Power, Inp_Close_Profit);
   PrintFormat("[Alcadeias] RSI(%d, %s) | OS=%.0f | OB=%.0f | DCA_Max=%d",
               Inp_RSI_Len, EnumToString(Inp_RSI_MA),
               Inp_RSI_Oversold, Inp_RSI_Overbought, Inp_RSI_DCA_Max);
   PrintFormat("[Alcadeias] Lot=%.2f × %.1f | Magic=%d | Bars=%d",
               Inp_Lot_Size, Inp_Times, Inp_Magic, Inp_Bar_Count);

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) { Comment(""); }

//+------------------------------------------------------------------+
//| Expert tick function — main loop                                  |
//+------------------------------------------------------------------+
void OnTick()
{
   // ── Only act on completed bars (new bar detection) ──
   if(!IsNewBar()) return;

   // ════════════════════════════════════════════════════════════════
   //  1. LOAD PRICE DATA
   // ════════════════════════════════════════════════════════════════
   MqlRates rates[];
   ArraySetAsSeries(rates, false);   // index 0 = oldest
   int n = CopyRates(_Symbol, PERIOD_CURRENT, 0, Inp_Bar_Count, rates);
   int minBars = MathMax(Inp_SHA_Trd_Len * 3, 200);
   if(n < minBars)
   {
      PrintFormat("[Alcadeias] Need %d bars, got %d — skipping", minBars, n);
      return;
   }

   // Extract OHLC arrays (chronological, index 0 = oldest)
   double O[], H[], L[], C[];
   ArrayResize(O, n);  ArrayResize(H, n);
   ArrayResize(L, n);  ArrayResize(C, n);
   for(int i = 0; i < n; i++)
   {
      O[i] = rates[i].open;
      H[i] = rates[i].high;
      L[i] = rates[i].low;
      C[i] = rates[i].close;
   }

   // ════════════════════════════════════════════════════════════════
   //  2. SHA SIGNAL INDICATOR (fast)
   // ════════════════════════════════════════════════════════════════
   double sigO[], sigH[], sigL[], sigC[];
   CalcSHA(O, H, L, C, sigO, sigH, sigL, sigC,
           Inp_SHA_Sig_Len, Inp_SHA_Sig_MA, n);

   // ════════════════════════════════════════════════════════════════
   //  3. SHA TREND INDICATOR (slow)
   // ════════════════════════════════════════════════════════════════
   double trdO[], trdH[], trdL[], trdC[];
   CalcSHA(O, H, L, C, trdO, trdH, trdL, trdC,
           Inp_SHA_Trd_Len, Inp_SHA_Trd_MA, n);

   // ── Validate that SHA values are ready at the last bar ──
   int last = n - 1;
   if(sigO[last] == EMPTY_VALUE || sigH[last] == EMPTY_VALUE ||
      sigL[last] == EMPTY_VALUE || sigC[last] == EMPTY_VALUE ||
      trdO[last] == EMPTY_VALUE || trdH[last] == EMPTY_VALUE ||
      trdL[last] == EMPTY_VALUE || trdC[last] == EMPTY_VALUE)
   {
      Print("[Alcadeias] SHA warmup incomplete — waiting for more bars");
      return;
   }

   // ════════════════════════════════════════════════════════════════
   //  4. GAP% SERIES & CURRENT GAP
   // ════════════════════════════════════════════════════════════════
   double gapArr[];
   CalcGapSeries(sigO, sigH, sigL, sigC,
                 trdO, trdH, trdL, trdC, gapArr, n);

   double curGap = 0.0;
   for(int i = last; i >= 0; i--)
      if(gapArr[i] != EMPTY_VALUE) { curGap = NormalizeDouble(gapArr[i], 6); break; }

   // ════════════════════════════════════════════════════════════════
   //  5. CONVERGENCE / DIVERGENCE STATE
   // ════════════════════════════════════════════════════════════════
   ENUM_CONV_STATE conv = CONV_UNKNOWN;
   double gNow = 0, gPrev = 0, gDelta = 0;
   CalcConvergence(gapArr, n, Inp_Conv_LB, Inp_Conv_CloseTh, Inp_Conv_DeadZ,
                   conv, gNow, gPrev, gDelta);

   // ════════════════════════════════════════════════════════════════
   //  6. SHA SIGNAL POWER  (most recent bar)
   //     1 = bullish (close > open relative to range)
   //     0 = bearish
   // ════════════════════════════════════════════════════════════════
   int sigPow = BarPower(sigO[last], sigH[last], sigL[last], sigC[last]);
   int trdPow = BarPower(trdO[last], trdH[last], trdL[last], trdC[last]);

   // ════════════════════════════════════════════════════════════════
   //  6b. RSI INDICATOR
   // ════════════════════════════════════════════════════════════════
   double rsiArr[];
   CalcRSI(C, rsiArr, Inp_RSI_Len, Inp_RSI_MA, n);
   double curRSI = 50.0;  // default neutral
   if(rsiArr[last] != EMPTY_VALUE)
      curRSI = rsiArr[last];

   // ════════════════════════════════════════════════════════════════
   //  7. POSITIONS
   // ════════════════════════════════════════════════════════════════
   int    bCnt = 0, sCnt = 0;
   double bProf = 0, sProf = 0, bFirst = 0, sFirst = 0;
   GetPositions(bCnt, bProf, bFirst, sCnt, sProf, sFirst);

   // ════════════════════════════════════════════════════════════════
   //  8. ENTRY / EXIT LOGIC  (strategy.py lines 242–271)
   // ════════════════════════════════════════════════════════════════
   bool gapInRange  = (curGap >= Inp_Gap_Min && curGap <= Inp_Gap_Max);
   bool entryConvOk = (conv == CONV_DIVERGING || conv == CONV_PARALLEL);

   int buySig  = 0;   // 0=nothing  1=BUY  3=CLOSE_BUY  5=BUY_MORE
   int sellSig = 0;   // 0=nothing  2=SELL 4=CLOSE_SELL  6=SELL_MORE

   // ── No positions open → entry ──
   if(bCnt == 0 && sCnt == 0)
   {
      if(sigPow == 1 && trdPow == 1 && gapInRange && entryConvOk)
         buySig = 1;                                 // BUY
      else if(sigPow == 0 && trdPow == 0 && gapInRange && entryConvOk)
         sellSig = 2;                                // SELL
   }
   // ── Only BUY positions open ── exit or RSI DCA
   else if(bCnt > 0 && sCnt == 0)
   {
      if(bProf > Inp_Close_Profit)
         buySig = 3;                                 // CLOSE_BUY  (profit target)
      else if(curRSI <= Inp_RSI_Oversold && bCnt <= Inp_RSI_DCA_Max)
         buySig = 5;                                 // BUY_MORE   (RSI oversold DCA)
   }
   // ── Only SELL positions open ── exit or RSI DCA
   else if(bCnt == 0 && sCnt > 0)
   {
      if(sProf > Inp_Close_Profit)
         sellSig = 4;                                // CLOSE_SELL (profit target)
      else if(curRSI >= Inp_RSI_Overbought && sCnt <= Inp_RSI_DCA_Max)
         sellSig = 6;                                // SELL_MORE  (RSI overbought DCA)
   }
   // ── Both sides open → do nothing (matches Python) ──

   // ════════════════════════════════════════════════════════════════
   //  9. ORDER EXECUTION
   // ════════════════════════════════════════════════════════════════
   double entryLot = NormLots(Inp_Times * Inp_Lot_Size);

   // ── BUY signals ──
   if(buySig == 1 && !Inp_Brake)
   {
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      if(g_trade.Buy(entryLot, _Symbol, ask, 0, 0, "Alcadeias BUY"))
         PrintFormat("[Alcadeias] BUY %.2f lots @ %.5f", entryLot, ask);
   }
   else if(buySig == 3)
   {
      int closed = CloseType(POSITION_TYPE_BUY);
      PrintFormat("[Alcadeias] CLOSE_BUY — %d positions, P/L=%.2f", closed, bProf);
   }
   else if(buySig == 5)
   {
      double vol = NormLots(FiboVolume(bCnt, Inp_Times));
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      if(g_trade.Buy(vol, _Symbol, ask, 0, 0,
                      StringFormat("Alcadeias RSI DCA BUY #%d", bCnt + 1)))
         PrintFormat("[Alcadeias] BUY_MORE #%d  %.2f lots @ %.5f  (RSI=%.1f <= %.0f)",
                     bCnt + 1, vol, ask, curRSI, Inp_RSI_Oversold);
   }

   // ── SELL signals ──
   if(sellSig == 2 && !Inp_Brake)
   {
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      if(g_trade.Sell(entryLot, _Symbol, bid, 0, 0, "Alcadeias SELL"))
         PrintFormat("[Alcadeias] SELL %.2f lots @ %.5f", entryLot, bid);
   }
   else if(sellSig == 4)
   {
      int closed = CloseType(POSITION_TYPE_SELL);
      PrintFormat("[Alcadeias] CLOSE_SELL — %d positions, P/L=%.2f", closed, sProf);
   }
   else if(sellSig == 6)
   {
      double vol = NormLots(FiboVolume(sCnt, Inp_Times));
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      if(g_trade.Sell(vol, _Symbol, bid, 0, 0,
                       StringFormat("Alcadeias RSI DCA SELL #%d", sCnt + 1)))
         PrintFormat("[Alcadeias] SELL_MORE #%d  %.2f lots @ %.5f  (RSI=%.1f >= %.0f)",
                     sCnt + 1, vol, bid, curRSI, Inp_RSI_Overbought);
   }

   // ════════════════════════════════════════════════════════════════
   //  10. CHART DISPLAY
   // ════════════════════════════════════════════════════════════════
   string cmt = StringFormat(
      "============ Alcadeias EA ============\n"
      "Signal SHA(%d): %s   |   Trend SHA(%d): %s\n"
      "Gap: %.4f   [%.4f - %.4f]  %s\n"
      "Conv: %s   (now=%.6f  prev=%.6f  d=%.6f)\n"
      "--------------------------------------\n"
      "BUY:  n=%d   P/L=$%.2f   1st=$%.2f\n"
      "SELL: n=%d   P/L=$%.2f   1st=$%.2f\n"
      "--------------------------------------\n"
      "RSI(%d): %.1f   OS=%.0f  OB=%.0f  DCA_Max=%d\n"
      "Next DCA vol:  BUY=%.2f  SELL=%.2f\n"
      "--------------------------------------\n"
      ">> %s",
      //--- row 1
      Inp_SHA_Sig_Len, sigPow == 1 ? "BULL" : "BEAR",
      Inp_SHA_Trd_Len, trdPow == 1 ? "BULL" : "BEAR",
      //--- row 2
      curGap, Inp_Gap_Min, Inp_Gap_Max,
      gapInRange ? "IN-RANGE" : "OUT",
      //--- row 3
      ConvStr(conv), gNow, gPrev, gDelta,
      //--- row 4-5
      bCnt, bProf, bFirst,
      sCnt, sProf, sFirst,
      //--- row 6: RSI
      Inp_RSI_Len, curRSI, Inp_RSI_Oversold, Inp_RSI_Overbought, Inp_RSI_DCA_Max,
      //--- row 7: Next DCA vol
      bCnt > 0 ? NormLots(FiboVolume(bCnt, Inp_Times)) : 0.0,
      sCnt > 0 ? NormLots(FiboVolume(sCnt, Inp_Times)) : 0.0,
      //--- action
      ActionStr(buySig, sellSig)
   );
   Comment(cmt);
}


//╔══════════════════════════════════════════════════════════════════╗
//║                     UTILITY FUNCTIONS                           ║
//╚══════════════════════════════════════════════════════════════════╝

//+------------------------------------------------------------------+
//| New bar detection (works on current chart timeframe)              |
//+------------------------------------------------------------------+
bool IsNewBar()
{
   datetime t = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(t != g_lastBar) { g_lastBar = t; return true; }
   return false;
}

//+------------------------------------------------------------------+
//| SHA bar power: 1=bullish, 0=bearish                               |
//| Matches: strategy.py _analyze / _analyze_trend logic              |
//+------------------------------------------------------------------+
int BarPower(double o, double h, double l, double c)
{
   double diff  = c - o;
   double range = h - l;
   if(range != 0.0 && (diff / range) >= Inp_SHA_Thr)
      return 1;   // bullish
   return 0;      // bearish
}

//+------------------------------------------------------------------+
//| Convergence state to string                                       |
//+------------------------------------------------------------------+
string ConvStr(ENUM_CONV_STATE st)
{
   switch(st)
   {
      case CONV_CLOSE:      return "CLOSE";
      case CONV_CONVERGING: return "CONVERGING";
      case CONV_DIVERGING:  return "DIVERGING";
      case CONV_PARALLEL:   return "PARALLEL";
      default:              return "UNKNOWN";
   }
}

//+------------------------------------------------------------------+
//| Action string for chart comment                                   |
//+------------------------------------------------------------------+
string ActionStr(int buySig, int sellSig)
{
   if(buySig == 1)  return "BUY (entry)";
   if(buySig == 3)  return "CLOSE BUY";
   if(buySig == 5)  return "BUY MORE (DCA)";
   if(sellSig == 2) return "SELL (entry)";
   if(sellSig == 4) return "CLOSE SELL";
   if(sellSig == 6) return "SELL MORE (DCA)";
   return "WAIT";
}


//╔══════════════════════════════════════════════════════════════════╗
//║                     FIBONACCI FUNCTIONS                         ║
//╚══════════════════════════════════════════════════════════════════╝

//+------------------------------------------------------------------+
//| Build fibonacci sequence cache (first 2 values 0,1 dropped)      |
//| Result: [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, ...]                |
//| Matches: strategy.py _recur_fibo + [2:] slice                    |
//+------------------------------------------------------------------+
void BuildFibo()
{
   int full[];
   ArrayResize(full, Inp_Fibo_SeqLen);
   for(int i = 0; i < Inp_Fibo_SeqLen; i++)
   {
      if(i <= 1) full[i] = i;
      else       full[i] = full[i - 1] + full[i - 2];
   }
   // Drop first 2 → [1, 2, 3, 5, 8, 13, ...]
   g_fiboLen = Inp_Fibo_SeqLen - 2;
   ArrayResize(g_fibo, g_fiboLen);
   for(int i = 0; i < g_fiboLen; i++)
      g_fibo[i] = full[i + 2];
}

//+------------------------------------------------------------------+
//| FiboQty — DCA threshold helper                                    |
//| Matches: strategy.py _get_fibo_qty(qty_count, times)             |
//|   fib[qty_count] * times                                         |
//+------------------------------------------------------------------+
double FiboQty(int idx, double times)
{
   if(idx >= 0 && idx < g_fiboLen)
      return (double)g_fibo[idx] * times;
   return times;  // fallback (matches Python except/IndexError)
}

//+------------------------------------------------------------------+
//| FiboVolume — next DCA lot size                                    |
//| Matches: strategy.py _get_next_fibo_volume(position_count, times)|
//|   round(fib[position_count] * times / 100, 2)                    |
//+------------------------------------------------------------------+
double FiboVolume(int posCount, double times)
{
   if(posCount >= 0 && posCount < g_fiboLen)
      return NormalizeDouble((double)g_fibo[posCount] * times / 100.0, 2);
   return NormalizeDouble(0.01 * times, 2);  // fallback
}

//+------------------------------------------------------------------+
//| Normalize lot to broker constraints                               |
//+------------------------------------------------------------------+
double NormLots(double lots)
{
   double mn = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double mx = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double st = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(st <= 0) st = 0.01;

   lots = MathMax(lots, mn);
   lots = MathMin(lots, mx);
   lots = MathFloor(lots / st) * st;
   return NormalizeDouble(lots, 2);
}


//╔══════════════════════════════════════════════════════════════════╗
//║                    POSITION MANAGEMENT                          ║
//╚══════════════════════════════════════════════════════════════════╝

//+------------------------------------------------------------------+
//| Gather position info (buy/sell counts, profits, first-profit)     |
//| Matches: mt5_helper.py get_buy_positions / get_sell_positions     |
//| "first" = oldest position by open time                            |
//+------------------------------------------------------------------+
void GetPositions(int &bCnt, double &bProf, double &bFirst,
                  int &sCnt, double &sProf, double &sFirst)
{
   bCnt = 0;  bProf = 0;  bFirst = 0;
   sCnt = 0;  sProf = 0;  sFirst = 0;

   datetime bFirstTime = D'2099.01.01';
   datetime sFirstTime = D'2099.01.01';

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != Inp_Magic) continue;

      double   profit   = PositionGetDouble(POSITION_PROFIT);
      long     type     = PositionGetInteger(POSITION_TYPE);
      datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);

      if(type == POSITION_TYPE_BUY)
      {
         bCnt++;
         bProf += profit;
         if(openTime < bFirstTime)
         {
            bFirstTime = openTime;
            bFirst     = profit;
         }
      }
      else if(type == POSITION_TYPE_SELL)
      {
         sCnt++;
         sProf += profit;
         if(openTime < sFirstTime)
         {
            sFirstTime = openTime;
            sFirst     = profit;
         }
      }
   }

   bProf  = NormalizeDouble(bProf, 2);
   sProf  = NormalizeDouble(sProf, 2);
   bFirst = NormalizeDouble(bFirst, 2);
   sFirst = NormalizeDouble(sFirst, 2);
}

//+------------------------------------------------------------------+
//| Close all positions of a given type (BUY or SELL)                 |
//| Returns number of positions closed.                               |
//| Matches: mt5_helper.py close_by_type                              |
//+------------------------------------------------------------------+
int CloseType(ENUM_POSITION_TYPE posType)
{
   int closed = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != Inp_Magic) continue;
      if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) != posType) continue;

      if(g_trade.PositionClose(ticket))
         closed++;
   }
   return closed;
}


//╔══════════════════════════════════════════════════════════════════╗
//║              MOVING AVERAGE FUNCTIONS                            ║
//║  TradingView-compatible implementations matching indicator.py    ║
//╚══════════════════════════════════════════════════════════════════╝

//+------------------------------------------------------------------+
//| Find first valid (non-EMPTY_VALUE) index                          |
//+------------------------------------------------------------------+
int FirstValid(const double &arr[], int n)
{
   for(int i = 0; i < n; i++)
      if(arr[i] != EMPTY_VALUE) return i;
   return -1;
}

//+------------------------------------------------------------------+
//| SMA — Simple Moving Average                                       |
//| Handles EMPTY_VALUE prefix in input (from SHA post-smooth pass)   |
//+------------------------------------------------------------------+
void MA_SMA(const double &src[], double &out[], int len, int n)
{
   ArrayResize(out, n);
   ArrayInitialize(out, EMPTY_VALUE);
   if(len <= 0 || n < len) return;

   // Find first valid value in src
   int fv = FirstValid(src, n);
   if(fv < 0 || fv + len > n) return;

   // SMA seed over first `len` valid values
   double sum = 0;
   for(int i = fv; i < fv + len; i++) sum += src[i];
   out[fv + len - 1] = sum / (double)len;

   // Rolling sum (all values from fv onward are guaranteed valid)
   for(int i = fv + len; i < n; i++)
   {
      sum += src[i] - src[i - len];
      out[i] = sum / (double)len;
   }
}

//+------------------------------------------------------------------+
//| Exponential MA — SMA-seeded (TradingView ta.ema / ta.rma style)  |
//| Seeds with SMA of first `len` consecutive valid values, then      |
//| applies standard exponential recursion.                           |
//|                                                                   |
//| RMA: alpha = 1/len          EMA: alpha = 2/(len+1)              |
//| Matches: indicator.py _tv_exp_ma                                  |
//+------------------------------------------------------------------+
void MA_Exp(const double &src[], double &out[], int len, double alpha, int n)
{
   ArrayResize(out, n);
   ArrayInitialize(out, EMPTY_VALUE);
   if(len <= 0 || n <= 0) return;

   // Find first window of `len` consecutive valid values
   int run = 0, seedEnd = -1;
   for(int i = 0; i < n; i++)
   {
      if(src[i] != EMPTY_VALUE)
      {
         run++;
         if(run >= len) { seedEnd = i; break; }
      }
      else run = 0;
   }
   if(seedEnd < 0) return;

   // SMA seed
   int seedStart = seedEnd - len + 1;
   double sum = 0;
   for(int i = seedStart; i <= seedEnd; i++) sum += src[i];
   out[seedEnd] = sum / (double)len;

   // Exponential recursion
   for(int i = seedEnd + 1; i < n; i++)
   {
      if(src[i] == EMPTY_VALUE)
         out[i] = out[i - 1];                                // carry forward
      else
         out[i] = alpha * src[i] + (1.0 - alpha) * out[i - 1];
   }
}

//+------------------------------------------------------------------+
//| Exponential MA — first-value seeded (Pine SMMA style)             |
//| Seeds with first valid value, then exponential recursion.         |
//| Matches: indicator.py _tv_exp_ma_first_seed                      |
//+------------------------------------------------------------------+
void MA_ExpFirst(const double &src[], double &out[], int len, double alpha, int n)
{
   ArrayResize(out, n);
   ArrayInitialize(out, EMPTY_VALUE);

   int fv = FirstValid(src, n);
   if(fv < 0) return;

   out[fv] = src[fv];
   for(int i = fv + 1; i < n; i++)
   {
      if(src[i] == EMPTY_VALUE)
         out[i] = out[i - 1];
      else
         out[i] = alpha * src[i] + (1.0 - alpha) * out[i - 1];
   }
}

//+------------------------------------------------------------------+
//| WMA — Weighted Moving Average                                     |
//| Weights: [1, 2, 3, ..., len]                                     |
//| Handles EMPTY_VALUE in input.                                     |
//+------------------------------------------------------------------+
void MA_WMA(const double &src[], double &out[], int len, int n)
{
   ArrayResize(out, n);
   ArrayInitialize(out, EMPTY_VALUE);
   if(len <= 0) return;

   double wSum = len * (len + 1) / 2.0;

   for(int i = len - 1; i < n; i++)
   {
      bool ok  = true;
      double s = 0;
      for(int j = 0; j < len; j++)
      {
         int idx = i - len + 1 + j;
         if(src[idx] == EMPTY_VALUE) { ok = false; break; }
         s += src[idx] * (double)(j + 1);
      }
      if(ok) out[i] = s / wSum;
   }
}

//+------------------------------------------------------------------+
//| HMA — Hull Moving Average                                         |
//| HMA = WMA( 2*WMA(src, len/2) - WMA(src, len),  sqrt(len) )      |
//+------------------------------------------------------------------+
void MA_HMA(const double &src[], double &out[], int len, int n)
{
   ArrayResize(out, n);
   ArrayInitialize(out, EMPTY_VALUE);
   if(len <= 0) return;

   int halfLen = len / 2;
   int sqrtLen = (int)MathSqrt((double)len);
   if(halfLen < 1) halfLen = 1;
   if(sqrtLen < 1) sqrtLen = 1;

   double wH[], wF[];
   MA_WMA(src, wH, halfLen, n);
   MA_WMA(src, wF, len, n);

   double diff[];
   ArrayResize(diff, n);
   ArrayInitialize(diff, EMPTY_VALUE);

   for(int i = 0; i < n; i++)
      if(wH[i] != EMPTY_VALUE && wF[i] != EMPTY_VALUE)
         diff[i] = 2.0 * wH[i] - wF[i];

   MA_WMA(diff, out, sqrtLen, n);
}

//+------------------------------------------------------------------+
//| MA Dispatcher — routes to the correct MA implementation           |
//| Matches: indicator.py _ma()                                       |
//+------------------------------------------------------------------+
void CalcMA(const double &src[], double &out[], int len,
            ENUM_SHA_MA_TYPE maType, int n)
{
   switch(maType)
   {
      case SHA_MA_SMA:  MA_SMA(src, out, len, n);                        break;
      case SHA_MA_EMA:  MA_Exp(src, out, len, 2.0 / (len + 1), n);      break;
      case SHA_MA_RMA:  MA_Exp(src, out, len, 1.0 / len, n);            break;
      case SHA_MA_WMA:  MA_WMA(src, out, len, n);                        break;
      case SHA_MA_SMMA: MA_ExpFirst(src, out, len, 1.0 / len, n);       break;
      case SHA_MA_HMA:  MA_HMA(src, out, len, n);                        break;
      default:          MA_Exp(src, out, len, 2.0 / (len + 1), n);      break;
   }
}


//╔══════════════════════════════════════════════════════════════════╗
//║          SMOOTHED HEIKEN ASHI v3 CALCULATION                    ║
//║  Exact match of indicator.py calculate_sha_v3                    ║
//╚══════════════════════════════════════════════════════════════════╝

//+------------------------------------------------------------------+
//| CalcSHA — Smoothed Heiken Ashi v3                                 |
//|                                                                   |
//| Step 1: Pre-smooth raw OHLC with MA(length, maType)              |
//| Step 2: Heiken Ashi calculation on smoothed values                |
//|   ha_close = (smO + smH + smL + smC) / 4                        |
//|   ha_open[0]  = (smO[0] + smC[0]) / 2                           |
//|   ha_open[i]  = (ha_open[i-1] + ha_close[i-1]) / 2              |
//|   ha_high = max(smH, ha_open, ha_close)                          |
//|   ha_low  = min(smL, ha_open, ha_close)                          |
//| Step 3: Post-smooth HA OHLC with same MA(length, maType)         |
//+------------------------------------------------------------------+
void CalcSHA(const double &rawO[], const double &rawH[],
             const double &rawL[], const double &rawC[],
             double &shaO[], double &shaH[],
             double &shaL[], double &shaC[],
             int len, ENUM_SHA_MA_TYPE mt, int n)
{
   // ── Step 1: Pre-smooth OHLC ──
   double smO[], smH[], smL[], smC[];
   CalcMA(rawO, smO, len, mt, n);
   CalcMA(rawH, smH, len, mt, n);
   CalcMA(rawL, smL, len, mt, n);
   CalcMA(rawC, smC, len, mt, n);

   // ── Step 2: Heiken Ashi on smoothed data ──
   double haC[], haO[], haH[], haL[];
   ArrayResize(haC, n);  ArrayInitialize(haC, EMPTY_VALUE);
   ArrayResize(haO, n);  ArrayInitialize(haO, EMPTY_VALUE);
   ArrayResize(haH, n);  ArrayInitialize(haH, EMPTY_VALUE);
   ArrayResize(haL, n);  ArrayInitialize(haL, EMPTY_VALUE);

   // Find first bar where ALL four pre-smoothed values are valid
   int fv = -1;
   for(int i = 0; i < n; i++)
   {
      if(smO[i] != EMPTY_VALUE && smH[i] != EMPTY_VALUE &&
         smL[i] != EMPTY_VALUE && smC[i] != EMPTY_VALUE)
      { fv = i; break; }
   }

   // Initialize output in case SHA can't be computed
   ArrayResize(shaO, n);  ArrayInitialize(shaO, EMPTY_VALUE);
   ArrayResize(shaH, n);  ArrayInitialize(shaH, EMPTY_VALUE);
   ArrayResize(shaL, n);  ArrayInitialize(shaL, EMPTY_VALUE);
   ArrayResize(shaC, n);  ArrayInitialize(shaC, EMPTY_VALUE);

   if(fv < 0) return;  // not enough data

   // ha_close = (o + h + l + c) / 4
   for(int i = fv; i < n; i++)
      haC[i] = (smO[i] + smH[i] + smL[i] + smC[i]) / 4.0;

   // ha_open: seed first valid bar, then recursive
   haO[fv] = (smO[fv] + smC[fv]) / 2.0;
   for(int i = fv + 1; i < n; i++)
      haO[i] = (haO[i - 1] + haC[i - 1]) / 2.0;

   // ha_high = max(smoothed_H, ha_open, ha_close)
   // ha_low  = min(smoothed_L, ha_open, ha_close)
   for(int i = fv; i < n; i++)
   {
      haH[i] = MathMax(smH[i], MathMax(haO[i], haC[i]));
      haL[i] = MathMin(smL[i], MathMin(haO[i], haC[i]));
   }

   // ── Step 3: Post-smooth HA OHLC ──
   CalcMA(haO, shaO, len, mt, n);
   CalcMA(haH, shaH, len, mt, n);
   CalcMA(haL, shaL, len, mt, n);
   CalcMA(haC, shaC, len, mt, n);
}


//╔══════════════════════════════════════════════════════════════════╗
//║                     RSI CALCULATION                             ║
//║  Matches: indicator.py calculate_rsi                             ║
//╚══════════════════════════════════════════════════════════════════╝

//+------------------------------------------------------------------+
//| CalcRSI — Relative Strength Index                                 |
//| delta = close[i] - close[i-1]                                    |
//| gain  = max(delta, 0),  loss = max(-delta, 0)                   |
//| avg_gain / avg_loss smoothed with MA(len, maType)                |
//| RSI = 100 - 100 / (1 + RS)                                      |
//+------------------------------------------------------------------+
void CalcRSI(const double &close[], double &rsi[],
             int len, ENUM_SHA_MA_TYPE maType, int n)
{
   ArrayResize(rsi, n);
   ArrayInitialize(rsi, EMPTY_VALUE);
   if(len <= 0 || n < 2) return;

   // Calculate delta, gain, loss
   double gain[], loss[];
   ArrayResize(gain, n);
   ArrayResize(loss, n);
   gain[0] = EMPTY_VALUE;
   loss[0] = EMPTY_VALUE;

   for(int i = 1; i < n; i++)
   {
      double delta = close[i] - close[i - 1];
      gain[i] = (delta > 0) ? delta : 0.0;
      loss[i] = (delta < 0) ? -delta : 0.0;
   }

   // Smooth gain and loss with the chosen MA
   double avgGain[], avgLoss[];
   CalcMA(gain, avgGain, len, maType, n);
   CalcMA(loss, avgLoss, len, maType, n);

   // RSI = 100 - 100 / (1 + RS)
   for(int i = 0; i < n; i++)
   {
      if(avgGain[i] == EMPTY_VALUE || avgLoss[i] == EMPTY_VALUE)
         continue;
      if(avgLoss[i] == 0.0)
         rsi[i] = 100.0;   // no losses → RSI = 100
      else
         rsi[i] = 100.0 - 100.0 / (1.0 + avgGain[i] / avgLoss[i]);
   }
}


//╔══════════════════════════════════════════════════════════════════╗
//║                 GAP & CONVERGENCE                               ║
//╚══════════════════════════════════════════════════════════════════╝

//+------------------------------------------------------------------+
//| Gap% series: abs((signal_mean - trend_mean) / trend_mean)         |
//| Matches: indicator.py calculate_sha_gap                           |
//+------------------------------------------------------------------+
void CalcGapSeries(const double &sO[], const double &sH[],
                   const double &sL[], const double &sC[],
                   const double &tO[], const double &tH[],
                   const double &tL[], const double &tC[],
                   double &gap[], int n)
{
   ArrayResize(gap, n);
   ArrayInitialize(gap, EMPTY_VALUE);

   for(int i = 0; i < n; i++)
   {
      if(sO[i] == EMPTY_VALUE || sH[i] == EMPTY_VALUE ||
         sL[i] == EMPTY_VALUE || sC[i] == EMPTY_VALUE ||
         tO[i] == EMPTY_VALUE || tH[i] == EMPTY_VALUE ||
         tL[i] == EMPTY_VALUE || tC[i] == EMPTY_VALUE) continue;

      double sMean = (sO[i] + sH[i] + sL[i] + sC[i]) / 4.0;
      double tMean = (tO[i] + tH[i] + tL[i] + tC[i]) / 4.0;

      if(tMean != 0.0)
         gap[i] = MathAbs((sMean - tMean) / tMean);
   }
}

//+------------------------------------------------------------------+
//| Convergence detection between signal SHA and trend SHA             |
//| Compares gap now vs gap `lookback` valid bars ago.                |
//|                                                                   |
//| gap_now < closeThreshold         → CLOSE                         |
//| gap_delta > deadZone             → DIVERGING                     |
//| gap_delta < -deadZone            → CONVERGING                    |
//| else                             → PARALLEL                      |
//|                                                                   |
//| Matches: indicator.py calculate_sha_convergence                   |
//+------------------------------------------------------------------+
void CalcConvergence(const double &gap[], int n, int lb,
                     double closeTh, double deadZone,
                     ENUM_CONV_STATE &state,
                     double &gNow, double &gPrev, double &gDelta)
{
   state  = CONV_UNKNOWN;
   gNow   = 0;
   gPrev  = 0;
   gDelta = 0;

   // Walk backwards to find valid gap values
   // We need: gap_now = last valid, gap_prev = (lb+1)th valid from end
   int cnt = 0;
   int nowIdx  = -1;
   int prevIdx = -1;

   for(int i = n - 1; i >= 0; i--)
   {
      if(gap[i] == EMPTY_VALUE) continue;
      cnt++;
      if(cnt == 1)       nowIdx = i;         // last valid gap
      if(cnt == lb + 1) { prevIdx = i; break; }  // (lb+1)th from end
   }

   if(nowIdx < 0 || prevIdx < 0) return;  // not enough valid data

   gNow   = gap[nowIdx];
   gPrev  = gap[prevIdx];
   gDelta = gNow - gPrev;

   if(gNow < closeTh)           state = CONV_CLOSE;
   else if(gDelta > deadZone)   state = CONV_DIVERGING;
   else if(gDelta < -deadZone)  state = CONV_CONVERGING;
   else                          state = CONV_PARALLEL;
}
//+------------------------------------------------------------------+
