import json
from fastapi.testclient import TestClient
from main import app

c = TestClient(app)
r = c.get('/api/kline', params={'code': '600519', 'level': 'daily', 'limit': 80})
klines = r.json()['data']['klines']
print(f'K线数量: {len(klines)}')

closes = [k['close'] for k in klines]
highs  = [k['high']  for k in klines]
lows   = [k['low']   for k in klines]
dates  = [k['date'][:10] for k in klines]

# MACD
def ema(arr, span):
    k = 2 / (span + 1)
    out = [arr[0]]
    for i in range(1, len(arr)):
        out.append(arr[i] * k + out[-1] * (1 - k))
    return out

ema12 = ema(closes, 12)
ema26 = ema(closes, 26)
dif   = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
deas  = ema(dif, 9)

# SKDJ
n, sn, sm = 9, 3, 1
rsv = [None] * len(closes)
for i in range(n-1, len(closes)):
    ln = min(lows[i-n+1:i+1])
    hn = max(highs[i-n+1:i+1])
    rsv[i] = 50 if hn == ln else (closes[i] - ln) / (hn - ln) * 100

sk = [None] * len(closes)
prev_sk = None
for i in range(len(closes)):
    if rsv[i] is not None:
        prev_sk = rsv[i] if prev_sk is None else (sm * rsv[i] + (sn - sm) * prev_sk) / sn
        sk[i] = prev_sk

sd = [None] * len(closes)
prev_sd = None
for i in range(len(closes)):
    if sk[i] is not None:
        prev_sd = sk[i] if prev_sd is None else (sm * sk[i] + (sn - sm) * prev_sd) / sn
        sd[i] = prev_sd

# 金叉
macd_gold = []
skdj_gold = []
for i in range(1, len(closes)):
    if dif[i-1] <= deas[i-1] and dif[i] > deas[i]:
        macd_gold.append((dates[i], round(dif[i],4), round(deas[i],4)))
    if sk[i-1] is not None and sk[i] is not None and sd[i-1] is not None and sd[i] is not None:
        if sk[i-1] <= sd[i-1] and sk[i] > sd[i]:
            skdj_gold.append((dates[i], round(sk[i],2), round(sd[i],2)))

both = set(d[0] for d in macd_gold) & set(d[0] for d in skdj_gold)
print(f'MACD金叉: {len(macd_gold)}, SKDJ金叉: {len(skdj_gold)}, 双重金叉: {len(both)}')
if both:
    print('双重金叉日期:', list(both))
else:
    print('--- 最近5个MACD金叉 ---')
    for d in macd_gold[-5:]: print(' ', d)
    print('--- 最近5个SKDJ金叉 ---')
    for d in skdj_gold[-5:]: print(' ', d)
