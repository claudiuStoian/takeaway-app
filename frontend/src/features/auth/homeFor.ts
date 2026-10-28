import type { UserRole } from '@/lib/types'

export function homeFor(role: UserRole): string {
  return role === 'admin' ? '/admin/orders' : '/restaurants'
}
