import api from './api';

export const courseService = {
  getAll: async () => {
    const response = await api.get('/course/');
    return response.data;
  },
  
  create: async (courseData) => {
    const response = await api.post('/course/', courseData);
    return response.data;
  },
  
  getById: async (courseId) => {
    const response = await api.get(`/course/${courseId}`);
    return response.data;
  },
  
  update: async (courseId, courseData) => {
    const response = await api.put(`/course/${courseId}`, courseData);
    return response.data;
  },
  
  clone: async (courseId, data) => {
    const response = await api.post(`/course/${courseId}/clone`, data);
    return response.data;
  },
  
  delete: async (courseId) => {
    const response = await api.delete(`/course/${courseId}`);
    return response.data;
  }
};
