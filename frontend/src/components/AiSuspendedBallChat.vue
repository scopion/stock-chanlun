<template>
  <Teleport to="body">
    <div class="ai-suspended-root">
      <Transition name="ai-sus-fade">
        <div
          v-if="expanded"
          class="ai-suspended-backdrop"
          aria-hidden="true"
          @click="expanded = false"
        />
      </Transition>

      <div class="ai-suspended-dock">
        <Transition name="ai-sus-panel">
          <div v-if="expanded" class="ai-suspended-panel">
            <AIChat :stock-code="stockCode" floating />
          </div>
        </Transition>

        <button
          type="button"
          class="ai-suspended-ball"
          :class="{ 'is-open': expanded }"
          :aria-expanded="expanded"
          aria-label="AI 诊股"
          @click="expanded = !expanded"
        >
          <svg v-if="!expanded" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2z"/>
            <circle cx="8.5" cy="14.5" r="1.5" fill="currentColor" stroke="none"/>
            <circle cx="15.5" cy="14.5" r="1.5" fill="currentColor" stroke="none"/>
          </svg>
          <svg v-else width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </button>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import AIChat from './AIChat.vue'

const props = defineProps<{ stockCode: string }>()

const expanded = ref(false)

watch(
  () => props.stockCode,
  () => {
    expanded.value = false
  }
)

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') expanded.value = false
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
.ai-suspended-root {
  pointer-events: none;
  position: fixed;
  inset: 0;
  z-index: 10050;
}

.ai-suspended-backdrop {
  pointer-events: auto;
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  backdrop-filter: blur(2px);
}

.ai-suspended-dock {
  pointer-events: none;
  position: fixed;
  right: max(16px, env(safe-area-inset-right));
  bottom: max(20px, env(safe-area-inset-bottom));
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
  z-index: 1;
}

.ai-suspended-panel {
  pointer-events: auto;
  position: relative;
  width: min(400px, calc(100vw - 32px));
  border-radius: 16px;
  border: 1px solid var(--border, rgba(148, 163, 184, 0.35));
  background: var(--bg-primary, #0f172a);
  box-shadow:
    0 25px 50px -12px rgba(0, 0, 0, 0.45),
    0 0 0 1px rgba(255, 255, 255, 0.04);
  overflow: hidden;
}

.ai-suspended-ball {
  pointer-events: auto;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: 2px solid rgba(14, 165, 233, 0.45);
  background: linear-gradient(145deg, #0ea5e9, #6366f1);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow:
    0 12px 28px rgba(14, 165, 233, 0.35),
    0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  transition: transform 0.2s, box-shadow 0.2s;
}

.ai-suspended-ball:hover {
  transform: scale(1.06);
  box-shadow:
    0 16px 36px rgba(14, 165, 233, 0.45),
    0 0 0 1px rgba(255, 255, 255, 0.15) inset;
}

.ai-suspended-ball.is-open {
  background: linear-gradient(145deg, #334155, #1e293b);
  border-color: rgba(148, 163, 184, 0.5);
}

.ai-sus-fade-enter-active,
.ai-sus-fade-leave-active {
  transition: opacity 0.2s ease;
}

.ai-sus-fade-enter-from,
.ai-sus-fade-leave-to {
  opacity: 0;
}

.ai-sus-panel-enter-active,
.ai-sus-panel-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}

.ai-sus-panel-enter-from,
.ai-sus-panel-leave-to {
  opacity: 0;
  transform: translateY(12px) scale(0.98);
}
</style>
