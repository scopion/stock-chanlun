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

ChanStock 是一款面向 A 股的智能技术分析工具，核心逻辑基于缠中说禅理论，通过程序化识别笔、线段、中枢等结构，判断趋势、背驰与买卖点，并结合 AI 大模型（DeepSeek / Gemini）输出可操作的投资建议。

### 主要目标用户

- 缠论学习者：希望将缠论应用于实战，借助系统快速识别笔、线段、中枢
- 技术分析爱好者：希望综合 MA、MACD、RSI 等指标与缠论结构
- 量化研究开发者：基于缠论数据接口做二次策略开发

---

## 系统架构

### 架构图

```
┌──────────────────────────────────────────────────────────────┐
│                        前端 (Browser)                        │
│              Vue 3 + TypeScript + ECharts                   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              统一单项目（端口 5173）                    │  │
│  │  PC 端（/）              │  移动端（/m/）             │  │
│  │  HomeView             │  MobileLayout                │  │
│  │  StockView           │  MobileHomeView             │  │
│  │  WatchlistView       │  MobileStockView            │  │
│  │  StockScreenView     │  MobileWatchlistView        │  │
│  │                      │  MobileScreenView           │  │
│  └──────────────────────────────────────────────────────┘  │
│                        │                                  │
│              ┌─────────┴─────────┐                        │
│              │    Pinia Store    │                        │
│              │  chanlun store   │                        │
│              │  watchlist store │                        │
│              │  comment store   │                        │
│              └─────────┬─────────┘                        │
│                        │ axios /api                       │
└────────────────────────┼──────────────────────────────────┘
                         /api
┌────────────────────────┼──────────────────────────────────┐
│                     后端 (Server)                           │
│           FastAPI (Python 3.10+) + Uvicorn                  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                   REST API 层 (main.py)                │  │
│  │  /api/stocks/*  /api/chanlun/*  /api/watchlist/*  │  │
│  └──────────────────────────────────────────────────────┘  │
│                              │                              │
│  ┌───────────────────────────┼──────────────────────────┐  │
│  │                   业务逻辑层                          │  │
│  │  ChanlunEngine  SignalDetector  StrategyEngine    │  │
│  │  FenxingDetector  BiDetector  WaveClassifier      │  │
│  └──────────────────────────────────────────────────────┘  │
│                              │                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           数据服务层（多源降级：东方财富/腾讯/新浪）    │  │
│  └──────────────────────────────────────────────────────┘  │
│                              │                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           AI 层 (DeepSeek / Gemini)                   │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 端口说明

| 服务 | 地址 |
|------|------|
| 前端（PC + 移动端统一） | http://localhost:5173 |
| 后端 API | http://localhost:8000 |

### URL 路由

| 路径 | 页面 |
|------|------|
| `/` | PC 首页 |
| `/stock/:code` | PC 个股分析页 |
| `/watchlist` | PC 自选股 |
| `/screen` | PC 条件选股 |
| `/m/` | 移动端首页 |
| `/m/stock/:code` | 移动端个股分析页 |
| `/m/watchlist` | 移动端自选股 |
| `/m/screen` | 移动端条件选股 |

---

## 目录结构

```
stock-chanlun/
├── backend/                          # FastAPI 后端
│   ├── main.py                      # API 入口，所有 REST 路由
│   ├── chanlun/                     # 缠论核心算法
│   │   ├── elements.py             # Pydantic 数据模型定义
│   │   ├── engine.py               # 缠论引擎（整合所有分析步骤）
│   │   ├── kline_processor.py       # K 线预处理
│   │   ├── fenxing_detector.py     # 分型检测器
│   │   ├── bi_detector.py          # 笔检测器
│   │   ├── segment_detector.py     # 线段 & 中枢检测器
│   │   └── signals.py              # 买卖点判定 + 支撑阻力位计算
│   ├── ai/                          # AI 增强模块
│   │   ├── llm_client.py          # LLM 客户端（DeepSeek / Gemini）
│   │   ├── analysis_agent.py       # 分析 Prompt 构建 & 响应解析
│   │   ├── strategy_engine.py      # 规则策略引擎
│   │   ├── wave_classifier.py      # 走势分类器
│   │   └── divergence.py           # 背驰检测器
│   ├── services/                    # 数据服务
│   │   ├── akshare_service.py       # 多源数据（东方财富/腾讯/新浪，含降级）
│   │   └── screening_service.py     # 选股服务
│   ├── requirements.txt
│   ├── .env                         # AI API Key
│   ├── watchlist.json              # 自选股持久化
│   └── settings.json              # AI 模型设置持久化
│
├── frontend/                        # Vue 3 前端（统一项目）
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue                # 根组件
│   │   ├── api/
│   │   │   └── stock.ts         # API 调用 + TypeScript 类型
│   │   ├── stores/
│   │   │   ├── chanlun.ts       # 缠论状态（独立错误状态）
│   │   │   ├── watchlist.ts     # 自选股状态（含最后更新时间）
│   │   │   └── comment.ts       # 笔记评论状态
│   │   ├── router/
│   │   │   └── index.ts        # 统一路由（PC + Mobile）
│   │   ├── views/               # PC 页面
│   │   │   ├── HomeView.vue
│   │   │   ├── StockView.vue
│   │   │   ├── WatchlistView.vue
│   │   │   └── StockScreenView.vue
│   │   ├── components/
│   │   │   ├── Chart/
│   │   │   │   ├── KLineChart.vue    # 主图（K线+缠论叠加）
│   │   │   │   ├── VolumeChart.vue
│   │   │   │   ├── MACDChart.vue
│   │   │   │   ├── RSIChart.vue
│   │   │   │   └── SKDJChart.vue
│   │   │   ├── Signal/
│   │   │   │   ├── SignalCard.vue    # 买卖点卡片
│   │   │   │   ├── StrategyCard.vue  # AI 策略卡片
│   │   │   │   └── CommentSection.vue # 笔记评论（成功 Toast）
│   │   │   └── IndicatorSelector.vue
│   │   └── mobile/               # 移动端页面和组件
│   │       ├── views/
│   │       │   ├── MobileHomeView.vue
│   │       │   ├── MobileStockView.vue
│   │       │   ├── MobileWatchlistView.vue
│   │       │   └── MobileScreenView.vue
│   │       └── components/
│   │           ├── MobileLayout.vue
│   │           ├── MobileBottomNav.vue
│   │           ├── MobileSearchBar.vue  # 含加载状态
│   │           ├── MobileKLineChart.vue
│   │           ├── MobileIndicatorSelector.vue
│   │           ├── MobileStockSheet.vue  # 底部抽屉（笔记 Tab）
│   │           └── MobileCommentSection.vue
│   ├── package.json
│   ├── vite.config.ts              # 代理到后端 :8000
│   └── index.html
│
├── README.md
```

---

## 功能特性

### 1. 缠论结构识别

| 功能 | 说明 |
|------|------|
| **分型检测** | 自动识别顶分型和底分型，严格五笔窗口；包含关系处理由两根K线相对位置决定方向 |
| **笔识别** | 顶分型 + 底分型，默认至少 5 根 K 线 |
| **线段识别** | 由连续 3 笔重叠构成，代表次级别走势 |
| **中枢识别** | 连续 3 个同级别线段重叠区域，输出上下沿价格区间 |
| **走势判断** | 上涨/下跌/盘整/震荡 |

### 2. 买卖点判定

| 买点 | 条件 |
|------|------|
| **一买** | 下跌趋势背驰点：当前段力度 < 前一段力度×0.8，且价格创阶段新低 |
| **二买** | 一买后回调低点，回调低点不跌破一买点 |
| **三买** | 向上笔确认突破某中枢后，回踩低点不跌入该中枢上沿 |

| 卖点 | 条件 |
|------|------|
| **一卖** | 上涨趋势背驰点：当前段力度 < 前一段力度×0.8 |
| **二卖** | 一卖后反弹高点，不超过一卖点 |
| **三卖** | 向下笔确认跌破某中枢后，反弹高点不突破该中枢下沿 |

### 3. 支撑阻力位

多级别自动计算并标注：中枢上下沿（强度 0.85）> 线段高低点（0.75）> 笔高低点（0.6）> 买卖点价格 > 历史高低价（0.5）。

### 4. K 线可视化

主图叠加：MA5/20/60、笔（红涨绿跌）、线段（黄/橙）、中枢（紫色矩形）、买卖点标记、AI 入场/止损/止盈线、支撑阻力水平线。
副图：成交量、MACD（DIF/DEA+柱状图）、RSI、SKDJ。

### 5. AI 策略增强

规则策略引擎 + MACD 背驰检测 + 走势分类 + 多级别共振 + LLM 自然语言分析（需配置 API Key）。

### 6. 大盘概览

实时展示上证/深证/创业板/科创50/沪深300/中证500 指数、涨跌家数、行业板块涨跌排行。

### 7. 智能选股

MACD+SKDJ 双金叉共振 + 缠论买卖点过滤 + 基础指标过滤。SSE 流式返回，边算边展示，支持分页加载。

### 8. 股票笔记

PC 端右侧栏 + 移动端底部抽屉笔记 Tab，支持发布/编辑/删除，提交后显示成功 Toast。

---

## 技术栈

### 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 主力语言 |
| FastAPI | 0.115.x | Web 框架，异步 API |
| Uvicorn | 0.32.x | ASGI 服务器 |
| Pandas | 2.2.x | K 线数据处理 |
| Pydantic | 2.10.x | 数据模型校验 |
| httpx | 0.28.x | HTTP 客户端（多源请求） |
| python-dotenv | 1.0.x | 环境变量加载 |

### 前端

| 技术 | 版本 | 用途 |
|------|------|------|
| Vue 3 | 3.5.x | 渐进式 JS 框架 |
| TypeScript | 5.7.x | 类型安全 |
| Vite | 6.0.x | 构建工具 |
| Pinia | 2.3.x | 状态管理 |
| Vue Router | 4.5.x | 前端路由 |
| ECharts | 5.5.x | K 线 & 副图图表库 |
| Axios | 1.7.x | HTTP 请求 |

### AI 模型（可选）

| 模型 | 用途 |
|------|------|
| DeepSeek API | 自然语言缠论分析 |
| Gemini API | 自然语言缠论分析 |

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

# Windows 激活
.venv\Scripts\activate

# macOS/Linux 激活
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置环境变量（可选）

在 `backend/` 目录下创建 `.env`：

```env
# DeepSeek API（可选）
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx

# Gemini API（可选，二选一）
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxx
```

> 不配置 AI Key 时，系统以纯规则模式运行，所有缠论分析和买卖点判定仍然正常工作，仅 LLM 增强分析不可用。

### 4. 启动后端

```bash
# 默认端口 8000
python main.py

# 或使用 uvicorn（支持热重载）
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

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
# 访问：http://localhost:5173
# PC 首页： http://localhost:5173/
# 移动端： http://localhost:5173/m/
# 前端自动代理 /api 请求到后端 http://localhost:8000
```

### 7. 生产构建

```bash
cd frontend
npm run build
# 构建产物输出到 frontend/dist/
```

---

## API 接口文档

> 基础路径：`http://localhost:8000/api`

### 股票数据

#### 搜索股票
```
GET /api/stocks/search?q={keyword}
```

#### 实时行情
```
GET /api/stocks/{code}/quote
```

#### K 线数据
```
GET /api/stocks/{code}/kline?level={level}&limit={limit}
```
`level`: `1min` `5min` `15min` `30min` `60min` `daily` `weekly` `monthly`

#### 大盘概览
```
GET /api/market/overview
```

#### 智能选股（SSE 流式）
```
GET /api/stocks/screen-stream?level=daily&pool_size=100&max_results=50
```

#### 缠论分析
```
GET /api/chanlun/{code}?level={level}
```

#### AI 策略信号
```
GET /api/chanlun/{code}/ai?level={level}&model={model}
```

### 自选股管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/watchlist` | 获取自选股列表 |
| POST | `/api/watchlist/{code}` | 添加自选股 |
| DELETE | `/api/watchlist/{code}` | 删除自选股 |

### 笔记管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/comments/{code}` | 获取笔记列表 |
| POST | `/api/comments` | 创建笔记 |
| PUT | `/api/comments/{id}` | 更新笔记 |
| DELETE | `/api/comments/{id}` | 删除笔记 |

---

## 缠论算法说明

### 分型检测

分型是缠论最基础的结构单元，分为顶分型和底分型：

- **顶分型**：中间 K 线高点最高、低点也最高（相邻三根 K 线呈「∧」形）
- **底分型**：中间 K 线高点最低、低点也最低（相邻三根 K 线呈「∨」形）

包含关系处理：两根 K 线产生包含时，依据相对位置决定取高高或取低低。

### 笔（Bi）

笔是连接相邻顶底分型的 K 线段：
- **向上笔**：底分型 → 顶分型
- **向下笔**：顶分型 → 底分型
- **最小笔长**：默认 5 根 K 线

### 线段（Segment）

由连续 3 笔重叠构成，代表次级别走势。线段结束需要被反向线段破坏。

### 中枢（Zhongshu）

连续 3 个同级别线段重叠区域，代表多空博弈均衡区间。

### 背驰判断

比较相邻同向段的价格变化幅度与 MACD 面积：
- **底背驰**：价格新低，但 MACD 面积未新低
- **顶背驰**：价格新高，但 MACD 面积未新高

---

## 前端页面说明

### PC 端

| 路径 | 说明 |
|------|------|
| `/` | 首页：大盘指数 + 热门股票 + 财经要闻 |
| `/stock/:code` | 个股分析：三栏布局（左侧行情统计 + 中间K线图 + 右侧AI策略） |
| `/watchlist` | 自选股监控：添加/删除/刷新，含最后更新时间 |
| `/screen` | 条件选股：SSE流式结果，分页加载 |

### 移动端

| 路径 | 说明 |
|------|------|
| `/m/` | 首页：搜索栏 + 指数 + 热门板块 + 热门股票 |
| `/m/stock/:code` | 个股页：顶部价格 + K线图 + 级别切换 + 信号摘要（可展开）+ 底部抽屉（行情/缠论/AI/笔记） |
| `/m/watchlist` | 自选股列表 |
| `/m/screen` | 条件选股 |

---

## 配置与参数

### 后端环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | ❌ | DeepSeek API Key |
| `GEMINI_API_KEY` | ❌ | Gemini API Key |

### 前端指标默认值

| 指标 | 默认 | 指标 | 默认 |
|------|------|------|------|
| MA5/20/60 | ✅ 开启 | 成交量 | ✅ 开启 |
| 笔/线段/中枢 | ✅ 开启 | MACD | ✅ 开启 |
| 买卖点 | ✅ 开启 | RSI | ❌ 关闭 |
| AI 信号线 | ✅ 开启 | SKDJ | ❌ 关闭 |
| 支撑阻力 | ✅ 开启 | | |

所有指标可通过 `IndicatorSelector` 组件实时切换，无需重新加载数据。

---

## 常见问题

### Q: K 线数据获取超时？
后端已实现多源降级（东方财富 → 腾讯 → 新浪），超时后自动尝试备用源。

### Q: 缠论分析结果为空？
K 线数据不足 20 根时返回空，请确认股票有足够交易历史。

### Q: AI 分析不可用？
确认已配置 `.env` 中的 API Key，或切换至另一 AI 模型（DeepSeek ↔ Gemini）。

### Q: 前端代理不生效？
检查 `vite.config.ts` 中 `target` 与后端端口一致（默认 8000）。

### Q: 如何添加新指标？
1. 后端：在 `backend/chanlun/` 中计算
2. 前端：在 `frontend/src/api/stock.ts` 添加类型
3. 在 `frontend/src/components/Chart/` 新建 `XxxChart.vue`
4. 在 `StockView.vue` 中引入并通过 `indicators.xxx` 控制

---

## 开发路线图

- [ ] 历史买卖点回测框架
- [ ] 多标的选择与对比分析
- [ ] 自选股价格预警推送
- [ ] 更多副图指标（布林带/DMI 等）
- [ ] 导出分析报告（PDF）
- [ ] WebSocket 实时行情推送

---

## 免责声明

本系统仅供技术研究与学习使用，不构成任何投资建议。股票投资有风险，入市需谨慎。系统分析结果可能与实际走势存在偏差，投资者应自行承担决策风险。
