import axios from 'axios'

const API_URL = localStorage.getItem('bp_api_url') || 'http://localhost:8000'

const api = axios.create({
    baseURL: API_URL,
    headers: {
        'Content-Type': 'application/json',
    },
    timeout: 300000
})

export const setApiUrl = (url) => {
    localStorage.setItem('bp_api_url', url)
    api.defaults.baseURL = url
}


export const getGroups = async () => {
    const response = await api.get('/api/v1/p2p/groups')
    return response.data;
}

export const getProposals = async () => {
    const response = await api.get('/api/v1/governance/proposals')
    return response.data;
}

export const createProposal = async (groupId, content, durationMinutes = 60) => {
    const response = await api.post('/api/v1/governance/proposals', {
        group_id: groupId,
        content,
        duration_minutes: durationMinutes
    })
    return response.data;
}

export const getElections = async () => {
    const response = await api.get('/api/v1/governance/elections')
    return response.data;
}

export const castVote = async (electionId, approval, reason = "", candidateId = null) => {
    const response = await api.post('/api/v1/governance/vote', {
        election_id: electionId,
        approval,
        reason,
        candidate_id: candidateId
    })
    return response.data;
}

export const deleteProposal = async (proposalId) => {
    const response = await api.delete(`/api/v1/governance/proposals/${proposalId}`)
    return response.data;
}

export const deleteElection = async (electionId) => {
    const response = await api.delete(`/api/v1/governance/elections/${electionId}`)
    return response.data;
}

export default api
