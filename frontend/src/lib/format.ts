import type { OrderStatus } from '@/lib/types'

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export function formatCents(cents: number): string {
  return usd.format(cents / 100)
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

export function shortId(publicId: string): string {
  return publicId.slice(0, 8)
}

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export const STATUS_COLORS: Record<OrderStatus, string> = {
  pending: 'bg-amber-100 text-amber-800',
  accepted: 'bg-blue-100 text-blue-800',
  out_for_delivery: 'bg-violet-100 text-violet-800',
  delivered: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  cancelled: 'bg-zinc-200 text-zinc-700',
}
