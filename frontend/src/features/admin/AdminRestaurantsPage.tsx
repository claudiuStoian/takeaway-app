import { Link } from 'react-router'

import { ErrorText } from '@/components/ErrorText'
import { Button } from '@/components/ui/button'
import { useRestaurants } from '@/features/shop/useRestaurants'
import { formatCents } from '@/lib/format'

export function AdminRestaurantsPage() {
  const { restaurants, error, hasMore, loadMore } = useRestaurants('')

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">Restaurants</h2>
      {/* The API has no admin restaurant list; this is the public one, so inactive restaurants are missing. */}
      <p className="text-xs text-muted-foreground">Active restaurants only (public list).</p>
      <ErrorText error={error} />
      <table className="w-full text-sm">
        <thead className="text-left text-muted-foreground">
          <tr className="border-b">
            <th className="py-2">Id</th>
            <th>Name</th>
            <th>Cuisine</th>
            <th>Delivery</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {restaurants.map((restaurant) => (
            <tr key={restaurant.id} className="border-b">
              <td className="py-2">{restaurant.id}</td>
              <td>{restaurant.name}</td>
              <td>{restaurant.cuisine}</td>
              <td>{formatCents(restaurant.delivery_fee_cents)}</td>
              <td className="text-right">
                <Link to={`/admin/restaurants/${restaurant.id}/menu`} className="underline">
                  Edit menu
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {hasMore && (
        <Button variant="outline" onClick={loadMore} className="self-center">
          Load more
        </Button>
      )}
    </section>
  )
}
