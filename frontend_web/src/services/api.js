import axios from 'axios'

const API_URL = localStorage.getItem('bp_api_url') || 'http://localhost:8000'

const api = axios.create({
    baseURL: API_URL,
    headers: {
        'Content-Type': 'application/json',
    },
    timeout: 10000
})

export const setApiUrl = (url) => {
    localStorage.setItem('bp_api_url', url)
    api.defaults.baseURL = url
}

export default api
