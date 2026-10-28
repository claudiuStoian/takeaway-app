import { STATUS_COLORS } from '@/lib/format'
import type { OrderStatus } from '@/lib/types'

export function StatusBadge({ status }: { status: OrderStatus }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[status]}`}>
      {status.replaceAll('_', ' ')}
    </span>
  )
}
