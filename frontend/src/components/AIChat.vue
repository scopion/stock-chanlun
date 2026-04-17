<template>
  <div class="card ai-chat-card">
    <div class="card-header">
      <div class="card-title-row">
        <span class="card-title">AI 诊股</span>
        <div class="ai-badge">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2z"/>
            <circle cx="8.5" cy="14.5" r="1.5"/>
            <circle cx="15.5" cy="14.5" r="1.5"/>
          </svg>
          <span>缠师</span>
        </div>
      </div>
      <button v-if="messages.length > 0" class="clear-btn" @click="clearChat" title="清空对话">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="3 6 5 6 21 6"/>
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
        </svg>
      </button>
    </div>

    <!-- 欢迎语 -->
    <div v-if="messages.length === 0" class="welcome">
      <div class="welcome-icon">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2z"/>
        </svg>
      </div>
      <p class="welcome-title">您好，我是缠师</p>
      <p class="welcome-desc">专注缠论技术分析，诊断股票走势</p>
      <div class="suggestions">
        <button
          v-for="s in suggestions"
          :key="s"
          class="suggestion-chip"
          @click="fillQuestion(s)"
        >{{ s }}</button>
      </div>
    </div>

    <!-- 消息列表 -->
    <div v-else ref="msgListRef" class="message-list">
      <div
        v-for="(msg, idx) in messages"
        :key="idx"
        class="message"
        :class="msg.role"
      >
        <div class="message-avatar">
          <template v-if="msg.role === 'assistant'">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2z"/>
            </svg>
          </template>
          <template v-else>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
          </template>
        </div>
        <div class="message-content">
          <div class="message-text">
            <span v-if="msg.role === 'user'">{{ msg.content }}</span>
            <template v-else>{{ msg.displayText }}{{ msg.streaming ? '▌' : '' }}</template>
          </div>
          <div v-if="msg.error" class="message-error">{{ msg.error }}</div>
        </div>
      </div>

      <!-- 加载指示器 -->
      <div v-if="isLoading" class="message assistant">
        <div class="message-avatar">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2z"/>
          </svg>
        </div>
        <div class="message-content">
          <div class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="input-area">
      <div class="input-wrapper">
        <textarea
          ref="inputRef"
          v-model="inputText"
          class="input-field"
          :placeholder="`询问 ${stockCode} 的走势...`"
          rows="1"
          @keydown.enter.exact.prevent="sendMessage"
          @keydown.enter.shift.exact="null"
          @input="autoResize"
        />
        <button
          class="send-btn"
          :disabled="!inputText.trim() || isLoading"
          @click="sendMessage"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </div>
      <p class="input-hint">Enter 发送，Shift+Enter 换行</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { stockApi } from '@/api/stock'
import toast from '@/composables/useToast'

const props = defineProps<{ stockCode: string }>()

interface Message {
  role: 'user' | 'assistant'
  content: string
  displayText: string
  streaming: boolean
  error?: string
}

const messages = ref<Message[]>([])
const inputText = ref('')
const isLoading = ref(false)
const msgListRef = ref<HTMLElement>()
const inputRef = ref<HTMLTextAreaElement>()
const sessionId = ref(`session_${props.stockCode}_${Date.now()}`)

const suggestions = [
  '分析当前走势',
  '现在是买点吗？',
  '压力位在哪？',
  '止损位建议',
  '可以买入吗？',
]

function fillQuestion(q: string) {
  inputText.value = `${q}`
  inputRef.value?.focus()
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isLoading.value) return

  // 添加用户消息
  messages.value.push({
    role: 'user',
    content: text,
    displayText: text,
    streaming: false,
  })
  inputText.value = ''
  await nextTick()
  scrollToBottom()

  // 添加空的 AI 消息占位
  const aiMsgIdx = messages.value.length
  messages.value.push({
    role: 'assistant',
    content: '',
    displayText: '',
    streaming: true,
  })
  isLoading.value = true

  try {
    let fullText = ''
    const stream = stockApi.aiDiagnosisStream(props.stockCode, text, sessionId.value, 'deepseek')

    for await (const token of stream) {
      fullText += token
      messages.value[aiMsgIdx] = {
        role: 'assistant',
        content: fullText,
        displayText: fullText,
        streaming: true,
      }
      await nextTick()
      scrollToBottom()
    }

    // 打字完成
    messages.value[aiMsgIdx] = {
      role: 'assistant',
      content: fullText,
      displayText: fullText,
      streaming: false,
    }
  } catch (err: any) {
    messages.value[aiMsgIdx] = {
      role: 'assistant',
      content: '',
      displayText: '',
      streaming: false,
      error: err.message || '诊断失败，请重试',
    }
    toast.error('AI 诊断请求失败，请重试')
  } finally {
    isLoading.value = false
    await nextTick()
    scrollToBottom()
  }
}

function scrollToBottom() {
  if (msgListRef.value) {
    msgListRef.value.scrollTop = msgListRef.value.scrollHeight
  }
}

function autoResize(e: Event) {
  const el = e.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 120) + 'px'
}

function clearChat() {
  messages.value = []
  sessionId.value = `session_${props.stockCode}_${Date.now()}`
}
</script>

<style scoped>
.ai-chat-card {
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  max-height: 320px;
  overflow: hidden;
  flex-shrink: 0;
}

/* Header */
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  flex-shrink: 0;
}

.card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-title { font-size: 0.85rem; font-weight: 700; color: var(--text-primary); }

.ai-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.15), rgba(139, 92, 246, 0.15));
  border: 1px solid rgba(14, 165, 233, 0.3);
  border-radius: 999px;
  font-size: 0.65rem;
  color: var(--accent-blue);
  font-weight: 600;
}

.clear-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
}

.clear-btn:hover {
  color: var(--accent-red);
  border-color: rgba(239, 68, 68, 0.4);
  background: rgba(239, 68, 68, 0.08);
}

/* Welcome */
.welcome {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 8px 4px;
  min-height: 0;
}

.welcome-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.15), rgba(139, 92, 246, 0.15));
  border: 1px solid rgba(14, 165, 233, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-blue);
  margin-bottom: 8px;
}

.welcome-title {
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 2px;
}

.welcome-desc {
  font-size: 0.68rem;
  color: var(--text-muted);
  margin: 0 0 10px;
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: center;
}

.suggestion-chip {
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 0.68rem;
  cursor: pointer;
  transition: all 0.15s;
}

.suggestion-chip:hover {
  border-color: var(--accent-blue);
  color: var(--accent-blue);
  background: rgba(14, 165, 233, 0.08);
}

/* Message List */
.message-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 0;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
  min-height: 0;
}

.message {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  color: var(--text-muted);
}

.message.assistant .message-avatar {
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.15), rgba(139, 92, 246, 0.1));
  border-color: rgba(14, 165, 233, 0.3);
  color: var(--accent-blue);
}

.message-content {
  max-width: 85%;
  flex-shrink: 0;
}

.message.user .message-content {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.message-text {
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 0.8125rem;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-primary);
}

.message.user .message-text {
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.15), rgba(14, 165, 233, 0.1));
  border: 1px solid rgba(14, 165, 233, 0.2);
  border-bottom-right-radius: 4px;
}

.message.assistant .message-text {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}

.message-error {
  margin-top: 4px;
  font-size: 0.72rem;
  color: var(--accent-red);
  padding: 4px 8px;
  background: rgba(239, 68, 68, 0.08);
  border-radius: 4px;
}

/* Typing indicator */
.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 4px 0;
}

.typing-indicator span {
  width: 6px;
  height: 6px;
  background: var(--text-muted);
  border-radius: 50%;
  animation: typing 1.2s infinite;
}

.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 100% { opacity: 0.3; transform: translateY(0); }
  50% { opacity: 1; transform: translateY(-4px); }
}

/* Input */
.input-area {
  flex-shrink: 0;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px;
  transition: border-color 0.15s;
}

.input-wrapper:focus-within {
  border-color: rgba(14, 165, 233, 0.5);
}

.input-field {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  font-size: 0.8125rem;
  line-height: 1.5;
  color: var(--text-primary);
  resize: none;
  max-height: 120px;
  font-family: inherit;
}

.input-field::placeholder { color: var(--text-muted); }

.send-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: linear-gradient(135deg, #0ea5e9, #0284c7);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  filter: brightness(1.1);
  transform: scale(1.05);
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.input-hint {
  font-size: 0.65rem;
  color: var(--text-muted);
  margin: 4px 0 0;
  text-align: center;
}
</style>
