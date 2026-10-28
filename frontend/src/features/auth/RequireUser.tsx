import type { ReactNode } from 'react'
import { Navigate } from 'react-router'

import type { UserRole } from '@/lib/types'

import { useAuth } from './AuthContext'
import { homeFor } from './homeFor'

/** UI gating only — the API is what actually enforces roles. */
export function RequireUser({ role, children }: { role?: UserRole; children: ReactNode }) {
  const { user, isLoading } = useAuth()

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>
  if (!user) return <Navigate to="/login" replace />
  if (role && user.role !== role) return <Navigate to={homeFor(user.role)} replace />
  return children
}
