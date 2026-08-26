import api from './api';

export const timetableService = {
  upload: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await api.post('/timetable/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
  
  getAll: async () => {
    const response = await api.get('/timetable/');
    return response.data;
  },
  
  getById: async (timetableId) => {
    const response = await api.get(`/timetable/${timetableId}`);
    return response.data;
  },
  
  delete: async (timetableId) => {
    const response = await api.delete(`/timetable/${timetableId}`);
    return response.data;
  }
};
