<template>
  <div class="mobile-layout">
    <!-- 顶部搜索栏 -->
    <MobileSearchBar ref="searchBarRef" @search="onSearch" />

    <!-- 主内容区 -->
    <main class="mobile-main">
      <RouterView />
    </main>

    <!-- 底部 Tab 导航 -->
    <MobileBottomNav />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import MobileSearchBar from '../components/MobileSearchBar.vue'
import MobileBottomNav from '../components/MobileBottomNav.vue'

const router = useRouter()
const searchBarRef = ref<InstanceType<typeof MobileSearchBar> | null>(null)

function onSearch(code: string) {
  router.push(`/m/stock/${code}`)
}

onMounted(() => {
  searchBarRef.value?.focus()
})
</script>

<style scoped>
.mobile-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg-base);
}

.mobile-main {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding-bottom: calc(var(--tabbar-height) + env(safe-area-inset-bottom, 0px));
  padding-top: var(--searchbar-height);
}
</style>
