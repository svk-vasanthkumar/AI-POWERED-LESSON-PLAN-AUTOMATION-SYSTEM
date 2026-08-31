import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to inject token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('jwt_token');
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Implement standard error extraction for UI
    let errorMessage = 'An unexpected error occurred';
    if (error.response) {
      if (error.response.status === 401) {
        localStorage.removeItem('jwt_token');
        window.location.href = '/login'; // Force redirect on unauthorized
      }
      if (error.response.data && error.response.data.detail) {
        const detail = error.response.data.detail;
        if (typeof detail === 'string') {
          errorMessage = detail;
        } else if (Array.isArray(detail)) {
          errorMessage = detail.map(d => d.msg).join(', ');
        } else {
          errorMessage = JSON.stringify(detail);
        }
      } else {
        errorMessage = `Error ${error.response.status}: ${error.response.statusText}`;
      }
    } else if (error.request) {
      errorMessage = 'Network error. Please check your connection.';
    }
    
    // Attach extracted message to error object for easy access
    error.uiMessage = errorMessage;
    return Promise.reject(error);
  }
);

export default api;
