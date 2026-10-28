import { formatCents } from '@/lib/format'
import type { Order } from '@/lib/types'

export function OrderItems({ order }: { order: Order }) {
  return (
    <div className="flex flex-col gap-1 text-sm">
      {order.items.map((item) => (
        <div key={item.menu_item_id} className="flex justify-between">
          <span>
            {item.quantity} × {item.name}
          </span>
          <span>{formatCents(item.unit_price_cents * item.quantity)}</span>
        </div>
      ))}
      <div className="flex justify-between text-muted-foreground">
        <span>Subtotal / delivery</span>
        <span>
          {formatCents(order.subtotal_cents)} / {formatCents(order.delivery_fee_cents)}
        </span>
      </div>
      <p className="text-muted-foreground">
        {order.delivery_address} · {order.phone}
        {order.notes && ` · "${order.notes}"`}
      </p>
    </div>
  )
}
