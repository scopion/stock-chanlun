import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import StockView from '../views/StockView.vue'
import WatchlistView from '../views/WatchlistView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: HomeView },
    { path: '/stock/:code', component: StockView },
    { path: '/watchlist', component: WatchlistView },
    { path: '/screen', component: () => import('../views/StockScreenView.vue') },
  ]
})

export default router