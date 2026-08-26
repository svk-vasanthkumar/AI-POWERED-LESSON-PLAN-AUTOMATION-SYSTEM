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
  }
};
