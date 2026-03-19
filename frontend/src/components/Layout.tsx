import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

const navItems = [
  { path: '/dashboard', label: 'Dashboard' },
  { path: '/opportunities', label: 'Opportunities' },
  { path: '/deadlines', label: 'Deadlines' },
  { path: '/profile', label: 'Profile' },
  { path: '/documents', label: 'Documents' },
  { path: '/chat', label: 'AI Chat' },
  { path: '/settings/email', label: 'Email' },
  { path: '/settings/sources', label: 'Sources' },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()
  const location = useLocation()

  return (
    <div className="min-h-screen flex flex-col">
      <nav className="bg-brand-900 text-white shadow-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-8">
              <Link to="/dashboard" className="text-xl font-bold tracking-tight">
                Funding Agent
              </Link>
              <div className="hidden sm:flex gap-1">
                {navItems.map((item) => (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                      location.pathname === item.path
                        ? 'bg-brand-700 text-white'
                        : 'text-blue-100 hover:bg-brand-700/50'
                    }`}
                  >
                    {item.label}
                  </Link>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm text-blue-200">{user?.full_name}</span>
              <button
                onClick={logout}
                className="text-sm text-blue-200 hover:text-white transition-colors"
              >
                Log out
              </button>
            </div>
          </div>
        </div>
      </nav>
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  )
}
