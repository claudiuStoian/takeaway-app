import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router'

import { ErrorText } from '@/components/ErrorText'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { fetchMenu, placeOrder } from '@/lib/api'
import { errorText, formatCents, shortId } from '@/lib/format'
import type { Menu, MenuItem, Order, OrderCreate } from '@/lib/types'

type Cart = Record<number, number>

type Placed = {
  order: Order
  idempotencyKey: string
  body: OrderCreate
  isRepeat: boolean
}

export function MenuPage() {
  const restaurantId = Number(useParams().restaurantId)
  const [menu, setMenu] = useState<Menu | null>(null)
  const [cart, setCart] = useState<Cart>({})
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    fetchMenu(restaurantId)
      .then((menu) => {
        if (!ignore) setMenu(menu)
      })
      .catch((err) => {
        if (!ignore) setError(errorText(err))
      })
    return () => {
      ignore = true
    }
  }, [restaurantId])

  if (!menu) return <ErrorText error={error} />

  const items = menu.categories.flatMap((category) => category.items)

  function setQuantity(itemId: number, quantity: number) {
    setCart((prev) => {
      const next = { ...prev }
      if (quantity > 0) next[itemId] = quantity
      else delete next[itemId]
      return next
    })
  }

  return (
    <div className="grid gap-6 md:grid-cols-[1fr_20rem]">
      <section className="flex flex-col gap-4">
        <div>
          <Link to="/restaurants" className="text-sm text-muted-foreground hover:text-foreground">
            ← Restaurants
          </Link>
          <h2 className="text-lg font-semibold">{menu.name}</h2>
          <p className="text-sm text-muted-foreground">{menu.description}</p>
        </div>
        {menu.categories.map((category) => (
          <div key={category.id}>
            <h3 className="mb-2 font-medium">{category.name}</h3>
            <ul className="flex flex-col gap-2">
              {category.items.map((item) => (
                <MenuItemRow
                  key={item.id}
                  item={item}
                  quantity={cart[item.id] ?? 0}
                  onQuantityChange={(quantity) => setQuantity(item.id, quantity)}
                />
              ))}
            </ul>
          </div>
        ))}
      </section>
      <Checkout menu={menu} items={items} cart={cart} onPlaced={() => setCart({})} />
    </div>
  )
}

function MenuItemRow({
  item,
  quantity,
  onQuantityChange,
}: {
  item: MenuItem
  quantity: number
  onQuantityChange: (quantity: number) => void
}) {
  return (
    <li className={`flex items-center gap-3 rounded-md border p-3 ${item.is_available ? '' : 'opacity-50'}`}>
      <div className="flex-1">
        <div className="font-medium">
          {item.name} {!item.is_available && <span className="text-xs">(unavailable)</span>}
        </div>
        {item.description && <p className="text-sm text-muted-foreground">{item.description}</p>}
      </div>
      <span className="text-sm">{formatCents(item.price_cents)}</span>
      {/* Unavailable items stay clickable on purpose: lets you check the API rejects them. */}
      <div className="flex items-center gap-1">
        <Button size="xs" variant="outline" onClick={() => onQuantityChange(quantity - 1)} disabled={!quantity}>
          −
        </Button>
        <span className="w-6 text-center text-sm">{quantity}</span>
        <Button size="xs" variant="outline" onClick={() => onQuantityChange(quantity + 1)}>
          +
        </Button>
      </div>
    </li>
  )
}

function Checkout({
  menu,
  items,
  cart,
  onPlaced,
}: {
  menu: Menu
  items: MenuItem[]
  cart: Cart
  onPlaced: () => void
}) {
  const [deliveryAddress, setDeliveryAddress] = useState('')
  const [phone, setPhone] = useState('')
  const [notes, setNotes] = useState('')
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID())
  const [placed, setPlaced] = useState<Placed | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isBusy, setIsBusy] = useState(false)

  const lines = items.filter((item) => cart[item.id])
  // Display only: the server computes the real total from current prices.
  const subtotalCents = lines.reduce((sum, item) => sum + item.price_cents * (cart[item.id] ?? 0), 0)

  async function submit(key: string, body: OrderCreate) {
    setError(null)
    setIsBusy(true)
    try {
      const order = await placeOrder(key, body)
      setPlaced({ order, idempotencyKey: key, body, isRepeat: placed?.order.public_id === order.public_id })
      setIdempotencyKey(crypto.randomUUID())
      onPlaced()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setIsBusy(false)
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    void submit(idempotencyKey, {
      restaurant_id: menu.id,
      items: lines.map((item) => ({ menu_item_id: item.id, quantity: cart[item.id] ?? 0 })),
      delivery_address: deliveryAddress,
      phone,
      notes: notes || null,
    })
  }

  return (
    <aside className="flex flex-col gap-3 self-start rounded-lg border p-4">
      <h3 className="font-medium">Your order</h3>
      {lines.length === 0 && <p className="text-sm text-muted-foreground">Nothing selected yet.</p>}
      {lines.map((item) => (
        <div key={item.id} className="flex justify-between text-sm">
          <span>
            {cart[item.id]} × {item.name}
          </span>
          <span>{formatCents(item.price_cents * (cart[item.id] ?? 0))}</span>
        </div>
      ))}
      <div className="flex justify-between border-t pt-2 text-sm text-muted-foreground">
        <span>Delivery</span>
        <span>{formatCents(menu.delivery_fee_cents)}</span>
      </div>
      <div className="flex justify-between font-medium">
        <span>Estimated total</span>
        <span>{formatCents(subtotalCents + menu.delivery_fee_cents)}</span>
      </div>
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <Input placeholder="Delivery address" value={deliveryAddress} onChange={(e) => setDeliveryAddress(e.target.value)} />
        <Input placeholder="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
        <Input placeholder="Notes (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} />
        <p className="truncate text-xs text-muted-foreground" title={idempotencyKey}>
          Idempotency-Key: {idempotencyKey}
        </p>
        <Button type="submit" disabled={isBusy}>
          Place order
        </Button>
      </form>
      <ErrorText error={error} />
      {placed && (
        <div className="flex flex-col gap-2 rounded-md bg-muted p-3 text-sm">
          <div className="flex items-center justify-between">
            <span>
              {placed.isRepeat ? 'Same order returned' : 'Order placed'}: {shortId(placed.order.public_id)}
            </span>
            <StatusBadge status={placed.order.status} />
          </div>
          <span>Server total: {formatCents(placed.order.total_cents)}</span>
          <Button
            size="sm"
            variant="outline"
            disabled={isBusy}
            onClick={() => submit(placed.idempotencyKey, placed.body)}
          >
            Resend with same key
          </Button>
          <Link to="/orders" className="text-xs underline">
            See my orders
          </Link>
        </div>
      )}
    </aside>
  )
}
