import { Link, Outlet, useLocation } from 'react-router-dom';

const NAV = [
  { path: '/', label: 'Dashboard' },
  { path: '/projects', label: 'Projects' },
];

export default function Layout() {
  const location = useLocation();

  const isActive = (path: string) =>
    path === '/' ? location.pathname === '/' : location.pathname.startsWith(path);

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <header className="border-b border-gray-800 bg-gray-900">
        <div className="mx-auto flex max-w-7xl items-center gap-8 px-6 py-3">
          <Link to="/" className="text-lg font-bold text-white">
            Work Orchestrator
          </Link>
          <nav className="flex gap-4">
            {NAV.map(({ path, label }) => (
              <Link
                key={path}
                to={path}
                className={`text-sm ${
                  isActive(path)
                    ? 'text-blue-400 font-medium'
                    : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                {label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-6">
        <Outlet />
      </main>
    </div>
  );
}
