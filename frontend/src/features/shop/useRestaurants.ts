import { useCallback, useEffect, useRef, useState } from 'react'

import { fetchRestaurants } from '@/lib/api'
import { errorText } from '@/lib/format'
import type { Restaurant } from '@/lib/types'

export function useRestaurants(cuisine: string) {
  const [restaurants, setRestaurants] = useState<Restaurant[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const latestRequest = useRef(0)

  const load = useCallback(
    async (cursor: string | null) => {
      // Responses can arrive out of order; only the latest request may update the list.
      const request = ++latestRequest.current
      try {
        const page = await fetchRestaurants(cursor, cuisine)
        if (request !== latestRequest.current) return
        setError(null)
        setRestaurants((prev) => (cursor ? [...prev, ...page.items] : page.items))
        setNextCursor(page.next_cursor)
      } catch (err) {
        if (request === latestRequest.current) setError(errorText(err))
      }
    },
    [cuisine],
  )

  useEffect(() => {
    void load(null)
  }, [load])

  return { restaurants, error, hasMore: nextCursor !== null, loadMore: () => load(nextCursor) }
}

// The API matches cuisine exactly and has no cuisines endpoint, so the options come from one max-size page.
const CUISINE_SCAN_LIMIT = 100

export function useCuisines(): string[] {
  const [cuisines, setCuisines] = useState<string[]>([])

  useEffect(() => {
    fetchRestaurants(null, '', CUISINE_SCAN_LIMIT)
      .then((page) => setCuisines([...new Set(page.items.map((r) => r.cuisine))].sort()))
      .catch(() => setCuisines([]))
  }, [])

  return cuisines
}
