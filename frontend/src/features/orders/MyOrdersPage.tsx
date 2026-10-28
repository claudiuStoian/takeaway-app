import { useCallback, useEffect, useState } from 'react'

import { ErrorText } from '@/components/ErrorText'
import { OrderItems } from '@/components/OrderItems'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { cancelOrder, fetchMyOrders } from '@/lib/api'
import { errorText, formatCents, formatDate, shortId } from '@/lib/format'
import type { Order } from '@/lib/types'

export function MyOrdersPage() {
  const [orders, setOrders] = useState<Order[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (cursor: string | null) => {
    try {
      const page = await fetchMyOrders(cursor)
      setError(null)
      setOrders((prev) => (cursor ? [...prev, ...page.items] : page.items))
      setNextCursor(page.next_cursor)
    } catch (err) {
      setError(errorText(err))
    }
  }, [])

  useEffect(() => {
    void load(null)
  }, [load])

  async function handleCancel(publicId: string) {
    setError(null)
    try {
      const updated = await cancelOrder(publicId)
      setOrders((prev) => prev.map((order) => (order.public_id === publicId ? updated : order)))
    } catch (err) {
      setError(errorText(err))
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">My orders</h2>
        <Button size="sm" variant="outline" onClick={() => load(null)}>
          Refresh
        </Button>
      </div>
      <ErrorText error={error} />
      {orders.length === 0 && <p className="text-sm text-muted-foreground">No orders yet.</p>}
      {orders.map((order) => (
        <details key={order.public_id} className="rounded-lg border p-3">
          <summary className="flex cursor-pointer items-center gap-3">
            <span className="font-mono text-sm">{shortId(order.public_id)}</span>
            <StatusBadge status={order.status} />
            <span className="text-sm text-muted-foreground">{formatDate(order.created_at)}</span>
            <span className="ml-auto font-medium">{formatCents(order.total_cents)}</span>
            {/* Shown for every status so you can check the API's 409 on non-pending orders. */}
            <Button
              size="xs"
              variant={order.status === 'pending' ? 'destructive' : 'ghost'}
              onClick={(e) => {
                e.preventDefault()
                void handleCancel(order.public_id)
              }}
            >
              Cancel
            </Button>
          </summary>
          <div className="mt-3">
            <OrderItems order={order} />
          </div>
        </details>
      ))}
      {nextCursor && (
        <Button variant="outline" onClick={() => load(nextCursor)} className="self-center">
          Load more
        </Button>
      )}
    </section>
  )
}
