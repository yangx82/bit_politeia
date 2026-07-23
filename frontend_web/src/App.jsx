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
        const checkStatus = async () => {
            const onboarded = localStorage.getItem('bp_onboarded') === 'true'
            if (onboarded) {
                setHasOnboarded(true)
                setLoading(false)
                return
            }

            // Fallback: If backend is already configured (e.g. after data import), auto-pass onboarding
            try {
                const { default: api } = await import('./services/api')
                const response = await api.get('/api/v1/status')
                const statusData = response.data
                if (statusData && (statusData.node_id || statusData.model)) {
                    localStorage.setItem('bp_onboarded', 'true')
                    if (statusData.model) localStorage.setItem('bp_model', statusData.model)
                    if (statusData.base_url) localStorage.setItem('bp_llm_base_url', statusData.base_url)
                    setHasOnboarded(true)
                }
            } catch (err) {
                console.error('Failed to check backend status:', err)
            } finally {
                setLoading(false)
            }
        }
        checkStatus()
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
