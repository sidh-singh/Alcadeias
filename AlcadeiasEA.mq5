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
//          (blocked when any MTF RSI is at extreme)
//  Exit:   Profit target
//  DCA:    Tiered RSI (M1→M5→M15) with fibonacci volume series
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

#define ALC_OBJ "ALC_"    // Prefix for all EA chart objects

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
input int              Inp_RSI_DCA_Max   = 3;              // Max DCA tiers (1=M1, 2=+M5, 3=+M15)

//--- RSI Multi-Timeframe Entry Filter
input group           "═══ RSI Multi-Timeframe ═══"
input double           Inp_RSI_MTF_OS    = 30.0;           // MTF RSI Oversold (blocks entry when ANY <=)
input double           Inp_RSI_MTF_OB    = 70.0;           // MTF RSI Overbought (blocks entry when ANY >=)
input int              Inp_RSI_MTF_Bars  = 200;            // Bars to load for MTF RSI warmup

//--- Lot sizing
input group           "═══ Lots ═══"
input double Inp_Lot_Size = 0.01;                          // Base Lot (mtqty)
input double Inp_Times    = 1.0;                           // Times / Hedge Multiplier
input bool   Inp_Brake    = false;                         // Brake — block new entries

//--- General
input group           "═══ General ═══"
input long   Inp_Magic     = 123456;                       // Magic Number
input int    Inp_Bar_Count = 1000;                         // Bars to load for SHA warmup

//--- Chart UI
input group           "═══ Chart UI ═══"
input bool   Inp_ShowPanel     = true;              // Show info panel on chart
input bool   Inp_ShowSHA       = true;              // Draw SHA indicator lines on chart
input bool   Inp_ShowArrows    = true;              // Show trade signal arrows on chart
input int    Inp_SHA_DrawBars  = 200;               // SHA lines: number of bars to draw
input int    Inp_SHA_SigWidth  = 2;                 // Signal SHA line width (1-5)
input int    Inp_SHA_TrdWidth  = 3;                 // Trend SHA line width (1-5)
input color  Inp_ClrSigBull    = clrLime;           // Signal SHA: Bullish color
input color  Inp_ClrSigBear    = clrRed;            // Signal SHA: Bearish color
input color  Inp_ClrTrdBull    = clrDodgerBlue;     // Trend SHA: Bullish color
input color  Inp_ClrTrdBear    = clrOrangeRed;      // Trend SHA: Bearish color
input color  Inp_ClrPanelBg    = C'15,15,25';       // Panel background color
input color  Inp_ClrPanelTxt   = clrWhite;          // Panel text color

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
   PrintFormat("[Alcadeias] RSI(%d, %s) | OS=%.0f | OB=%.0f | DCA_Tiers=%d",
               Inp_RSI_Len, EnumToString(Inp_RSI_MA),
               Inp_RSI_Oversold, Inp_RSI_Overbought, Inp_RSI_DCA_Max);
   PrintFormat("[Alcadeias] RSI MTF: OS=%.0f | OB=%.0f | Bars=%d",
               Inp_RSI_MTF_OS, Inp_RSI_MTF_OB, Inp_RSI_MTF_Bars);
   PrintFormat("[Alcadeias] Lot=%.2f × %.1f | Magic=%d | Bars=%d",
               Inp_Lot_Size, Inp_Times, Inp_Magic, Inp_Bar_Count);

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, ALC_OBJ);
   Comment("");
}

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

   // Bar times for chart UI drawing
   datetime T[];
   ArrayResize(T, n);
   for(int i = 0; i < n; i++)
      T[i] = rates[i].time;

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
   //  6b. RSI INDICATOR (chart timeframe)
   // ════════════════════════════════════════════════════════════════
   double rsiArr[];
   CalcRSI(C, rsiArr, Inp_RSI_Len, Inp_RSI_MA, n);
   double curRSI = 50.0;  // default neutral
   if(rsiArr[last] != EMPTY_VALUE)
      curRSI = rsiArr[last];

   // ════════════════════════════════════════════════════════════════
   //  6c. MULTI-TIMEFRAME RSI (M1, M5, M15)
   //      Matches: strategy.py rsi_1m / rsi_5m / rsi_15m
   // ════════════════════════════════════════════════════════════════
   double rsiM1  = CalcRSI_TF(PERIOD_M1,  Inp_RSI_Len, Inp_RSI_MA, Inp_RSI_MTF_Bars);
   double rsiM5  = CalcRSI_TF(PERIOD_M5,  Inp_RSI_Len, Inp_RSI_MA, Inp_RSI_MTF_Bars);
   double rsiM15 = CalcRSI_TF(PERIOD_M15, Inp_RSI_Len, Inp_RSI_MA, Inp_RSI_MTF_Bars);

   // MTF entry filter: block if ANY timeframe is extreme
   // Matches: strategy.py rsi_any_oversold / rsi_any_overbought / rsi_mtf_blocked
   bool rsiAnyOversold   = (rsiM1 <= Inp_RSI_MTF_OS || rsiM5 <= Inp_RSI_MTF_OS || rsiM15 <= Inp_RSI_MTF_OS);
   bool rsiAnyOverbought = (rsiM1 >= Inp_RSI_MTF_OB || rsiM5 >= Inp_RSI_MTF_OB || rsiM15 >= Inp_RSI_MTF_OB);
   bool rsiMtfBlocked    = rsiAnyOversold || rsiAnyOverbought;

   // ════════════════════════════════════════════════════════════════
   //  7. POSITIONS
   // ════════════════════════════════════════════════════════════════
   int    bCnt = 0, sCnt = 0;
   double bProf = 0, sProf = 0, bFirst = 0, sFirst = 0;
   double bVol = 0, sVol = 0;
   GetPositions(bCnt, bProf, bFirst, bVol, sCnt, sProf, sFirst, sVol);

   // ════════════════════════════════════════════════════════════════
   //  8. ENTRY / EXIT LOGIC  (strategy.py lines 242–271)
   // ════════════════════════════════════════════════════════════════
   bool gapInRange  = (curGap >= Inp_Gap_Min && curGap <= Inp_Gap_Max);
   bool entryConvOk = (conv == CONV_DIVERGING || conv == CONV_PARALLEL);

   int buySig  = 0;   // 0=nothing  1=BUY  3=CLOSE_BUY  5=BUY_MORE
   int sellSig = 0;   // 0=nothing  2=SELL 4=CLOSE_SELL  6=SELL_MORE

   // ── No positions open → entry (with MTF RSI filter) ──
   // Matches: strategy.py lines 258-263
   if(bCnt == 0 && sCnt == 0)
   {
      if(!rsiMtfBlocked)
      {
         if(sigPow == 1 && trdPow == 1 && gapInRange && entryConvOk)
            buySig = 1;                              // BUY
         else if(sigPow == 0 && trdPow == 0 && gapInRange && entryConvOk)
            sellSig = 2;                             // SELL
      }
   }
   // ── Only BUY positions open → exit or tiered RSI DCA ──
   //    Max 4 total: 1 entry + 1×M1 RSI + 1×M5 RSI + 1×M15 RSI
   //    Matches: strategy.py lines 266-274
   else if(bCnt > 0 && sCnt == 0)
   {
      if(bProf > Inp_Close_Profit)
         buySig = 3;                                 // CLOSE_BUY  (profit target)
      else if(rsiM1 <= Inp_RSI_Oversold && bCnt == 1 && Inp_RSI_DCA_Max >= 1)
         buySig = 5;                                 // BUY_MORE   (M1 RSI oversold, tier 1)
      else if(rsiM5 <= Inp_RSI_Oversold && bCnt == 2 && Inp_RSI_DCA_Max >= 2)
         buySig = 5;                                 // BUY_MORE   (M5 RSI oversold, tier 2)
      else if(rsiM15 <= Inp_RSI_Oversold && bCnt == 3 && Inp_RSI_DCA_Max >= 3)
         buySig = 5;                                 // BUY_MORE   (M15 RSI oversold, tier 3)
   }
   // ── Only SELL positions open → exit or tiered RSI DCA ──
   //    Max 4 total: 1 entry + 1×M1 RSI + 1×M5 RSI + 1×M15 RSI
   //    Matches: strategy.py lines 278-285
   else if(bCnt == 0 && sCnt > 0)
   {
      if(sProf > Inp_Close_Profit)
         sellSig = 4;                                // CLOSE_SELL (profit target)
      else if(rsiM1 >= Inp_RSI_Overbought && sCnt == 1 && Inp_RSI_DCA_Max >= 1)
         sellSig = 6;                                // SELL_MORE  (M1 RSI overbought, tier 1)
      else if(rsiM5 >= Inp_RSI_Overbought && sCnt == 2 && Inp_RSI_DCA_Max >= 2)
         sellSig = 6;                                // SELL_MORE  (M5 RSI overbought, tier 2)
      else if(rsiM15 >= Inp_RSI_Overbought && sCnt == 3 && Inp_RSI_DCA_Max >= 3)
         sellSig = 6;                                // SELL_MORE  (M15 RSI overbought, tier 3)
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
      // Volume-based fibo DCA — matches strategy.py _get_next_fibo_volume
      double vol = NormLots(FiboVolumeByTotal(bVol, Inp_Times));
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      if(g_trade.Buy(vol, _Symbol, ask, 0, 0,
                      StringFormat("Alcadeias RSI DCA BUY #%d", bCnt + 1)))
         PrintFormat("[Alcadeias] BUY_MORE #%d  %.2f lots @ %.5f  (M1=%.1f M5=%.1f M15=%.1f)",
                     bCnt + 1, vol, ask, rsiM1, rsiM5, rsiM15);
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
      // Volume-based fibo DCA — matches strategy.py _get_next_fibo_volume
      double vol = NormLots(FiboVolumeByTotal(sVol, Inp_Times));
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      if(g_trade.Sell(vol, _Symbol, bid, 0, 0,
                       StringFormat("Alcadeias RSI DCA SELL #%d", sCnt + 1)))
         PrintFormat("[Alcadeias] SELL_MORE #%d  %.2f lots @ %.5f  (M1=%.1f M5=%.1f M15=%.1f)",
                     sCnt + 1, vol, bid, rsiM1, rsiM5, rsiM15);
   }

   // ════════════════════════════════════════════════════════════════
   //  10. CHART UI — Panel, SHA Lines, Trade Arrows
   // ════════════════════════════════════════════════════════════════
   double nextBuyVol  = bCnt > 0 ? NormLots(FiboVolumeByTotal(bVol, Inp_Times)) : 0.0;
   double nextSellVol = sCnt > 0 ? NormLots(FiboVolumeByTotal(sVol, Inp_Times)) : 0.0;

   if(Inp_ShowPanel)
   {
      Comment("");  // clear text comment when panel is active
      DrawPanel(sigPow, trdPow, curGap, gapInRange, conv, gDelta,
                rsiM1, rsiM5, rsiM15, rsiMtfBlocked,
                bCnt, bVol, bProf, bFirst,
                sCnt, sVol, sProf, sFirst,
                nextBuyVol, nextSellVol, buySig, sellSig);
   }
   else
   {
      // Fallback text display when panel disabled
      Comment(StringFormat(
         "Alcadeias | Sig(%d):%s Trd(%d):%s | Gap:%.4f %s | %s | RSI M1:%.0f M5:%.0f M15:%.0f\n"
         "BUY:%d($%.2f) SELL:%d($%.2f) | Next DCA: B=%.2f S=%.2f | >> %s",
         Inp_SHA_Sig_Len, sigPow == 1 ? "BULL" : "BEAR",
         Inp_SHA_Trd_Len, trdPow == 1 ? "BULL" : "BEAR",
         curGap, gapInRange ? "OK" : "OUT", ConvStr(conv),
         rsiM1, rsiM5, rsiM15,
         bCnt, bProf, sCnt, sProf,
         nextBuyVol, nextSellVol, ActionStr(buySig, sellSig)
      ));
   }

   // Draw SHA indicator lines on chart
   DrawSHALines(T, sigO, sigC, trdO, trdC, n);

   // Draw trade arrow for current signal
   if(buySig != 0 || sellSig != 0)
      DrawTradeArrow(buySig, sellSig, T[last],
                     SymbolInfoDouble(_Symbol, SYMBOL_BID),
                     SymbolInfoDouble(_Symbol, SYMBOL_ASK));
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

//+------------------------------------------------------------------+
//| MA type short name for panel display                              |
//+------------------------------------------------------------------+
string MAShortName(ENUM_SHA_MA_TYPE t)
{
   switch(t)
   {
      case SHA_MA_SMA:  return "SMA";
      case SHA_MA_EMA:  return "EMA";
      case SHA_MA_RMA:  return "RMA";
      case SHA_MA_WMA:  return "WMA";
      case SHA_MA_SMMA: return "SMMA";
      case SHA_MA_HMA:  return "HMA";
   }
   return "?";
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
//| FiboVolumeByTotal — volume-based DCA lot size                     |
//| Matches: strategy.py _get_next_fibo_volume(total_volume, times)  |
//| Finds total_volume in fib sequence, returns next fib value.       |
//| Eg: fib lots = [0.01, 0.02, 0.03, 0.05, 0.08, 0.13, ...]       |
//|     total_volume 0.01 → next 0.02                                |
//|     total_volume 0.03 → next 0.05                                |
//+------------------------------------------------------------------+
double FiboVolumeByTotal(double totalVolume, double times)
{
   int totalUnits = (times != 0.0)
                    ? (int)MathRound(totalVolume * 100.0 / times)
                    : 0;
   for(int i = 0; i < g_fiboLen; i++)
   {
      if(g_fibo[i] >= totalUnits)
      {
         if(i + 1 < g_fiboLen)
            return NormalizeDouble((double)g_fibo[i + 1] * times / 100.0, 2);
         else
            return NormalizeDouble(0.01 * times, 2);
      }
   }
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
void GetPositions(int &bCnt, double &bProf, double &bFirst, double &bVol,
                  int &sCnt, double &sProf, double &sFirst, double &sVol)
{
   bCnt = 0;  bProf = 0;  bFirst = 0;  bVol = 0;
   sCnt = 0;  sProf = 0;  sFirst = 0;  sVol = 0;

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

      double volume = PositionGetDouble(POSITION_VOLUME);

      if(type == POSITION_TYPE_BUY)
      {
         bCnt++;
         bProf += profit;
         bVol  += volume;
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
         sVol  += volume;
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
   bVol   = NormalizeDouble(bVol, 2);
   sVol   = NormalizeDouble(sVol, 2);
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


//+------------------------------------------------------------------+
//| CalcRSI_TF — Compute RSI on a specific timeframe                  |
//| Returns last valid RSI value, or 50.0 if not enough data.         |
//| Used for multi-timeframe RSI (M1, M5, M15) matching Python.       |
//+------------------------------------------------------------------+
double CalcRSI_TF(ENUM_TIMEFRAMES tf, int rsiLen, ENUM_SHA_MA_TYPE maType, int barCount)
{
   MqlRates tfRates[];
   ArraySetAsSeries(tfRates, false);
   int tfN = CopyRates(_Symbol, tf, 0, barCount, tfRates);
   if(tfN < rsiLen + 2) return 50.0;  // not enough data

   double tfC[];
   ArrayResize(tfC, tfN);
   for(int i = 0; i < tfN; i++)
      tfC[i] = tfRates[i].close;

   double tfRSI[];
   CalcRSI(tfC, tfRSI, rsiLen, maType, tfN);

   // Return last valid RSI value
   for(int i = tfN - 1; i >= 0; i--)
      if(tfRSI[i] != EMPTY_VALUE) return tfRSI[i];

   return 50.0;  // fallback neutral
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


//╔══════════════════════════════════════════════════════════════════╗
//║                    CHART UI FUNCTIONS                           ║
//║  Dashboard panel, SHA indicator lines, trade signal arrows       ║
//╚══════════════════════════════════════════════════════════════════╝

//+------------------------------------------------------------------+
//| Create/update a rectangle label on chart                          |
//+------------------------------------------------------------------+
void UIRect(string id, int x, int y, int w, int h, color bg, color bdr)
{
   string nm = ALC_OBJ + id;
   if(ObjectFind(0, nm) < 0)
      ObjectCreate(0, nm, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, nm, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, nm, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, nm, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, nm, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, nm, OBJPROP_YSIZE, h);
   ObjectSetInteger(0, nm, OBJPROP_BGCOLOR, bg);
   ObjectSetInteger(0, nm, OBJPROP_BORDER_COLOR, bdr);
   ObjectSetInteger(0, nm, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, nm, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, nm, OBJPROP_HIDDEN, true);
   ObjectSetInteger(0, nm, OBJPROP_BACK, false);
}

//+------------------------------------------------------------------+
//| Create/update a text label on chart                               |
//+------------------------------------------------------------------+
void UIText(string id, int x, int y, string text, color clr,
            int fontSize = 9, string font = "Consolas")
{
   string nm = ALC_OBJ + id;
   if(ObjectFind(0, nm) < 0)
      ObjectCreate(0, nm, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, nm, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, nm, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, nm, OBJPROP_YDISTANCE, y);
   ObjectSetString(0, nm, OBJPROP_TEXT, text);
   ObjectSetString(0, nm, OBJPROP_FONT, font);
   ObjectSetInteger(0, nm, OBJPROP_FONTSIZE, fontSize);
   ObjectSetInteger(0, nm, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, nm, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, nm, OBJPROP_HIDDEN, true);
}

//+------------------------------------------------------------------+
//| Draw dashboard panel (top-left corner)                            |
//+------------------------------------------------------------------+
void DrawPanel(int sigPow, int trdPow,
               double curGap, bool gapInRange,
               ENUM_CONV_STATE conv, double gDelta,
               double rsiM1, double rsiM5, double rsiM15,
               bool rsiMtfBlocked,
               int bCnt, double bVol, double bProf, double bFirst,
               int sCnt, double sVol, double sProf, double sFirst,
               double nextBuyVol, double nextSellVol,
               int buySig, int sellSig)
{
   int pw = 340, px = 10, py = 25;
   int rh = 16, pad = 8;
   int titleH = rh + 4;
   int bodyRows = 15;
   int ph = titleH + bodyRows * rh + pad;

   color bg  = Inp_ClrPanelBg;
   color brd = C'60,60,80';
   color txt = Inp_ClrPanelTxt;
   color dim = C'120,120,150';
   color sep = C'45,45,65';
   color grn = clrLime;
   color red = clrRed;
   color ylw = clrGold;
   color cyn = clrAqua;

   // ── Background ──
   UIRect("PBG", px, py, pw, ph, bg, brd);
   UIRect("PTB", px, py, pw, titleH, C'30,30,55', brd);

   int tx = px + pad;
   int ty = py + 3;

   // Row 0: Title
   UIText("R00", tx, ty, "===== ALCADEIAS EA =====", ylw, 10);

   // Row 1: Signal SHA
   ty = py + titleH + pad;
   UIText("R01", tx, ty,
      StringFormat("Signal SHA(%d,%s):  %s",
         Inp_SHA_Sig_Len, MAShortName(Inp_SHA_Sig_MA),
         sigPow == 1 ? "BULL" : "BEAR"),
      sigPow == 1 ? grn : red);

   // Row 2: Trend SHA
   ty += rh;
   UIText("R02", tx, ty,
      StringFormat("Trend  SHA(%d,%s):  %s",
         Inp_SHA_Trd_Len, MAShortName(Inp_SHA_Trd_MA),
         trdPow == 1 ? "BULL" : "BEAR"),
      trdPow == 1 ? grn : red);

   // Row 3: Separator
   ty += rh;
   UIText("R03", tx, ty, "----------------------------------", sep);

   // Row 4: Gap
   ty += rh;
   UIText("R04", tx, ty,
      StringFormat("Gap: %.4f  [%.4f-%.4f]  %s",
         curGap, Inp_Gap_Min, Inp_Gap_Max,
         gapInRange ? "IN-RANGE" : "OUT"),
      gapInRange ? grn : dim);

   // Row 5: Convergence
   ty += rh;
   color cClr = (conv == CONV_DIVERGING) ? grn :
                (conv == CONV_CONVERGING) ? red :
                (conv == CONV_CLOSE) ? ylw : dim;
   UIText("R05", tx, ty,
      StringFormat("Conv: %-11s  d=%s%.6f",
         ConvStr(conv),
         gDelta >= 0 ? "+" : "", gDelta), cClr);

   // Row 6: Separator
   ty += rh;
   UIText("R06", tx, ty, "----------------------------------", sep);

   // Row 7: RSI values
   ty += rh;
   UIText("R07", tx, ty,
      StringFormat("RSI(%d)  M1:%.0f  M5:%.0f  M15:%.0f",
         Inp_RSI_Len, rsiM1, rsiM5, rsiM15), txt);

   // Row 8: MTF filter status
   ty += rh;
   UIText("R08", tx, ty,
      StringFormat("MTF: %s   DCA Tiers: %d",
         rsiMtfBlocked ? "BLOCKED" : "CLEAR",
         Inp_RSI_DCA_Max),
      rsiMtfBlocked ? red : grn);

   // Row 9: Separator
   ty += rh;
   UIText("R09", tx, ty, "----------------------------------", sep);

   // Row 10: BUY positions
   ty += rh;
   UIText("R10", tx, ty,
      StringFormat("BUY:  n=%d  vol=%.2f  P/L=$%.2f",
         bCnt, bVol, bProf),
      bCnt > 0 ? (bProf >= 0 ? grn : red) : dim);

   // Row 11: SELL positions
   ty += rh;
   UIText("R11", tx, ty,
      StringFormat("SELL: n=%d  vol=%.2f  P/L=$%.2f",
         sCnt, sVol, sProf),
      sCnt > 0 ? (sProf >= 0 ? grn : red) : dim);

   // Row 12: Next DCA volumes
   ty += rh;
   UIText("R12", tx, ty,
      StringFormat("Next DCA: BUY=%.2f  SELL=%.2f",
         nextBuyVol, nextSellVol), cyn);

   // Row 13: Separator
   ty += rh;
   UIText("R13", tx, ty, "----------------------------------", sep);

   // Row 14: Current action
   ty += rh;
   string act = ActionStr(buySig, sellSig);
   color aClr = (buySig == 1 || buySig == 5) ? grn :
                (sellSig == 2 || sellSig == 6) ? red :
                (buySig == 3 || sellSig == 4) ? ylw : txt;
   UIText("R14", tx, ty, ">> " + act, aClr, 11);
}

//+------------------------------------------------------------------+
//| Draw SHA indicator lines on chart                                 |
//| Signal SHA = colored close line (colored by bull/bear)            |
//| Trend SHA  = colored close line (thicker, colored by bull/bear)   |
//+------------------------------------------------------------------+
void DrawSHALines(const datetime &T[],
                  const double &sigO[], const double &sigC[],
                  const double &trdO[], const double &trdC[],
                  int n)
{
   if(!Inp_ShowSHA) return;

   // Remove old SHA line objects
   ObjectsDeleteAll(0, ALC_OBJ + "SS_");
   ObjectsDeleteAll(0, ALC_OBJ + "ST_");

   int from = MathMax(0, n - Inp_SHA_DrawBars);

   for(int i = from; i < n - 1; i++)
   {
      // ── Signal SHA close line (fast) ──
      if(sigC[i] != EMPTY_VALUE && sigC[i + 1] != EMPTY_VALUE)
      {
         string sn = ALC_OBJ + "SS_" + IntegerToString(i);
         bool sb = (sigC[i] >= sigO[i]);

         ObjectCreate(0, sn, OBJ_TREND, 0, T[i], sigC[i], T[i + 1], sigC[i + 1]);
         ObjectSetInteger(0, sn, OBJPROP_COLOR, sb ? Inp_ClrSigBull : Inp_ClrSigBear);
         ObjectSetInteger(0, sn, OBJPROP_WIDTH, Inp_SHA_SigWidth);
         ObjectSetInteger(0, sn, OBJPROP_RAY_RIGHT, false);
         ObjectSetInteger(0, sn, OBJPROP_SELECTABLE, false);
         ObjectSetInteger(0, sn, OBJPROP_HIDDEN, true);
         ObjectSetInteger(0, sn, OBJPROP_BACK, true);
      }

      // ── Trend SHA close line (slow) ──
      if(trdC[i] != EMPTY_VALUE && trdC[i + 1] != EMPTY_VALUE)
      {
         string tn = ALC_OBJ + "ST_" + IntegerToString(i);
         bool tb = (trdC[i] >= trdO[i]);

         ObjectCreate(0, tn, OBJ_TREND, 0, T[i], trdC[i], T[i + 1], trdC[i + 1]);
         ObjectSetInteger(0, tn, OBJPROP_COLOR, tb ? Inp_ClrTrdBull : Inp_ClrTrdBear);
         ObjectSetInteger(0, tn, OBJPROP_WIDTH, Inp_SHA_TrdWidth);
         ObjectSetInteger(0, tn, OBJPROP_RAY_RIGHT, false);
         ObjectSetInteger(0, tn, OBJPROP_SELECTABLE, false);
         ObjectSetInteger(0, tn, OBJPROP_HIDDEN, true);
         ObjectSetInteger(0, tn, OBJPROP_BACK, true);
      }
   }
}

//+------------------------------------------------------------------+
//| Draw trade arrow on chart at signal bar                           |
//| 233=up arrow, 234=down arrow, 251=X (close mark)                 |
//+------------------------------------------------------------------+
void DrawTradeArrow(int buySig, int sellSig, datetime time,
                    double bid, double ask)
{
   if(!Inp_ShowArrows) return;

   string nm = ALC_OBJ + "AR_" + IntegerToString((int)time);
   int code = 0;
   color clr;
   double price;

   if(buySig == 1)       { code = 233; clr = clrLime;        price = ask; }
   else if(buySig == 3)  { code = 251; clr = clrDeepSkyBlue; price = bid; }
   else if(buySig == 5)  { code = 233; clr = clrGreen;       price = ask; }
   else if(sellSig == 2) { code = 234; clr = clrRed;         price = bid; }
   else if(sellSig == 4) { code = 251; clr = clrDeepSkyBlue; price = ask; }
   else if(sellSig == 6) { code = 234; clr = clrOrangeRed;   price = bid; }
   else return;

   if(ObjectFind(0, nm) < 0)
      ObjectCreate(0, nm, OBJ_ARROW, 0, time, price);
   ObjectSetDouble(0, nm, OBJPROP_PRICE, price);
   ObjectSetInteger(0, nm, OBJPROP_ARROWCODE, code);
   ObjectSetInteger(0, nm, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, nm, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, nm, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, nm, OBJPROP_HIDDEN, true);
   ObjectSetInteger(0, nm, OBJPROP_ANCHOR, ANCHOR_BOTTOM);
}
//+------------------------------------------------------------------+
