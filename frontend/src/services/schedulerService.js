import api from './api';

export const schedulerService = {
  generateSchedule: async (courseId, calendarId = null, timetableId = null, examConfigs = null) => {
    let url = `/scheduler/${courseId}`;
    const params = new URLSearchParams();
    if (calendarId) params.append('calendar_id', calendarId);
    if (timetableId) params.append('timetable_id', timetableId);
    
    const queryString = params.toString();
    if (queryString) {
      url += `?${queryString}`;
    }
    
    const payload = examConfigs ? { exam_configs: examConfigs } : {};
    const response = await api.post(url, payload);
    return response.data;
  },
  
  getSchedule: async (courseId) => {
    const response = await api.get(`/scheduler/${courseId}`);
    return response.data;
  },
  
  updateSession: async (courseId, sessionId, updateData) => {
    const response = await api.patch(`/scheduler/${courseId}/sessions/${sessionId}`, updateData);
    return response.data;
  },
  
  rescheduleSession: async (courseId, sessionId, rescheduleData) => {
    const response = await api.post(`/scheduler/${courseId}/sessions/${sessionId}/reschedule`, rescheduleData);
    return response.data;
  },
  
  getProgress: async (courseId) => {
    const response = await api.get(`/scheduler/${courseId}/progress`);
    return response.data;
  },
  
  exportPdf: async (courseId) => {
    const response = await api.get(`/scheduler/${courseId}/export/pdf`, { responseType: 'blob' });
    return response.data;
  },
  
  exportDocx: async (courseId) => {
    const response = await api.get(`/scheduler/${courseId}/export/docx`, { responseType: 'blob' });
    return response.data;
  },
  
  exportXlsx: async (courseId) => {
    const response = await api.get(`/scheduler/${courseId}/export/xlsx`, { responseType: 'blob' });
    return response.data;
  }
};
