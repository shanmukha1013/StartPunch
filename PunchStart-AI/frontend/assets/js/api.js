const API_BASE_URL = localStorage.getItem('punchstart_api_url') || 'http://127.0.0.1:8000';

async function apiRequest(endpoint, method = 'GET', body = null) {
    const token = localStorage.getItem('auth_token');
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60000);

    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            method,
            headers,
            body: body ? JSON.stringify(body) : null,
            signal: controller.signal
        });

        if (!response.ok) {
            const payload = await response.json().catch(() => ({}));
            throw new Error(payload.detail || 'The request could not be completed.');
        }
        return response.json();
    } catch (error) {
        if (error.name === 'AbortError') {
            throw new Error('The analysis is taking longer than expected. Please try again.');
        }
        throw new Error(error.message || 'The request could not be completed.');
    } finally {
        clearTimeout(timeout);
    }
}

function runAnalysis(startupData) {
    return apiRequest('/api/analyze', 'POST', startupData);
}
