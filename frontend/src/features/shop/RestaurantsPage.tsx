import { useState } from 'react'
import { Link } from 'react-router'

import { ErrorText } from '@/components/ErrorText'
import { Button } from '@/components/ui/button'
import { formatCents } from '@/lib/format'

import { useCuisines, useRestaurants } from './useRestaurants'

export function RestaurantsPage() {
  const [cuisine, setCuisine] = useState('')
  const { restaurants, error, hasMore, loadMore } = useRestaurants(cuisine)
  const cuisines = useCuisines()

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <h2 className="text-lg font-semibold">Restaurants</h2>
        <select
          className="ml-auto h-9 rounded-md border px-2 text-sm"
          value={cuisine}
          onChange={(e) => setCuisine(e.target.value)}
        >
          <option value="">All cuisines</option>
          {cuisines.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>
      <ErrorText error={error} />
      <ul className="grid gap-3 sm:grid-cols-2">
        {restaurants.map((restaurant) => (
          <li key={restaurant.id}>
            <Link
              to={`/restaurants/${restaurant.id}`}
              className="block rounded-lg border p-4 hover:bg-muted"
            >
              <div className="flex justify-between">
                <span className="font-medium">{restaurant.name}</span>
                <span className="text-xs text-muted-foreground">{restaurant.cuisine}</span>
              </div>
              <p className="text-sm text-muted-foreground">{restaurant.description}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {restaurant.address} · delivery {formatCents(restaurant.delivery_fee_cents)}
              </p>
            </Link>
          </li>
        ))}
      </ul>
      {hasMore && (
        <Button variant="outline" onClick={loadMore} className="self-center">
          Load more
        </Button>
      )}
    </section>
  )
}
