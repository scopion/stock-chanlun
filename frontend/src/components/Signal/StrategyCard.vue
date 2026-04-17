<template>
  <div class="card strategy-card">
    <div class="card-header">
      <span class="card-title">AI 策略建议</span>
      <div class="header-right">
        <span v-if="updatedAt" class="card-time">{{ updatedAt }}</span>
        <span v-if="signal" class="risk-badge" :class="riskClass">{{ signal.risk_level }}风险</span>
      </div>
    </div>

    <div v-if="!signal" class="empty-strategy">
      <div class="skeleton" style="height: 100px; border-radius: 8px;" />
    </div>

    <div v-else class="strategy-content">
      <!-- Direction -->
      <div class="direction-block" :class="dirClass">
        <div class="direction-main">
          <span class="dir-arrow">{{ dirSymbol }}</span>
          <span class="dir-text">{{ signal.direction }}</span>
        </div>
        <div class="dir-confidence">
          <div class="confidence-bar">
            <div
              class="confidence-fill"
              :style="{
                width: (signal.confidence * 100) + '%',
                background: confColor(signal.confidence)
              }"
            />
          </div>
          <span class="conf-pct mono">{{ (signal.confidence * 100).toFixed(0) }}%</span>
        </div>
      </div>

      <!-- Price levels -->
      <div class="price-levels">
        <div class="level-row">
          <span class="level-label">入场价</span>
          <span class="level-value mono">{{ signal.entry_price?.toFixed(2) || '—' }}</span>
        </div>
        <div class="level-row">
          <span class="level-label">止盈价</span>
          <span class="level-value mono price-up">{{ signal.take_profit?.toFixed(2) || '—' }}</span>
        </div>
        <div class="level-row">
          <span class="level-label">止损价</span>
          <span class="level-value mono price-down">{{ signal.stop_loss?.toFixed(2) || '—' }}</span>
        </div>
      </div>

      <!-- Holding period -->
      <div class="period-row">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
        </svg>
        <span>操作窗口: {{ signal.holding_period }}</span>
      </div>

      <!-- Divergence -->
      <div v-if="signal.divergence" class="divergence-block">
        <div class="divergence-header">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
          </svg>
          <span>背驰判断</span>
          <span class="divergence-prob mono">{{ (signal.divergence.probability * 100).toFixed(0) }}%</span>
        </div>
        <div class="divergence-desc">{{ signal.divergence.description }}</div>
      </div>

      <!-- Resonance -->
      <div v-if="signal.resonance?.共振" class="resonance-block">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
        </svg>
        <span>多级别共振: {{ signal.resonance.levels?.join(' + ') }}</span>
      </div>

      <!-- Description -->
      <div class="strategy-desc">{{ signal.description }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AISignal } from '../../api/stock'

const props = defineProps<{ signal: AISignal | null; updatedAt?: string | null }>()

const dirClass = computed(() => {
  if (!props.signal) return ''
  if (props.signal.direction === '买入') return 'dir-buy'
  if (props.signal.direction === '卖出') return 'dir-sell'
  return 'dir-wait'
})

const dirSymbol = computed(() => {
  if (!props.signal) return '—'
  if (props.signal.direction === '买入') return '▲'
  if (props.signal.direction === '卖出') return '▼'
  return '◆'
})

const riskClass = computed(() => {
  if (!props.signal) return ''
  if (props.signal.risk_level === '低') return 'risk-low'
  if (props.signal.risk_level === '中') return 'risk-mid'
  return 'risk-high'
})

function confColor(c: number) {
  if (c >= 0.75) return 'var(--accent-green)'
  if (c >= 0.5) return 'var(--accent-amber)'
  return 'var(--accent-red)'
}
</script>

<style scoped>
.strategy-card { padding: 14px; }
.card-header { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.header-right { display: flex; align-items: center; gap: 6px; }
.card-time { font-size: 0.65rem; color: var(--text-muted); font-family: var(--font-mono); }

.risk-badge {
  font-size: 0.7rem;
  padding: 3px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.risk-low { background: rgba(63,185,80,0.15); color: var(--accent-green); }
.risk-mid { background: rgba(210,153,34,0.15); color: var(--accent-amber); }
.risk-high { background: rgba(248,81,73,0.15); color: var(--accent-red); }

.empty-strategy { padding: 8px 0; }

.strategy-content { display: flex; flex-direction: column; gap: 12px; }

.direction-block {
  padding: 14px;
  border-radius: 10px;
  text-align: center;
}
.dir-buy { background: rgba(63,185,80,0.1); border: 1px solid rgba(63,185,80,0.2); }
.dir-sell { background: rgba(248,81,73,0.1); border: 1px solid rgba(248,81,73,0.2); }
.dir-wait { background: rgba(210,153,34,0.1); border: 1px solid rgba(210,153,34,0.2); }

.direction-main { display: flex; align-items: center; justify-content: center; gap: 8px; margin-bottom: 8px; }
.dir-arrow { font-size: 1.4rem; }
.dir-text { font-size: 1.3rem; font-weight: 700; }
.dir-buy .dir-text { color: var(--accent-green); }
.dir-sell .dir-text { color: var(--accent-red); }
.dir-wait .dir-text { color: var(--accent-amber); }

.dir-confidence { display: flex; align-items: center; gap: 8px; justify-content: center; }
.conf-pct { font-size: 0.8rem; color: var(--text-secondary); }

.price-levels { display: flex; flex-direction: column; gap: 6px; }
.level-row { display: flex; justify-content: space-between; align-items: center; }
.level-label { font-size: 0.8rem; color: var(--text-secondary); }
.level-value { font-size: 0.9rem; font-weight: 600; }

.period-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  color: var(--text-secondary);
  padding: 8px 0;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}

.divergence-block {
  padding: 8px 10px;
  background: rgba(88,166,255,0.08);
  border: 1px solid rgba(88,166,255,0.15);
  border-radius: 8px;
}
.divergence-header { display: flex; align-items: center; gap: 6px; font-size: 0.8rem; font-weight: 600; margin-bottom: 4px; color: var(--accent-blue); }
.divergence-prob { color: var(--accent-blue); }
.divergence-desc { font-size: 0.75rem; color: var(--text-secondary); }

.resonance-block {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  color: var(--accent-purple);
  padding: 6px 10px;
  background: rgba(188,140,255,0.08);
  border: 1px solid rgba(188,140,255,0.15);
  border-radius: 8px;
}

.strategy-desc {
  font-size: 0.78rem;
  color: var(--text-secondary);
  line-height: 1.6;
  padding: 10px;
  background: var(--bg-secondary);
  border-radius: 8px;
}
</style>