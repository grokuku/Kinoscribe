import { type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Film, ListTodo, Settings, Languages, Clapperboard, FolderOpen } from 'lucide-react';

const nav = [
  { to: '/', label: 'Films', icon: Film },
  { to: '/libraries', label: 'Bibliothèques', icon: FolderOpen },
  { to: '/tasks', label: 'Tâches', icon: ListTodo },
  { to: '/settings', label: 'Paramètres', icon: Settings },
];

export default function Layout({ children }: { children: ReactNode }) {
  const loc = useLocation();

  return (
    <div className="min-h-screen flex">
      {/* ── Sidebar ── */}
      <aside className="hidden lg:flex flex-col w-64 flex-shrink-0 border-r border-white/[0.06] bg-surface-50/50 backdrop-blur-md">
        {/* Logo */}
        <div className="flex items-center gap-3 px-6 h-16 border-b border-white/[0.06]">
          <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-violet-600 shadow-lg shadow-brand-500/25">
            <Clapperboard className="w-5 h-5 text-white" />
          </div>
          <div>
            <span className="font-bold text-base text-gray-100 tracking-tight">Kinoscribe</span>
            <span className="block text-[10px] text-gray-600 leading-none mt-0.5">subtitles · localization</span>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {nav.map(({ to, label, icon: Icon }) => {
            const active = loc.pathname === to || (to !== '/' && loc.pathname.startsWith(to));
            return (
              <Link
                key={to}
                to={to}
                className={active ? 'nav-link-active' : 'nav-link'}
              >
                <Icon className="w-[18px] h-[18px]" />
                {label}
              </Link>
            );
          })}
        </nav>

        {/* Bottom */}
        <div className="px-5 py-4 border-t border-white/[0.06]">
          <p className="text-[10px] text-gray-600 leading-tight">
            Local-first contextual<br />subtitle translation
          </p>
        </div>
      </aside>

      {/* ── Mobile top bar ── */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-50 flex items-center gap-2 px-4 h-14 bg-surface-50/80 backdrop-blur-xl border-b border-white/[0.06]">
        <Link to="/" className="flex items-center gap-2 text-brand-400 font-bold text-lg">
          <Languages className="w-5 h-5" />
          <span className="tracking-tight">Kinoscribe</span>
        </Link>
        <div className="flex-1" />
        <nav className="flex gap-1">
          {nav.map(({ to, label, icon: Icon }) => {
            const active = loc.pathname === to || (to !== '/' && loc.pathname.startsWith(to));
            return (
              <Link
                key={to}
                to={to}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  active
                    ? 'bg-brand-500/15 text-brand-300'
                    : 'text-gray-500 hover:text-gray-200'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span className="hidden sm:inline">{label}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* ── Main content ── */}
      <main className="flex-1 min-w-0 lg:py-0">
        <div className="lg:hidden h-14" /> {/* Mobile spacer */}
        <div className="h-full lg:overflow-y-auto">
          <div className="px-4 sm:px-6 lg:px-8 xl:px-10 py-6 lg:py-8">
            {children}
          </div>
        </div>
      </main>
    </div>
  );
}