import api from './api';

export const authService = {
  login: async (email, password) => {
    const response = await api.post('/auth/login', {
      email,
      password
    });
    
    if (response.data.access_token) {
      localStorage.setItem('jwt_token', response.data.access_token);
    }
    return response.data;
  },
  
  resetPassword: async (email, current_password, new_password) => {
    const response = await api.post('/auth/reset-password', {
      email,
      current_password,
      new_password
    });
    return response.data;
  },
  
  forgotPassword: async (email) => {
    const response = await api.post('/auth/forgot-password', { email });
    return response.data;
  },
  
  resetPasswordWithToken: async (token, new_password) => {
    const response = await api.post('/auth/reset-password-token', { token, new_password });
    return response.data;
  },
  
  getProfile: async () => {
    const response = await api.get('/auth/profile');
    return response.data.user;
  },
  
  logout: () => {
    localStorage.removeItem('jwt_token');
  },

  updateProfile: async (profileData) => {
    const response = await api.put('/auth/profile', profileData);
    return response.data;
  },

  updatePreferences: async (preferencesData) => {
    const response = await api.put('/auth/preferences', preferencesData);
    return response.data;
  }
};
