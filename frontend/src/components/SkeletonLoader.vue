<template>
  <div class="skeleton-wrap" :class="variant">
    <div v-if="type === 'text'" class="skeleton skeleton-text" :style="textStyle" />
    <div v-else-if="type === 'card'" class="skeleton-card">
      <div class="sk-header">
        <div class="sk-circle" />
        <div class="sk-lines">
          <div class="skeleton skeleton-line" style="width: 60%" />
          <div class="skeleton skeleton-line" style="width: 40%" />
        </div>
      </div>
      <div class="sk-body">
        <div v-for="i in lines" :key="i" class="skeleton skeleton-line" :style="{ width: lineWidth(i) }" />
      </div>
    </div>
    <div v-else-if="type === 'chart'" class="skeleton-chart">
      <div class="sk-chart-area" />
      <div class="sk-chart-bar" />
    </div>
    <div v-else class="skeleton" :style="customStyle" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  type?: 'text' | 'card' | 'chart' | 'custom'
  variant?: 'dark' | 'light'
  height?: number | string
  width?: number | string
  lines?: number
  customStyle?: Record<string, string>
}>(), {
  type: 'text',
  variant: 'dark',
  height: 20,
  lines: 3,
})

const textStyle = computed(() => ({
  height: typeof props.height === 'number' ? `${props.height}px` : props.height,
  width: props.width ? (typeof props.width === 'number' ? `${props.width}px` : props.width) : '100%',
}))

function lineWidth(index: number): string {
  const widths = ['100%', '85%', '70%', '50%']
  return widths[(index - 1) % widths.length]
}
</script>

<style scoped>
.skeleton-wrap { display: inline-block; }
.skeleton-wrap.dark { --sk-bg: var(--bg-secondary); --sk-shine: var(--border); }
.skeleton-wrap.light { --sk-bg: #e5e7eb; --sk-shine: #d1d5db; }

.skeleton {
  background: linear-gradient(90deg, var(--sk-bg) 25%, var(--sk-shine) 50%, var(--sk-bg) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 6px;
}
.skeleton-text { min-height: 16px; }
.skeleton-line { height: 14px; margin-bottom: 8px; }
.skeleton-line:last-child { margin-bottom: 0; }

.skeleton-card {
  padding: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
}
.sk-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.sk-circle { width: 40px; height: 40px; border-radius: 50%; }
.sk-lines { flex: 1; display: flex; flex-direction: column; gap: 8px; }
.sk-body { display: flex; flex-direction: column; gap: 6px; }

.skeleton-chart { width: 100%; height: 200px; display: flex; flex-direction: column; gap: 16px; }
.sk-chart-area { flex: 1; border-radius: 8px; }
.sk-chart-bar { height: 40px; border-radius: 6px; }

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>