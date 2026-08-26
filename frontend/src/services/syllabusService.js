import api from './api';

export const syllabusService = {
  upload: async (file, courseId) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('course_id', courseId);
    
    const response = await api.post('/syllabus/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
  
  getAll: async () => {
    const response = await api.get('/syllabus/');
    return response.data;
  },
  
  getById: async (syllabusId) => {
    const response = await api.get(`/syllabus/${syllabusId}`);
    return response.data;
  },
  
  delete: async (syllabusId) => {
    const response = await api.delete(`/syllabus/${syllabusId}`);
    return response.data;
  }
};
