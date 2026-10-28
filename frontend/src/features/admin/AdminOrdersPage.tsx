import { useCallback, useEffect, useState } from 'react'

import { ErrorText } from '@/components/ErrorText'
import { OrderItems } from '@/components/OrderItems'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { changeOrderStatus, fetchAdminOrders, fetchOrderHistory } from '@/lib/api'
import { errorText, formatCents, formatDate, shortId } from '@/lib/format'
import type { AdminOrder, OrderStatus, OrderStatusEvent } from '@/lib/types'

const STATUSES: OrderStatus[] = [
  'pending',
  'accepted',
  'out_for_delivery',
  'delivered',
  'rejected',
  'cancelled',
]

export function AdminOrdersPage() {
  const [status, setStatus] = useState('')
  const [restaurantId, setRestaurantId] = useState('')
  const [orders, setOrders] = useState<AdminOrder[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(
    async (cursor: string | null) => {
      try {
        const page = await fetchAdminOrders(cursor, status, restaurantId)
        setError(null)
        setOrders((prev) => (cursor ? [...prev, ...page.items] : page.items))
        setNextCursor(page.next_cursor)
      } catch (err) {
        setError(errorText(err))
      }
    },
    [status, restaurantId],
  )

  useEffect(() => {
    void load(null)
  }, [load])

  function replaceOrder(updated: AdminOrder) {
    setOrders((prev) => prev.map((order) => (order.public_id === updated.public_id ? updated : order)))
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">All orders</h2>
        <select
          className="ml-auto h-9 rounded-md border px-2 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">Any status</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <Input
          className="max-w-36"
          placeholder="Restaurant id"
          value={restaurantId}
          onChange={(e) => setRestaurantId(e.target.value.trim())}
        />
        <Button size="sm" variant="outline" onClick={() => load(null)}>
          Refresh
        </Button>
      </div>
      <ErrorText error={error} />
      {orders.length === 0 && <p className="text-sm text-muted-foreground">No orders.</p>}
      {orders.map((order) => (
        <AdminOrderRow key={order.public_id} order={order} onChanged={replaceOrder} />
      ))}
      {nextCursor && (
        <Button variant="outline" onClick={() => load(nextCursor)} className="self-center">
          Load more
        </Button>
      )}
    </section>
  )
}

function AdminOrderRow({ order, onChanged }: { order: AdminOrder; onChanged: (order: AdminOrder) => void }) {
  const [history, setHistory] = useState<OrderStatusEvent[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function moveTo(to: OrderStatus) {
    setError(null)
    try {
      onChanged(await changeOrderStatus(order.public_id, to))
      setHistory(null)
    } catch (err) {
      setError(errorText(err))
    }
  }

  async function loadHistory() {
    setError(null)
    try {
      setHistory(await fetchOrderHistory(order.public_id))
    } catch (err) {
      setError(errorText(err))
    }
  }

  return (
    <details className="rounded-lg border p-3" onToggle={(e) => e.currentTarget.open && !history && loadHistory()}>
      <summary className="flex cursor-pointer flex-wrap items-center gap-3">
        <span className="font-mono text-sm">{shortId(order.public_id)}</span>
        <StatusBadge status={order.status} />
        <span className="text-sm">{order.customer.full_name}</span>
        <span className="text-sm text-muted-foreground">restaurant #{order.restaurant_id}</span>
        <span className="text-sm text-muted-foreground">{formatDate(order.created_at)}</span>
        <span className="ml-auto font-medium">{formatCents(order.total_cents)}</span>
      </summary>
      <div className="mt-3 flex flex-col gap-3">
        <OrderItems order={order} />
        {/* Every target is offered, not only legal ones, so illegal moves can be checked for 409. */}
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-xs text-muted-foreground">Move to:</span>
          {STATUSES.filter((s) => s !== order.status).map((s) => (
            <Button key={s} size="xs" variant="outline" onClick={() => moveTo(s)}>
              {s.replaceAll('_', ' ')}
            </Button>
          ))}
        </div>
        <ErrorText error={error} />
        {history && (
          <ol className="flex flex-col gap-1 text-xs text-muted-foreground">
            {history.map((event) => (
              <li key={event.created_at + event.to_status}>
                {formatDate(event.created_at)}: {event.from_status ?? 'created'} → {event.to_status} by{' '}
                {event.actor.full_name} ({event.actor.role})
              </li>
            ))}
          </ol>
        )}
      </div>
    </details>
  )
}
