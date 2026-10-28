import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'

import { ErrorText } from '@/components/ErrorText'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { createCategory, createItem, fetchAdminMenu, updateCategory, updateItem } from '@/lib/api'
import { errorText } from '@/lib/format'
import type { AdminCategory, AdminMenu, AdminMenuItem, MenuItemUpdate } from '@/lib/types'

export function AdminMenuPage() {
  const restaurantId = Number(useParams().restaurantId)
  const [menu, setMenu] = useState<AdminMenu | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    try {
      setMenu(await fetchAdminMenu(restaurantId))
    } catch (err) {
      setError(errorText(err))
    }
  }, [restaurantId])

  useEffect(() => {
    void reload()
  }, [reload])

  /** Runs one write, shows its error inline, and reloads the menu so the page mirrors the DB. */
  async function run(write: () => Promise<unknown>): Promise<boolean> {
    setError(null)
    try {
      await write()
      await reload()
      return true
    } catch (err) {
      setError(errorText(err))
      return false
    }
  }

  if (!menu) return <ErrorText error={error} />

  return (
    <section className="flex flex-col gap-4">
      <div>
        <Link to="/admin/restaurants" className="text-sm text-muted-foreground hover:text-foreground">
          ← Restaurants
        </Link>
        <h2 className="text-lg font-semibold">
          {menu.name} menu {!menu.is_active && <span className="text-sm text-destructive">(inactive)</span>}
        </h2>
      </div>
      <ErrorText error={error} />
      <NewCategoryForm onCreate={(name) => run(() => createCategory(restaurantId, name))} />
      {menu.categories.map((category) => (
        <CategorySection
          key={`${category.id}-${category.name}-${category.position}`}
          category={category}
          categories={menu.categories}
          onUpdateCategory={(changes) => run(() => updateCategory(restaurantId, category.id, changes))}
          onCreateItem={(name, priceCents) =>
            run(() => createItem(restaurantId, { category_id: category.id, name, price_cents: priceCents }))
          }
          onUpdateItem={(itemId, changes) => run(() => updateItem(restaurantId, itemId, changes))}
        />
      ))}
    </section>
  )
}

function NewCategoryForm({ onCreate }: { onCreate: (name: string) => Promise<boolean> }) {
  const [name, setName] = useState('')

  return (
    <form
      className="flex gap-2"
      onSubmit={async (e) => {
        e.preventDefault()
        if (await onCreate(name)) setName('')
      }}
    >
      <Input className="max-w-64" placeholder="New category name" value={name} onChange={(e) => setName(e.target.value)} />
      <Button type="submit" variant="outline">
        Add category
      </Button>
    </form>
  )
}

function CategorySection({
  category,
  categories,
  onUpdateCategory,
  onCreateItem,
  onUpdateItem,
}: {
  category: AdminCategory
  categories: AdminCategory[]
  onUpdateCategory: (changes: Partial<Pick<AdminCategory, 'name' | 'position' | 'is_archived'>>) => Promise<boolean>
  onCreateItem: (name: string, priceCents: number) => Promise<boolean>
  onUpdateItem: (itemId: number, changes: MenuItemUpdate) => Promise<boolean>
}) {
  const [name, setName] = useState(category.name)
  const [position, setPosition] = useState(String(category.position))

  return (
    <div className={`rounded-lg border p-3 ${category.is_archived ? 'bg-muted opacity-60' : ''}`}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Input className="max-w-56 font-medium" value={name} onChange={(e) => setName(e.target.value)} />
        <Input className="w-20" type="number" value={position} onChange={(e) => setPosition(e.target.value)} />
        <Button size="sm" variant="outline" onClick={() => onUpdateCategory(changedCategoryFields(category, name, position))}>
          Save
        </Button>
        <Button size="sm" variant="ghost" onClick={() => onUpdateCategory({ is_archived: !category.is_archived })}>
          {category.is_archived ? 'Unarchive' : 'Archive'}
        </Button>
        <span className="text-xs text-muted-foreground">id {category.id}</span>
      </div>
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-muted-foreground">
          <tr>
            <th>Name</th>
            <th>Description</th>
            <th>Price (cents)</th>
            <th>Category</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {category.items.map((item) => (
            <ItemRow key={`${item.id}-${item.updated_at}`} item={item} categories={categories} onUpdate={(changes) => onUpdateItem(item.id, changes)} />
          ))}
          <NewItemRow onCreate={onCreateItem} />
        </tbody>
      </table>
    </div>
  )
}

function ItemRow({
  item,
  categories,
  onUpdate,
}: {
  item: AdminMenuItem
  categories: AdminCategory[]
  onUpdate: (changes: MenuItemUpdate) => Promise<boolean>
}) {
  const [name, setName] = useState(item.name)
  const [description, setDescription] = useState(item.description ?? '')
  const [priceCents, setPriceCents] = useState(String(item.price_cents))
  const [categoryId, setCategoryId] = useState(item.category_id)

  function changedFields(): MenuItemUpdate {
    const changes: MenuItemUpdate = {}
    if (name !== item.name) changes.name = name
    if (description !== (item.description ?? '')) changes.description = description || null
    if (Number(priceCents) !== item.price_cents) changes.price_cents = Number(priceCents)
    if (categoryId !== item.category_id) changes.category_id = categoryId
    return changes
  }

  return (
    <tr className={`border-t ${item.is_archived ? 'opacity-50' : ''}`}>
      <td className="py-1 pr-1">
        <Input value={name} onChange={(e) => setName(e.target.value)} />
      </td>
      <td className="pr-1">
        <Input value={description} onChange={(e) => setDescription(e.target.value)} />
      </td>
      <td className="w-28 pr-1">
        <Input type="number" value={priceCents} onChange={(e) => setPriceCents(e.target.value)} />
      </td>
      <td className="pr-1">
        <select
          className="h-9 rounded-md border px-1 text-sm"
          value={categoryId}
          onChange={(e) => setCategoryId(Number(e.target.value))}
        >
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </select>
      </td>
      <td className="flex gap-1 py-1 whitespace-nowrap">
        <Button size="xs" variant="outline" onClick={() => onUpdate(changedFields())}>
          Save
        </Button>
        <Button size="xs" variant="ghost" onClick={() => onUpdate({ is_available: !item.is_available })}>
          {item.is_available ? 'Make unavailable' : 'Make available'}
        </Button>
        <Button size="xs" variant="ghost" onClick={() => onUpdate({ is_archived: !item.is_archived })}>
          {item.is_archived ? 'Unarchive' : 'Archive'}
        </Button>
      </td>
    </tr>
  )
}

function NewItemRow({ onCreate }: { onCreate: (name: string, priceCents: number) => Promise<boolean> }) {
  const [name, setName] = useState('')
  const [priceCents, setPriceCents] = useState('')

  return (
    <tr className="border-t">
      <td className="py-1 pr-1">
        <Input placeholder="New item name" value={name} onChange={(e) => setName(e.target.value)} />
      </td>
      <td />
      <td className="pr-1">
        <Input type="number" placeholder="cents" value={priceCents} onChange={(e) => setPriceCents(e.target.value)} />
      </td>
      <td />
      <td>
        <Button
          size="xs"
          variant="outline"
          onClick={async () => {
            if (await onCreate(name, Number(priceCents))) {
              setName('')
              setPriceCents('')
            }
          }}
        >
          Add item
        </Button>
      </td>
    </tr>
  )
}

function changedCategoryFields(category: AdminCategory, name: string, position: string) {
  const changes: Partial<Pick<AdminCategory, 'name' | 'position'>> = {}
  if (name !== category.name) changes.name = name
  if (Number(position) !== category.position) changes.position = Number(position)
  return changes
}
