import api from './api';

export const academicCalendarService = {
  upload: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await api.post('/calendar/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
  
  getAll: async () => {
    const response = await api.get('/calendar/');
    return response.data;
  },
  
  getById: async (calendarId) => {
    const response = await api.get(`/calendar/${calendarId}`);
    return response.data;
  },
  
  delete: async (calendarId) => {
    const response = await api.delete(`/calendar/${calendarId}`);
    return response.data;
  }
};
