import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router'

import { ErrorText } from '@/components/ErrorText'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { signup } from '@/lib/api'
import { errorText } from '@/lib/format'

import { useAuth } from './AuthContext'
import { homeFor } from './homeFor'

const DEMO_USERS = [
  { email: 'customer1@example.com', password: 'customer1-demo' },
  { email: 'admin1@example.com', password: 'admin1-demo' },
]

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [isSignup, setIsSignup] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isBusy, setIsBusy] = useState(false)

  if (user) return <Navigate to={homeFor(user.role)} replace />

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setIsBusy(true)
    try {
      if (isSignup) await signup(email, password, fullName)
      const me = await login(email, password)
      navigate(homeFor(me.role))
    } catch (err) {
      setError(errorText(err))
    } finally {
      setIsBusy(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mx-auto flex max-w-sm flex-col gap-3">
      <h2 className="text-lg font-semibold">{isSignup ? 'Sign up' : 'Log in'}</h2>
      {isSignup && (
        <Input placeholder="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
      )}
      <Input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <Input
        type="password"
        placeholder="Password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <ErrorText error={error} />
      <Button type="submit" disabled={isBusy}>
        {isSignup ? 'Sign up' : 'Log in'}
      </Button>
      <Button type="button" variant="link" onClick={() => setIsSignup(!isSignup)}>
        {isSignup ? 'Have an account? Log in' : 'No account? Sign up'}
      </Button>
      {!isSignup && (
        <div className="flex flex-col gap-1 text-xs text-muted-foreground">
          <span>Seeded users:</span>
          {DEMO_USERS.map((demo) => (
            <button
              key={demo.email}
              type="button"
              className="text-left hover:text-foreground"
              onClick={() => {
                setEmail(demo.email)
                setPassword(demo.password)
              }}
            >
              {demo.email}
            </button>
          ))}
        </div>
      )}
    </form>
  )
}
