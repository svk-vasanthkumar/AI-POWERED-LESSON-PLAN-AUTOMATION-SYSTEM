import api from './api';

export const timetableService = {
  upload: async (file, facultyId, courseId, semester) => {
    const formData = new FormData();
    formData.append('file', file);
    
    const params = new URLSearchParams({
      faculty_id: facultyId,
      course_id: courseId,
      semester: semester
    });
    
    const response = await api.post(`/timetable/upload?${params.toString()}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
  
  getAll: async () => {
    const response = await api.get(`/timetable/?t=${new Date().getTime()}`);
    return response.data;
  },
  
  getById: async (timetableId) => {
    const response = await api.get(`/timetable/${timetableId}`);
    return response.data;
  },
  
  update: async (timetableId, data) => {
    const response = await api.put(`/timetable/${timetableId}`, data);
    return response.data;
  },
  
  delete: async (timetableId) => {
    const response = await api.delete(`/timetable/${timetableId}`);
    return response.data;
  }
};
