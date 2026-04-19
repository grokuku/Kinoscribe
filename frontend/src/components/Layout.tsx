import { type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Film, ListTodo, Settings, Languages } from 'lucide-react';

export default function Layout({ children }: { children: ReactNode }) {
  const loc = useLocation();

  const nav = [
    { to: '/', label: 'Films', icon: Film },
    { to: '/tasks', label: 'Tâches', icon: ListTodo },
    { to: '/settings', label: 'Paramètres', icon: Settings },
  ];

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-gray-800 bg-gray-950/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto flex items-center justify-between px-4 h-14">
          <Link to="/" className="flex items-center gap-2 text-brand-400 font-bold text-lg hover:text-brand-300 transition-colors">
            <Languages className="w-6 h-6" />
            Kinoscribe
          </Link>
          <nav className="flex items-center gap-1">
            {nav.map(({ to, label, icon: Icon }) => {
              const active = loc.pathname === to || (to !== '/' && loc.pathname.startsWith(to));
              return (
                <Link
                  key={to}
                  to={to}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    active
                      ? 'bg-brand-600/20 text-brand-400'
                      : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-6">
        {children}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 py-4 text-center text-xs text-gray-600">
        Kinoscribe — Local-first contextual subtitle translation
      </footer>
    </div>
  );
}