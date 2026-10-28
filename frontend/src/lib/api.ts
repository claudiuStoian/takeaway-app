import type {
  AdminCategory,
  AdminMenu,
  AdminMenuItem,
  AdminOrder,
  AdminOrderPage,
  Menu,
  MenuCategoryUpdate,
  MenuItemCreate,
  MenuItemUpdate,
  Order,
  OrderCreate,
  OrderPage,
  OrderStatus,
  OrderStatusEvent,
  RestaurantPage,
  Token,
  User,
} from '@/lib/types'

const BASE = '/api/v1'
const TOKEN_KEY = 'takeaway_token'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null) {
  if (token) sessionStorage.setItem(TOKEN_KEY, token)
  else sessionStorage.removeItem(TOKEN_KEY)
}

export async function login(email: string, password: string): Promise<Token> {
  return request<Token>('POST', '/auth/login', { email, password })
}

export async function signup(email: string, password: string, fullName: string): Promise<User> {
  return request<User>('POST', '/auth/signup', { email, password, full_name: fullName })
}

export async function fetchMe(): Promise<User> {
  return request<User>('GET', '/me')
}

export async function fetchRestaurants(
  cursor: string | null,
  cuisine: string,
  limit: number | null = null,
): Promise<RestaurantPage> {
  return request<RestaurantPage>(
    'GET',
    `/restaurants?${query({ cursor, cuisine, limit: limit ? String(limit) : null })}`,
  )
}

export async function fetchMenu(restaurantId: number): Promise<Menu> {
  return request<Menu>('GET', `/restaurants/${restaurantId}/menu`)
}

export async function placeOrder(idempotencyKey: string, order: OrderCreate): Promise<Order> {
  return request<Order>('POST', '/orders', order, { 'Idempotency-Key': idempotencyKey })
}

export async function fetchMyOrders(cursor: string | null): Promise<OrderPage> {
  return request<OrderPage>('GET', `/orders?${query({ cursor })}`)
}

export async function cancelOrder(publicId: string): Promise<Order> {
  return request<Order>('POST', `/orders/${publicId}/cancel`)
}

export async function fetchAdminOrders(
  cursor: string | null,
  status: string,
  restaurantId: string,
): Promise<AdminOrderPage> {
  return request<AdminOrderPage>(
    'GET',
    `/admin/orders?${query({ cursor, status, restaurant_id: restaurantId })}`,
  )
}

export async function changeOrderStatus(publicId: string, to: OrderStatus): Promise<AdminOrder> {
  return request<AdminOrder>('POST', `/admin/orders/${publicId}/status`, { to })
}

export async function fetchOrderHistory(publicId: string): Promise<OrderStatusEvent[]> {
  return request<OrderStatusEvent[]>('GET', `/admin/orders/${publicId}/history`)
}

export async function fetchAdminMenu(restaurantId: number): Promise<AdminMenu> {
  return request<AdminMenu>('GET', `/admin/restaurants/${restaurantId}/menu`)
}

export async function createCategory(restaurantId: number, name: string): Promise<AdminCategory> {
  return request<AdminCategory>('POST', `/admin/restaurants/${restaurantId}/categories`, { name })
}

export async function updateCategory(
  restaurantId: number,
  categoryId: number,
  changes: MenuCategoryUpdate,
): Promise<AdminCategory> {
  return request<AdminCategory>(
    'PATCH',
    `/admin/restaurants/${restaurantId}/categories/${categoryId}`,
    changes,
  )
}

export async function createItem(restaurantId: number, item: MenuItemCreate): Promise<AdminMenuItem> {
  return request<AdminMenuItem>('POST', `/admin/restaurants/${restaurantId}/items`, item)
}

export async function updateItem(
  restaurantId: number,
  itemId: number,
  changes: MenuItemUpdate,
): Promise<AdminMenuItem> {
  return request<AdminMenuItem>('PATCH', `/admin/restaurants/${restaurantId}/items/${itemId}`, changes)
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  headers: Record<string, string> = {},
): Promise<T> {
  const token = getToken()
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      ...(body !== undefined && { 'Content-Type': 'application/json' }),
      ...(token && { Authorization: `Bearer ${token}` }),
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    throw new ApiError(res.status, await errorMessage(res))
  }
  return res.json() as Promise<T>
}

async function errorMessage(res: Response): Promise<string> {
  const prefix = `${res.status} ${res.statusText}`
  try {
    const { detail } = await res.json()
    if (typeof detail === 'string') return `${prefix}: ${detail}`
    // FastAPI validation errors: a list of { loc, msg }
    if (Array.isArray(detail)) {
      return `${prefix}: ${detail.map((d) => `${d.loc?.slice(1).join('.')}: ${d.msg}`).join('; ')}`
    }
  } catch {
    // non-JSON body (e.g. Nginx 429 page)
  }
  return prefix
}

function query(params: Record<string, string | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value)
  }
  return search.toString()
}
