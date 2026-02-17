import React from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import { MessageSquare, Users, Archive, User, Gavel } from 'lucide-react'

const SidebarItem = ({ to, icon: Icon, label, active }) => (
    <Link
        to={to}
        className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${active ? 'bg-primary/10 text-primary' : 'hover:bg-slate-100 text-secondary'
            }`}
    >
        <Icon size={20} />
        <span className="font-medium text-sm">{label}</span>
    </Link>
)

const Layout = () => {
    const location = useLocation()

    return (
        <div className="flex h-screen bg-transparent">
            {/* Sidebar */}
            <div className="w-64 bg-surface border-r border-slate-200 flex flex-col p-4 shadow-sm">
                <h1 className="text-xl font-bold text-primary mb-8 px-4">Bit Politeia Web</h1>

                <div className="flex-1 space-y-2">
                    <SidebarItem to="/chat" icon={MessageSquare} label="Messages" active={location.pathname === '/chat' || location.pathname === '/'} />
                    <SidebarItem to="/contacts" icon={Users} label="Contacts" active={location.pathname === '/contacts'} />
                    <SidebarItem to="/governance" icon={Gavel} label="Governance" active={location.pathname === '/governance'} />
                    <SidebarItem to="/archives" icon={Archive} label="Archives" active={location.pathname === '/archives'} />
                    <SidebarItem to="/profile" icon={User} label="Profile" active={location.pathname === '/profile'} />
                </div>

                <div className="text-xs text-slate-400 px-4">
                    v0.1.0 • Agent Connected
                </div>
            </div>

            {/* Main Content */}
            <main className="flex-1 overflow-auto bg-background p-6">
                <Outlet />
            </main>
        </div>
    )
}

export default Layout
