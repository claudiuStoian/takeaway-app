import { BrowserRouter, Navigate, NavLink, Route, Routes } from 'react-router'

import { Button } from '@/components/ui/button'
import { AdminMenuPage } from '@/features/admin/AdminMenuPage'
import { AdminOrdersPage } from '@/features/admin/AdminOrdersPage'
import { AdminRestaurantsPage } from '@/features/admin/AdminRestaurantsPage'
import { AuthProvider, useAuth } from '@/features/auth/AuthContext'
import { LoginPage } from '@/features/auth/LoginPage'
import { RequireUser } from '@/features/auth/RequireUser'
import { MyOrdersPage } from '@/features/orders/MyOrdersPage'
import { MenuPage } from '@/features/shop/MenuPage'
import { RestaurantsPage } from '@/features/shop/RestaurantsPage'

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <div className="mx-auto max-w-5xl p-4">
          <Header />
          <Routes>
            <Route path="/" element={<Navigate to="/login" replace />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/restaurants" element={<RequireUser><RestaurantsPage /></RequireUser>} />
            <Route path="/restaurants/:restaurantId" element={<RequireUser><MenuPage /></RequireUser>} />
            <Route path="/orders" element={<RequireUser><MyOrdersPage /></RequireUser>} />
            <Route path="/admin/orders" element={<RequireUser role="admin"><AdminOrdersPage /></RequireUser>} />
            <Route
              path="/admin/restaurants"
              element={<RequireUser role="admin"><AdminRestaurantsPage /></RequireUser>}
            />
            <Route
              path="/admin/restaurants/:restaurantId/menu"
              element={<RequireUser role="admin"><AdminMenuPage /></RequireUser>}
            />
          </Routes>
        </div>
      </AuthProvider>
    </BrowserRouter>
  )
}

const CUSTOMER_LINKS = [
  { to: '/restaurants', label: 'Restaurants' },
  { to: '/orders', label: 'My orders' },
]

const ADMIN_LINKS = [
  { to: '/admin/orders', label: 'All orders' },
  { to: '/admin/restaurants', label: 'Restaurants' },
]

function Header() {
  const { user, logout } = useAuth()
  const links = user?.role === 'admin' ? ADMIN_LINKS : CUSTOMER_LINKS

  return (
    <header className="mb-6 flex flex-wrap items-center gap-4 border-b pb-3">
      <h1 className="text-xl font-bold">Takeaway</h1>
      {user && (
        <>
          <nav className="flex gap-1">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end
                className={({ isActive }) =>
                  `rounded-md px-3 py-1.5 text-sm ${isActive ? 'bg-secondary' : 'text-muted-foreground hover:text-foreground'}`
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
          <span className="ml-auto text-sm text-muted-foreground">
            {user.full_name} ({user.role})
          </span>
          <Button variant="outline" size="sm" onClick={logout}>
            Log out
          </Button>
        </>
      )}
    </header>
  )
}

export default App
