/**
 * 格式化工具 Composable
 */

/**
 * 格式化价格
 */
export function usePriceFormatter() {
  function formatPrice(price: number | null | undefined, decimals = 2): string {
    if (price == null || Number.isNaN(price) || price <= 0) return '—'
    return price.toFixed(decimals)
  }

  /**
   * 格式化涨跌额
   */
  function formatChange(change: number | null | undefined, decimals = 2): string {
    if (change == null || Number.isNaN(change)) return '—'
    const sign = change > 0 ? '+' : ''
    return `${sign}${change.toFixed(decimals)}`
  }

  /**
   * 格式化涨跌幅
   */
  function formatChangePct(pct: number | null | undefined, decimals = 2): string {
    if (pct == null || Number.isNaN(pct)) return '—'
    const sign = pct > 0 ? '+' : ''
    return `${sign}${pct.toFixed(decimals)}%`
  }

  return { formatPrice, formatChange, formatChangePct }
}

/**
 * 格式化成交量
 */
export function useVolumeFormatter() {
  function formatVolume(volume: number | null | undefined): string {
    if (volume == null || Number.isNaN(volume) || volume <= 0) return '—'
    if (volume >= 1e8) return (volume / 1e8).toFixed(2) + '亿'
    if (volume >= 1e4) return (volume / 1e4).toFixed(2) + '万'
    return String(Math.round(volume))
  }

  function formatAmount(amount: number | null | undefined): string {
    if (amount == null || Number.isNaN(amount) || amount <= 0) return '—'
    if (amount >= 1e8) return (amount / 1e8).toFixed(2) + ' 亿'
    if (amount >= 1e4) return (amount / 1e4).toFixed(2) + ' 万'
    return amount.toFixed(0)
  }

  return { formatVolume, formatAmount }
}

/**
 * 格式化日期时间
 */
export function useDateFormatter() {
  function formatDateTime(iso: string): string {
    if (!iso) return ''
    try {
      const d = new Date(iso)
      if (isNaN(d.getTime())) return iso
      const mm = String(d.getMonth() + 1).padStart(2, '0')
      const dd = String(d.getDate()).padStart(2, '0')
      const hh = String(d.getHours()).padStart(2, '0')
      const mi = String(d.getMinutes()).padStart(2, '0')
      return `${mm}-${dd} ${hh}:${mi}`
    } catch {
      return iso
    }
  }

  function formatDate(iso: string): string {
    if (!iso) return ''
    try {
      const d = new Date(iso)
      if (isNaN(d.getTime())) return iso
      const mm = String(d.getMonth() + 1).padStart(2, '0')
      const dd = String(d.getDate()).padStart(2, '0')
      return `${mm}-${dd}`
    } catch {
      return iso
    }
  }

  function formatTime(iso: string): string {
    if (!iso) return ''
    try {
      const d = new Date(iso)
      if (isNaN(d.getTime())) return iso
      const hh = String(d.getHours()).padStart(2, '0')
      const mi = String(d.getMinutes()).padStart(2, '0')
      return `${hh}:${mi}`
    } catch {
      return iso
    }
  }

  function formatFullDate(iso: string): string {
    if (!iso) return ''
    try {
      const d = new Date(iso)
      if (isNaN(d.getTime())) return iso
      const yyyy = d.getFullYear()
      const mm = String(d.getMonth() + 1).padStart(2, '0')
      const dd = String(d.getDate()).padStart(2, '0')
      return `${yyyy}-${mm}-${dd}`
    } catch {
      return iso
    }
  }

  return { formatDateTime, formatDate, formatTime, formatFullDate }
}

/**
 * 格式化置信度
 */
export function useConfidenceFormatter() {
  function formatConfidence(conf: number | null | undefined): string {
    if (conf == null || Number.isNaN(conf)) return '—'
    return `${(conf * 100).toFixed(0)}%`
  }

  function confidenceColor(conf: number): string {
    if (conf >= 0.75) return 'var(--accent-green)'
    if (conf >= 0.5) return 'var(--accent-amber)'
    return 'var(--accent-red)'
  }

  return { formatConfidence, confidenceColor }
}