import { useState, useEffect } from 'react'
import { HashRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Onboarding from './pages/Onboarding'
import Chat from './pages/Chat'
import Profile from './pages/Profile'
import Contacts from './pages/Contacts'
import Governance from './pages/Governance'
import Archive from './pages/Archive'

function App() {
    const [hasOnboarded, setHasOnboarded] = useState(false)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        const onboarded = localStorage.getItem('bp_onboarded') === 'true'
        setHasOnboarded(onboarded)
        setLoading(false)
    }, [])

    if (loading) return <div className="flex items-center justify-center h-screen">Loading...</div>

    return (
        <Router>
            <Routes>
                <Route path="/onboarding" element={
                    hasOnboarded ? <Navigate to="/" /> : <Onboarding onComplete={() => setHasOnboarded(true)} />
                } />

                <Route element={hasOnboarded ? <Layout /> : <Navigate to="/onboarding" />}>
                    <Route path="/" element={<Chat />} />
                    <Route path="/chat" element={<Chat />} />
                    <Route path="/profile" element={<Profile />} />
                    <Route path="/contacts" element={<Contacts />} />
                    <Route path="/governance" element={<Governance />} />
                    <Route path="/archives" element={<Archive />} />
                </Route>
            </Routes>
        </Router>
    )
}

export default App
