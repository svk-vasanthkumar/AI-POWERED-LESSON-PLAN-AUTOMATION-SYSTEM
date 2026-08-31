import api from './api';

export const reportsService = {
  getCourseProgress: async () => {
    const response = await api.get('/reports/course-progress');
    return response.data;
  },
  
  getFacultyWorkload: async () => {
    const response = await api.get('/reports/faculty-workload');
    return response.data;
  },
  
  getCoCoverage: async () => {
    const response = await api.get('/reports/co-coverage');
    return response.data;
  }
};
