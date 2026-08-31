import api from './api';

export const lessonPlanService = {
  generate: async (syllabusId, payload) => {
    const response = await api.post(`/lesson-plan/generate/${syllabusId}`, payload);
    return response.data;
  },
  
  getAll: async () => {
    const response = await api.get('/lesson-plan/');
    return response.data;
  },
  
  getById: async (lessonId) => {
    const response = await api.get(`/lesson-plan/${lessonId}`);
    return response.data;
  },
  
  update: async (lessonId, payload) => {
    const response = await api.put(`/lesson-plan/${lessonId}`, payload);
    return response.data;
  },
  
  delete: async (lessonId) => {
    const response = await api.delete(`/lesson-plan/${lessonId}`);
    return response.data;
  },
  
  exportPdf: async (lessonId) => {
    const response = await api.get(`/lesson-plan/${lessonId}/export/pdf`, { responseType: 'blob' });
    return response.data;
  },
  
  exportDocx: async (lessonId) => {
    const response = await api.get(`/lesson-plan/${lessonId}/export/docx`, { responseType: 'blob' });
    return response.data;
  },
  
  exportXlsx: async (lessonId) => {
    const response = await api.get(`/lesson-plan/${lessonId}/export/xlsx`, { responseType: 'blob' });
    return response.data;
  }
};
