import api from './client';

export const downloadExport = async (url, fallbackName) => {
  const response = await api.get(url, { responseType: 'blob' });
  
  // Extract filename from Content-Disposition header if available
  let filename = fallbackName;
  const disposition = response.headers['content-disposition'];
  if (disposition && disposition.includes('filename=')) {
    filename = disposition.split('filename=')[1].replace(/["']/g, '');
  }

  const blob = new Blob([response.data], { type: response.headers['content-type'] });
  const downloadUrl = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = downloadUrl;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(downloadUrl);
};