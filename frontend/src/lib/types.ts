export type UserRole = 'customer' | 'admin'

export type OrderStatus =
  | 'pending'
  | 'accepted'
  | 'out_for_delivery'
  | 'delivered'
  | 'rejected'
  | 'cancelled'

export type User = {
  public_id: string
  email: string
  full_name: string
  role: UserRole
  created_at: string
}

export type Token = {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}

export type Restaurant = {
  id: number
  name: string
  description: string
  cuisine: string
  address: string
  delivery_fee_cents: number
}

export type RestaurantPage = {
  items: Restaurant[]
  next_cursor: string | null
}

export type MenuItem = {
  id: number
  name: string
  description: string | null
  price_cents: number
  is_available: boolean
}

export type MenuCategory = {
  id: number
  name: string
  items: MenuItem[]
}

export type Menu = Restaurant & {
  categories: MenuCategory[]
}

export type AdminMenuItem = MenuItem & {
  category_id: number
  is_archived: boolean
  updated_at: string
}

export type AdminCategory = {
  id: number
  name: string
  position: number
  is_archived: boolean
  items: AdminMenuItem[]
}

export type AdminMenu = Restaurant & {
  is_active: boolean
  categories: AdminCategory[]
}

export type MenuCategoryUpdate = Partial<Pick<AdminCategory, 'name' | 'position' | 'is_archived'>>

export type MenuItemCreate = {
  category_id: number
  name: string
  description?: string | null
  price_cents: number
  is_available?: boolean
}

export type MenuItemUpdate = Partial<MenuItemCreate & { is_archived: boolean }>

export type OrderItemCreate = {
  menu_item_id: number
  quantity: number
}

export type OrderCreate = {
  restaurant_id: number
  items: OrderItemCreate[]
  delivery_address: string
  phone: string
  notes?: string | null
}

export type OrderItem = {
  menu_item_id: number
  name: string
  unit_price_cents: number
  quantity: number
}

export type Order = {
  public_id: string
  restaurant_id: number
  status: OrderStatus
  delivery_address: string
  phone: string
  notes: string | null
  subtotal_cents: number
  delivery_fee_cents: number
  total_cents: number
  items: OrderItem[]
  created_at: string
  updated_at: string
}

export type OrderPage = {
  items: Order[]
  next_cursor: string | null
}

export type UserSummary = {
  public_id: string
  full_name: string
  email: string
  role: UserRole
}

export type AdminOrder = Order & {
  customer: UserSummary
}

export type AdminOrderPage = {
  items: AdminOrder[]
  next_cursor: string | null
}

export type OrderStatusEvent = {
  from_status: OrderStatus | null
  to_status: OrderStatus
  actor: UserSummary
  created_at: string
}
