# ChanStock — 缠论智能股票分析系统

> 基于缠论（Chan Theory）的智能股票分析系统，结合 AI 背驰判断提供买卖点建议，支持日线、周线、月线及分钟级别的 K 线可视化分析。

---

## 目录

- [项目概览](#项目概览)
- [系统架构](#系统架构)
- [目录结构](#目录结构)
- [功能特性](#功能特性)
- [技术栈](#技术栈)
- [安装部署](#安装部署)
- [API 接口文档](#api-接口文档)
- [缠论算法说明](#缠论算法说明)
- [前端页面说明](#前端页面说明)
- [配置与参数](#配置与参数)
- [常见问题](#常见问题)

---

## 项目概览

ChanStock 是一款面向 A 股的智能技术分析工具，核心逻辑基于缠中说禅理论（简称缠论），通过程序化识别笔、线段、中枢等结构，判断趋势、背驰与买卖点，并结合 AI 大模型（DeepSeek / Gemini）输出可操作的投资建议。

### 主要目标用户

- 缠论学习者：希望将缠论应用于实战，借助系统快速识别笔、线段、中枢
- 技术分析爱好者：希望综合 MA、MACD、RSI 等指标与缠论结构
- 量化研究开发者：基于缠论数据接口做二次策略开发

---

## 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                        前端 (Browser)                        │
│              Vue 3 + TypeScript + ECharts                   │
│                                                              │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────────┐  ┌─────────────────┐  │
│  │ HomeView │  │ StockView     │  │ WatchlistView         │  │ StockScreenView │  │
│  │  首页     │  │ 个股分析页面   │  │ 自选股监控页           │  │ 智能选股页面      │  │
│  └──────────┘  └──────────────┘  └──────────────────────┘  └─────────────────┘  │
│                        │                                     │
│              ┌─────────┴─────────┐                           │
│              │    Pinia Store    │                           │
│              │  chanlun store    │                           │
│              │  watchlist store  │                           │
│              └─────────┬─────────┘                           │
│                        │ axios /api                          │
└────────────────────────┼────────────────────────────────────┘
                         /api
┌────────────────────────┼────────────────────────────────────┐
│                     后端 (Server)                             │
│           FastAPI (Python 3.10+) + Uvicorn                   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │                   REST API 层 (main.py)              │    │
│  │  /api/stocks/*  /api/chanlun/*  /api/watchlist/*    │    │
│  └──────────────────────────────────────────────────────┘    │
│                              │                               │
│  ┌───────────────────────────┼───────────────────────────┐  │
│  │                   业务逻辑层                          │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  ┌────────────────────┐  │
│  │  │ ChanlunEngine│  │ SignalDetector│  │StrategyEng│  │ ScreeningService   │  │
│  │  └──────────────┘  └──────────────┘  └───────────┘  └────────────────────┘  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │  │
│  │  │ FenxingDetect│  │  BiDetector   │  │ WaveClass │  │  │
│  │  └──────────────┘  └──────────────┘  └───────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│                              │                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                   数据服务层                           │  │
│  │              AKShare (东方财富/新浪/同花顺数据源)                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                              │                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                   AI 层                              │  │
│  │         LLM Client (DeepSeek / Gemini)                │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 数据流向

```
用户输入股票代码
      │
      ▼
前端搜索 → AKShare 获取 K 线原始数据
      │
      ▼
缠论引擎（后端）
  ① 分型检测（顶分型 / 底分型）
      │
      ▼
  ② 笔识别（基于分型组合 + K 线计数过滤）
      │
      ▼
  ③ 线段识别（笔的升级，段级结构）
      │
      ▼
  ④ 中枢识别（三个以上线段重叠区域）
      │
      ▼
  ⑤ 买卖点判定（一买/二买/三买，一卖/二卖/三卖）
      │
      ▼
  ⑥ 支撑阻力位计算（中枢/笔/线段/买卖点/历史高低价）
      │
      ▼
  ⑦ 背驰检测（MACD 面积 / 力度比较）
      │
      ▼
  ⑧ 策略推荐 + AI 大模型增强
      │
      ▼
前端渲染 K 线图 + 缠论叠加 + 副图指标
```

---

## 目录结构

```
stock-chanlun/
├── backend/                          # FastAPI 后端
│   ├── main.py                      # API 入口，所有 REST 路由
│   ├── chanlun/                     # 缠论核心算法
│   │   ├── elements.py              # Pydantic 数据模型定义
│   │   ├── engine.py                # 缠论引擎（整合所有分析步骤）
│   │   ├── kline_processor.py        # K 线预处理（列名标准化等）
│   │   ├── fenxing_detector.py       # 分型检测器（顶/底分型识别）
│   │   ├── bi_detector.py           # 笔检测器（基于分型组合）
│   │   ├── segment_detector.py       # 线段 & 中枢检测器
│   │   ├── signals.py               # 买卖点判定 + 支撑阻力位计算
│   │   └── __init__.py
│   ├── ai/                          # AI 增强模块
│   │   ├── llm_client.py            # LLM 客户端（DeepSeek / Gemini）
│   │   ├── analysis_agent.py        # 分析 Prompt 构建 & 响应解析
│   │   ├── strategy_engine.py       # 规则策略引擎（信号优先级/置信度/止损止盈）
│   │   ├── wave_classifier.py       # 走势分类器（上涨/下跌/盘整/震荡）
│   │   ├── divergence.py            # 背驰检测器（MACD 面积比较）
│   │   └── __init__.py
│   ├── services/                    # 数据服务
│   │   ├── akshare_service.py       # AKShare 封装（搜索/K线/行情/新闻等）
│   │   ├── screening_service.py     # 选股服务（MACD+SKDJ 双金叉筛选）
│   │   └── __init__.py
│   ├── requirements.txt             # Python 依赖
│   ├── .env                         # 环境变量（AI API Key 等）
│   ├── watchlist.json               # 自选股持久化存储
│   └── settings.json                # AI 模型设置持久化
│
├── frontend/                        # Vue 3 前端
│   ├── src/
│   │   ├── main.ts                  # Vue 应用入口
│   │   ├── App.vue                  # 根组件（布局/nav）
│   │   ├── api/
│   │   │   └── stock.ts             # Axios API 调用 + TypeScript 类型定义
│   │   ├── stores/
│   │   │   ├── chanlun.ts           # Pinia 缠论状态管理
│   │   │   └── watchlist.ts         # Pinia 自选股状态管理
│   │   ├── router/
│   │   │   └── index.ts             # Vue Router 路由配置
│   │   ├── views/
│   │   │   ├── HomeView.vue         # 首页（大盘 + 热门股 + 财经新闻）
│   │   │   ├── StockView.vue        # 个股分析页（主体页面）
│   │   │   ├── WatchlistView.vue    # 自选股监控页
│   │   │   └── StockScreenView.vue  # 智能选股页（MACD+SKDJ 双金叉）
│   │   ├── components/
│   │   │   ├── Chart/
│   │   │   │   ├── KLineChart.vue   # 主图：K 线 + 缠论叠加（ECharts）
│   │   │   │   ├── VolumeChart.vue  # 副图：成交量
│   │   │   │   ├── MACDChart.vue    # 副图：MACD（EMA 差值 + DEA + 柱状图）
│   │   │   │   ├── RSIChart.vue     # 副图：RSI（相对强弱指数）
│   │   │   │   └── SKDJChart.vue    # 副图：SKDJ（慢速随机指标）
│   │   │   ├── Signal/
│   │   │   │   ├── SignalCard.vue   # 买卖点卡片（列表展示所有信号）
│   │   │   │   └── StrategyCard.vue # AI 策略信号卡片（方向/置信度/止损止盈）
│   │   │   └── IndicatorSelector.vue # 指标选择器（显示/隐藏各类叠加）
│   │   └── styles/
│   │       └── main.css             # 全局样式（CSS 变量：颜色/字体/主题）
│   ├── package.json
│   ├── vite.config.ts               # Vite 配置（代理到后端 :8000）
│   └── index.html
│
├── README.md                        # 本文档
```

---

## 功能特性

### 1. 缠论结构识别

| 功能 | 说明 |
|------|------|
| **分型检测** | 自动识别顶分型和底分型，严格五笔窗口（前后各1根）；包含关系处理由两根K线相对位置决定方向 |
| **笔识别** | 顶分型 + 底分型（之间有若干根K线）= 一笔，默认至少 5 根 K 线，支持配置最小笔长 |
| **线段识别** | 由连续 3 笔重叠构成（最低3笔），代表次级别走势 |
| **中枢识别** | 连续 3 个同级别线段重叠区域，输出中枢上下沿价格区间 |
| **走势判断** | 基于线段方向统计，判断上涨/下跌/盘整/震荡 |

### 2. 买卖点判定

| 买点 | 条件描述 |
|------|---------|
| **一买** | 下跌趋势背驰点：当前下跌段力度 < 前一段力度×0.8，且价格创阶段新低 |
| **二买** | 一买后回调低点，回调低点不跌破一买点（止损设在一买点下方3%以内） |
| **三买** | 向上笔确认突破某中枢后，回踩低点不跌入该中枢上沿 |

| 卖点 | 条件描述 |
|------|---------|
| **一卖** | 上涨趋势背驰点：当前上涨段力度 < 前一段力度×0.8，且价格创阶段新高 |
| **二卖** | 一卖后反弹高点，反弹高点不超过一卖点（止损设在一卖点上方3%以内） |
| **三卖** | 向下笔确认跌破某中枢后，反弹高点不突破该中枢下沿 |

### 3. 支撑阻力位

系统自动计算并标注多级别支撑阻力位：

- **中枢上下沿**：最强支撑/阻力（强度 0.85），颜色标识
- **线段高低点**：次强参考（强度 0.75）
- **笔高低点**：近期参考（强度 0.6）
- **买卖点对应价格**：信号强度映射
- **历史 K 线高低价**：近期高低价参考（强度 0.5）

同价格附近（±0.5%）自动去重，保留最强信号标注。

### 4. K 线可视化

主图支持叠加：
- MA5 / MA20 / MA60 均线（可独立开关）
- 笔（红涨绿跌实线）
- 线段（黄/橙粗线）
- 中枢区域（紫色半透明矩形 + 上下沿标注）
- 买卖点标记（彩色圆点 + 文字标签）
- AI 入场线 / 止损线 / 止盈线
- 支撑阻力水平线（支撑绿虚线 / 阻力红虚线，透明度随强度变化）

副图支持：
- 成交量柱状图（红涨绿跌）
- MACD（DIF / DEA 金叉死叉 + 柱状图）
- RSI（14 日，默认隐藏）
- SKDJ 慢速随机（默认隐藏）

### 5. AI 策略增强

| 模块 | 说明 |
|------|------|
| **规则策略引擎** | 结合买卖点 + 走势 + 背驰，输出方向/置信度/风险评级/止损止盈 |
| **背驰检测** | MACD 面积比较，检测力度衰竭 |
| **走势分类** | 上涨/下跌/盘整/震荡四象限分类 |
| **多级别共振** | 30 分钟线 + 日线趋势共振，提高信号可靠性 |
| **LLM 增强** | DeepSeek / Gemini 大模型自然语言分析（需配置 API Key） |

### 6. 大盘概览

在首页实时展示 A 股整体市场状态：

| 模块 | 说明 |
|------|------|
| **主要指数** | 上证/深证/创业板/科创50/沪深300/中证500 实时行情 |
| **市场宽度** | 上涨/下跌/平盘家数，反映整体市场情绪 |
| **行业板块** | 东方财富行业板块涨跌排行，展示领涨/领跌板块 |

### 7. 财经新闻

首页底部展示实时财经要闻：

- **东方财富快讯**（优先）：实时推送市场重要资讯
- **同花顺新闻**（备用）：市场新闻补充
- 每 5 分钟自动更新，支持点击跳转原文

### 8. 智能选股

基于缠论买卖点 + MACD/SKDJ 指标共振的选股功能：

| 功能 | 说明 |
|------|------|
| **MACD+SKDJ 双金叉共振** | MACD 金叉与 SKDJ 金叉在 ±3 根 K 线内重合，当日 DIF>DEA 且 SK>SD |
| **缠论买卖点筛选** | 按一买/二买/三买/一卖/二卖/三卖过滤候选股 |
| **基础指标过滤** | 涨跌幅区间、成交量区间、行业、PE、PB |
| **候选池** | 基于东方财富热门涨幅榜， pool_size 可配置 |
| **SSE 流式返回** | 边算边展示，实时显示分析进度 |

选股页面（`/screen`）提供：
- 筛选条件配置面板（涨跌幅/成交量/行业/PE/PB/买卖点/双金叉）
- K 线级别切换（日线/周线/月线）
- 实时进度条 + 流式结果卡片展示
- 点击结果跳转个股分析页

### 9. 股票数据

- **搜索**：支持股票代码和名称模糊搜索（东方财富数据源）
- **实时行情**：最新价、涨跌幅、开盘、最高、最低、成交量
- **K 线**：1 分钟 / 5 分钟 / 15 分钟 / 30 分钟 / 60 分钟 / 日 / 周 / 月线
- **热门股票**：当日人气榜（涨跌幅排序）
- **自选股**：持久化存储，支持添加/删除/列表展示

---

## 技术栈

### 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| **Python** | 3.10+ | 主力语言 |
| **FastAPI** | 0.115.x | Web 框架，异步 API |
| **Uvicorn** | 0.32.x | ASGI 服务器 |
| **Pandas** | 2.2.x | K 线数据处理 |
| **NumPy** | 1.26.x | 数值计算 |
| **Pydantic** | 2.10.x | 数据模型校验 |
| **AKShare** | 1.14.x | A 股数据源（东方财富/新浪） |
| **TA-Lib / ta** | 1.9.x | 技术指标计算 |
| **httpx** | 0.28.x | 异步 HTTP 客户端 |
| **python-dotenv** | 1.0.x | 环境变量加载 |
| **Redis** | 5.2.x | 热门榜缓存（可选） |

### 前端

| 技术 | 版本 | 用途 |
|------|------|------|
| **Vue 3** | 3.5.x | 渐进式 JS 框架 |
| **TypeScript** | 5.7.x | 类型安全 |
| **Vite** | 6.0.x | 构建工具 |
| **Pinia** | 2.3.x | 状态管理 |
| **Vue Router** | 4.5.x | 前端路由 |
| **ECharts** | 5.5.x | K 线 & 副图图表库 |
| **Axios** | 1.7.x | HTTP 请求 |
| **Noto Sans SC** | - | 中文字体 |

### AI 模型（可选）

| 模型 | 提供方 | 用途 |
|------|--------|------|
| **DeepSeek** | DeepSeek API | 自然语言缠论分析 |
| **Gemini** | Google Gemini API | 自然语言缠论分析 |

---

## 安装部署

### 前置条件

- Python 3.10+
- Node.js 18+
- npm 或 pnpm

### 1. 克隆项目

```bash
git clone <repo-url>
cd stock-chanlun
```

### 2. 安装后端依赖

```bash
cd backend

# 推荐创建虚拟环境
python -m venv .venv

# 激活虚拟环境（Windows）
.venv\Scripts\activate

# 激活虚拟环境（macOS/Linux）
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置环境变量（可选）

在 `backend/` 目录下创建 `.env` 文件：

```env
# DeepSeek API（用于 AI 分析增强，可选）
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx

# Gemini API（可选，二选一）
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxxx

# Redis 连接（可选，用于热门榜缓存加速）
REDIS_URL=redis://localhost:6379/0
```

> 不配置 AI Key 时，系统以纯规则模式运行，所有缠论分析和买卖点判定仍然正常工作，仅 LLM 增强分析不可用。

### 4. 启动后端

```bash
# 默认端口 8000
python main.py

# 或使用 uvicorn 直接启动（支持热重载）
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 后端启动后访问
# API 文档：http://localhost:8000/docs
# 健康检查：http://localhost:8000/health
```

### 5. 安装前端依赖

```bash
cd frontend
npm install
```

### 6. 启动前端开发服务器

```bash
npm run dev
# 默认访问：http://localhost:5173
# 前端会自动代理 /api 请求到后端 http://localhost:8000
```

> **注意**：前端 vite.config.ts 中代理目标为 `http://localhost:8000`，需确保后端运行在 8000 端口，或修改 `vite.config.ts` 中的 `target` 为实际端口。

### 7. 生产构建

```bash
cd frontend
npm run build
# 构建产物输出到 frontend/dist/
```

### Docker 部署（可选）

```dockerfile
# backend/Dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## API 接口文档

> 基础路径：`http://localhost:8000/api`

### 股票数据

#### 搜索股票

```
GET /api/stocks/search?q={keyword}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| q | string | ✅ | 股票代码或名称（至少 1 字符） |

**返回示例：**

```json
{
  "stocks": [
    { "code": "000001", "name": "平安银行" },
    { "code": "600000", "name": "浦发银行" }
  ],
  "total": 2
}
```

#### 实时行情

```
GET /api/stocks/{code}/quote
```

**返回示例：**

```json
{
  "code": "000001",
  "name": "平安银行",
  "price": 12.34,
  "change_pct": 1.23,
  "volume": 12345678,
  "high": 12.50,
  "low": 12.10,
  "open": 12.20,
  "prev_close": 12.19
}
```

#### K 线数据

```
GET /api/stocks/{code}/kline?level={level}&limit={limit}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| level | string | daily | K 线级别：`1min` `5min` `15min` `30min` `60min` `daily` `weekly` `monthly` |
| limit | int | 500 | 最大返回根数（上限 2000） |

#### 热门股票

```
GET /api/stocks/hot?limit={limit}
```

返回新浪财经实时涨跌幅排行，默认 15 支。

#### 大盘概览

```
GET /api/market/overview
```

返回 A 股整体市场状态，包括主要指数、涨跌家数、行业板块。

**返回示例：**

```json
{
  "indices": {
    "sh": { "name": "上证指数", "price": 3342.01, "change_pct": 0.82 },
    "sz": { "name": "深证成指", "price": 10788.32, "change_pct": 1.15 },
    "cyb": { "name": "创业板指", "price": 2105.67, "change_pct": 1.52 },
    "kc50": { "name": "科创50", "price": 1025.44, "change_pct": 0.93 },
    "hs300": { "name": "沪深300", "price": 3902.12, "change_pct": 1.01 },
    "zz500": { "name": "中证500", "price": 5890.33, "change_pct": 0.76 }
  },
  "market_breadth": {
    "advancers": 715,
    "decliners": 4746,
    "unchanged": 35
  },
  "sectors": [...],
  "sectors_top": [{ "name": "涨幅板块", "change_pct": 3.2 }],
  "sectors_bottom": [{ "name": "跌幅板块", "change_pct": -2.1 }]
}
```

#### 智能选股（SSE 流式）

```
GET /api/stocks/screen-stream?level=daily&pool_size=100&max_results=50&dual_cross=true
```

基于缠论买卖点 + MACD/SKDJ 双金叉的选股接口，SSE 流式返回，边算边展示。

|| 参数 | 类型 | 默认值 | 说明 |
||------|------|--------|------|
|| level | string | daily | K 线级别：`daily` `weekly` `monthly` |
|| pool_size | int | 100 | 候选股票池大小 |
|| max_results | int | 50 | 最多返回结果数 |
|| dual_cross | bool | false | 是否强制要求 MACD+SKDJ 双金叉 |
|| change_pct_min | float | - | 最小涨跌幅（%） |
|| change_pct_max | float | - | 最大涨跌幅（%） |
|| volume_min | float | - | 最小成交量 |
|| industry | string | - | 行业名称过滤 |
|| pe_max | float | - | PE 上限 |
|| pb_max | float | - | PB 上限 |
|| signal_types | string | - | 逗号分隔的买卖点类型 |

**SSE 事件类型：**

- `progress`：当前分析进度 `{ "type": "progress", "done": 10, "total": 100 }`
- `result`：符合条件的结果（见下方示例）
- `done`：全部完成 `{ "type": "done", "total": 100 }`

**result 事件示例：**

```json
data: {"type": "result", "data": {
  "code": "600602",
  "name": "某股票",
  "price": 24.39,
  "change_pct": 7.4,
  "has_dual_cross": true,
  "dual_cross_date": "2026-03-30",
  "latest_signal": "一买",
  "trend": "下跌"
}}
```

#### 财经新闻

```
GET /api/news?limit={limit}
```

返回财经新闻列表，优先东方财富快讯，备用同花顺。

|| 参数 | 类型 | 默认值 | 说明 |
||------|------|--------|------|
|| limit | int | 10 | 返回条数（1-30） |

**返回示例：**

```json
{
  "items": [
    {
      "title": "央行宣布降准0.5个百分点",
      "time": "2026-04-06 10:30",
      "url": "https://...",
      "source": "东方财富",
      "digest": "央行宣布将于4月15日下调存款准备金率..."
    }
  ]
}
```

### 缠论分析

#### 缠论完整分析

```
GET /api/chanlun/{code}?level={level}
```

**返回字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| stock_code | string | 股票代码 |
| level | string | 分析级别 |
| trend | string | 走势判断：`上涨` `下跌` `盘整` `震荡` `未知` |
| summary | string | 自然语言总结 |
| bis | Bi[] | 笔列表 |
| xiangs | XiangSegment[] | 线段列表 |
| zhongshus | Zhongshu[] | 中枢列表 |
| signals | Signal[] | 买卖点列表 |
| supportResistance | SupportResistance[] | 支撑阻力位列表 |

**Signal 结构：**

```json
{
  "type": "一买",
  "level": "daily",
  "price": 12.30,
  "datetime": "2024-01-15 14:30:00",
  "confidence": 0.85,
  "stop_loss": 11.93,
  "take_profit": 12.92,
  "description": "背驰一买: 当前段力度0.12 < 前段力度0.18"
}
```

**SupportResistance 结构：**

```json
{
  "type": "support",
  "price": 12.30,
  "source": "zhongshu",
  "relatedId": "zs_1",
  "datetime": "2024-01-10 00:00:00",
  "strength": 0.85
}
```

`source` 可选值：
- `zhongshu` — 中枢上下沿
- `bi_low` / `bi_high` — 笔低/高点
- `kline_low` / `kline_high` — 线段高低点或 K 线高低价
- `signal` — 买卖点对应价格

#### AI 策略信号

```
GET /api/chanlun/{code}/ai?level={level}&model={model}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| model | string | deepseek | AI 模型：`deepseek` 或 `gemini` |

**返回示例：**

```json
{
  "stock_code": "000001",
  "level": "daily",
  "direction": "买入",
  "confidence": 0.82,
  "risk_level": "中",
  "entry_price": 12.30,
  "stop_loss": 11.93,
  "take_profit": 12.92,
  "holding_period": "1-4周",
  "description": "当前: 下跌趋势 | 信号: 一买(置信85%) | 背驰概率: 75%",
  "trend": "下跌",
  "divergence": {
    "type": "底背驰",
    "probability": 0.75,
    "description": "价格新低但 MACD 面积未新低"
  },
  "resonance": {
    "共振": true,
    "direction": "买入",
    "levels": ["30min", "daily"],
    "description": "30分钟与日线趋势共振"
  },
  "llm": {
    "model": "deepseek",
    "used": true,
    "error": null
  }
}
```

### 自选股管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/watchlist` | 获取自选股列表（带实时行情） |
| POST | `/api/watchlist/{code}` | 添加自选股 |
| DELETE | `/api/watchlist/{code}` | 删除自选股 |

> 自选股数据持久化存储在 `backend/watchlist.json` 中。

### 系统设置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/settings` | 获取当前 AI 模型设置 |
| PUT | `/api/settings?model={model}` | 切换 AI 模型 |

---

## 缠论算法说明

### 分型检测（FengxingDetector）

分型是缠论最基础的结构单元，分为顶分型和底分型：

- **顶分型**：中间 K 线高点最高、低点也最高（相邻三根 K 线呈「∧」形）
- **底分型**：中间 K 线高点最低、低点也最低（相邻三根 K 线呈「∨」形）

检测窗口取前后各 1 根 K 线（共 3 根），严格对应缠论标准定义。

**包含关系处理**（单次遍历 O(n)）：
- 两根 K 线产生包含时，判断依据是**两根线的相对位置**，而非单根自身的阴阳：
  - 若 prev 最高点 ≤ cur 最低点（prev 在 cur 下方）→ 向上关系 → **取高高**
  - 若 prev 最低点 ≥ cur 最高点（prev 在 cur 上方）→ 向下关系 → **取低低**
- 取高高：合并高低点取高（保留最高高点）
- 取低低：合并高低点取低（保留最低低点）

### 笔（BiDetector）

笔是连接相邻顶底分型（或底顶分型）的 K 线段：

- **向上笔**：底分型 → 顶分型（下降转上升）
- **向下笔**：顶分型 → 底分型（上升转下降）
- **最小笔长**：默认 5 根 K 线（防止噪音），可配置
- 笔是缠论分析的基准级别

### 线段（SegmentDetector）

线段是由连续 3 笔（或以上）重叠构成的更高周期结构，代表次级别走势。线段结束需要被反向线段破坏。

### 中枢（Zhongshu）

中枢是**连续 3 个**同级别线段重叠的价格区域，代表多空双方博弈的均衡区间：

- **中枢区间**：`[range_low, range_high]`
- 中枢上沿：重叠区域最高价
- 中枢下沿：重叠区域最低价
- 处于中枢内：盘整走势
- **三买**：向上笔确认突破某中枢后，回踩低点不跌入该中枢上沿
- **三卖**：向下笔确认跌破某中枢后，反弹高点不突破该中枢下沿

> 注意：三买/三卖的"突破"需是**已确认**的（向上/下笔终点在中枢终点之后），而非简单的任意一笔碰触。

### 背驰判断（DivergenceDetector）

背驰是缠论核心概念，表示力度衰竭：

- **判断方法**：比较相邻同向段的价格变化幅度与 MACD 面积
- **底背驰**：价格新低，但 MACD 面积未新低（或力度减小）
- **顶背驰**：价格新高，但 MACD 面积未新高（或力度减小）
- **力度公式**：`力度 = (high - low) / 时间差`

### 买卖点置信度计算

```
基础置信度 = 信号自身置信度
背驰加持   = +15%（背驰概率 > 70% 时）
多中枢衰减 = ×0.85（中枢数量 > 2 时）
趋势加持   = +10%（趋势方向与信号方向一致时）
```

---

## 前端页面说明

### 首页（`/`）

- 顶部导航栏（ChanStock Logo + 搜索框 + 选股/自选股链接）
- 股票搜索（代码/名称模糊匹配，回车或点击搜索按钮）
- **今日大盘**：上证/深证/创业板等主要指数实时行情 + 涨跌家数 + 行业板块领涨领跌
- 热门股票排行（新浪财经实时涨跌幅，显示排名/代码/名称/涨跌幅）
- 财经要闻（东方财富快讯，支持点击跳转原文）
- 点击股票卡片跳转至个股分析页

### 选股页（`/screen`）

- 筛选条件面板（涨跌幅区间、成交量区间、行业、PE/PB 上限）
- 缠论买卖点类型过滤（一买/二买/三买/一卖/二卖/三卖）
- MACD+SKDJ 双金叉开关
- K 线级别切换（日线/周线/月线）
- 实时进度条 + SSE 流式结果卡片，边算边展示
- 点击结果卡片跳转个股分析页

### 个股分析页（`/stock/{code}`）

三栏布局：

**左栏（固定 240px）**
- 股票代码 + 名称 + 实时价格 + 涨跌幅
- 开盘/最高/最低/成交量统计
- 分析级别切换（日/周/月/1分/5分/15分/30分/60分）
- 走势判断 badge + 自然语言总结
- 买卖点信号列表

**中栏（自适应）**
- 级别切换 tabs
- 主图：K 线 + 均线 + 缠论叠加 + 支撑阻力线（ECharts）
- 副图：成交量 / MACD / RSI / SKDJ（按需显示）
- 底部状态栏：当前 K 线 OHLC + MA 值

**右栏（固定 280px）**
- AI 策略卡片（方向/置信度/风险评级）
- 入场价/止损价/止盈价标注
- 背驰信息
- 多级别共振信息
- AI 模型切换（DS = DeepSeek / GM = Gemini）

**顶部操作栏**
- AI 模型切换按钮
- 刷新按钮（重新加载数据）
- 加入/移除自选股按钮

### 自选股页（`/watchlist`）

- 顶部添加股票输入框
- 自选股表格（代码/名称/现价/涨跌幅）
- 点击行跳转个股分析页
- 行末删除按钮

---

## 配置与参数

### 后端环境变量（`.env`）

| 变量 | 必填 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | ❌ | DeepSeek API Key（用于 AI 增强分析） |
| `GEMINI_API_KEY` | ❌ | Gemini API Key（二选一） |
| `REDIS_URL` | ❌ | Redis URL（用于热门榜缓存） |

### 缠论参数（代码中可调）

| 参数 | 文件 | 默认值 | 说明 |
|------|------|--------|------|
| `min_bars` | `bi_detector.py` | 5 | 笔最小 K 线数量 |
| `min_overlap_bis` | `segment_detector.py` | 3 | 线段最小笔数量 |
| 背驰阈值 | `signals.py` | 0.8 | 力度衰减 20% 触发背驰 |
| K 线数量上限 | `main.py` | 500 | 单次分析最大 K 线数 |

### 前端指标配置（`stores/chanlun.ts`）

| 指标 | 默认值 | 说明 |
|------|--------|------|
| MA5/20/60 | ✅ 开启 | 均线显示 |
| 笔/线段/中枢 | ✅ 开启 | 缠论元素叠加 |
| 买卖点 | ✅ 开启 | 信号标注 |
| AI 信号线 | ✅ 开启 | 入场/止损/止盈线 |
| 支撑阻力 | ✅ 开启 | 支撑阻力水平线 |
| 成交量 | ✅ 开启 | 副图显示 |
| MACD | ✅ 开启 | 副图显示 |
| RSI / SKDJ | ❌ 关闭 | 副图显示 |

> 所有指标可通过 `IndicatorSelector` 组件实时切换，无需重新加载数据。

---

## 常见问题

### Q: 后端启动报错 `ModuleNotFoundError: No module named 'akshare'`

确保已激活虚拟环境，并执行 `pip install -r requirements.txt`。

### Q: K 线数据获取失败

AKShare 数据源依赖网络连接，部分接口有频率限制。如持续失败，检查网络或稍后重试。

### Q: 缠论分析结果为空

K 线数据不足 20 根时系统返回 404。请确认股票有足够的交易历史（新股或停牌股数据可能不足）。

### Q: AI 分析返回错误

1. 确认已配置 `.env` 中的 API Key
2. 确认 API Key 有足够配额
3. 查看后端日志中 LLM 错误信息
4. 可切换 AI 模型（DeepSeek ↔ Gemini）尝试

### Q: 前端代理不生效

检查 `vite.config.ts` 中 `server.proxy` 配置，确保 `target` 与后端实际端口一致。默认前端 `:5173`，后端 `:8000`。

### Q: 如何添加新的技术指标？

1. 后端：在 `backend/services/akshare_service.py` 或 `backend/chanlun/kline_processor.py` 中计算指标
2. 前端：在 `frontend/src/api/stock.ts` 添加类型定义
3. 在 `frontend/src/components/Chart/` 新建 `XxxChart.vue`
4. 在 `StockView.vue` 中引入并通过 `indicators.xxx` 控制显示

### Q: 自选股数据存储在哪里？

持久化在 `backend/watchlist.json`（JSON 文件，非数据库）。如需迁移至数据库，修改 `main.py` 中 `_load_watchlist` 和 `_save_watchlist` 函数即可。

---

## 开发路线图

- [ ] 历史买卖点回测框架
- [ ] 多标的选择与对比分析
- [ ] 缠论结构自动标注（机器学习辅助笔识别）
- [ ] 自选股价格预警推送
- [ ] 更多副图指标（布林带/KDJ/DMI 等）
- [ ] 移动端适配优化
- [ ] 导出分析报告（PDF）
- [ ] WebSocket 实时行情推送

---

## 免责声明

本系统仅供技术研究与学习使用，不构成任何投资建议。股票投资有风险，入市需谨慎。系统分析结果可能与实际走势存在偏差，投资者应自行承担决策风险。请自行判断。
