import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import StockView from '../views/StockView.vue'
import WatchlistView from '../views/WatchlistView.vue'
import SectorView from '../views/SectorView.vue'
import MobileLayout from '../mobile/components/MobileLayout.vue'
import MobileHomeView from '../mobile/views/MobileHomeView.vue'
import MobileSectorView from '../mobile/views/MobileSectorView.vue'
import MobileStockView from '../mobile/views/MobileStockView.vue'
import MobileWatchlistView from '../mobile/views/MobileWatchlistView.vue'

const router = createRouter({
  // 与 vite.config.ts 的 base: '/stock-chanlun/' 保持一致
  history: createWebHistory('/stock-chanlun/'),
  routes: [
    // ── PC 端路由 ──────────────────────────────────────────────────────
    { path: '/', component: HomeView },
    { path: '/stock/:code', component: StockView },
    { path: '/watchlist', component: WatchlistView },
    { path: '/screen', component: () => import('../views/StockScreenView.vue') },
    { path: '/sector/:name', component: SectorView },

    // ── Mobile 端路由（前缀 /m/）──────────────────────────────────────
    {
      path: '/m',
      component: MobileLayout,
      children: [
        { path: '', component: MobileHomeView },
        { path: 'stock/:code', component: MobileStockView },
        { path: 'watchlist', component: MobileWatchlistView },
        { path: 'screen', component: () => import('../mobile/views/MobileScreenView.vue') },
        { path: 'sector/:name', component: MobileSectorView },
      ],
    },
  ],
})

export default router
