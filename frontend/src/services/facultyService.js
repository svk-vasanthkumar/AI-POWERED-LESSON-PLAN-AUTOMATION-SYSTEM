import api from './api';

export const facultyService = {
  getAll: async () => {
    const response = await api.get('/faculty/');
    return response.data;
  },
  
  create: async (facultyData) => {
    const response = await api.post('/faculty/', facultyData);
    return response.data;
  },
  
  update: async (facultyId, facultyData) => {
    const response = await api.put(`/faculty/${facultyId}`, facultyData);
    return response.data;
  },
  
  delete: async (facultyId) => {
    const response = await api.delete(`/faculty/${facultyId}`);
    return response.data;
  },
  
  sendEmail: async (facultyId, password) => {
    const response = await api.post(`/faculty/${facultyId}/send-email`, { password });
    return response.data;
  }
};
