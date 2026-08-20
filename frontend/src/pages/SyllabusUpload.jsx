import React, { useState } from 'react';
import api from '../api/client';
import { Upload, FileText, CheckCircle, AlertCircle } from 'lucide-react';

export default function SyllabusUpload({ courseId, onGenerated }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');

  const handleUploadAndGenerate = async (e) => {
    e.preventDefault();
    if (!file) return;

    setLoading(true);
    setStatus('Uploading and extracting text...');

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('course_id', courseId);

      // 1. Upload syllabus
      const uploadRes = await api.post('/syllabus/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      const syllabusId = uploadRes.data.syllabus_id;
      setStatus('Generating AI structured lesson plan with Groq...');

      // 2. Trigger AI Generation
      const planRes = await api.post(`/lesson-plan/generate/${syllabusId}`);
      setStatus('Lesson plan generated successfully!');
      if (onGenerated) onGenerated(planRes.data);
    } catch (err) {
      setStatus(`Error: ${err.response?.data?.detail || 'Failed to process syllabus'}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
      <h3 className="text-lg font-semibold text-slate-800 mb-4 flex items-center gap-2">
        <Upload className="w-5 h-5 text-indigo-600" /> Upload Syllabus Document
      </h3>
      <form onSubmit={handleUploadAndGenerate} className="space-y-4">
        <input
          type="file"
          accept=".pdf,.docx"
          onChange={(e) => setFile(e.target.files[0])}
          className="block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"
        />
        <button
          type="submit"
          disabled={!file || loading}
          className="px-4 py-2 bg-indigo-600 text-white rounded-md font-medium hover:bg-indigo-700 disabled:opacity-50 transition"
        >
          {loading ? 'Processing...' : 'Upload & Generate Plan'}
        </button>
      </form>
      {status && (
        <p className="mt-4 text-sm font-medium text-slate-600 bg-slate-50 p-3 rounded-md">
          {status}
        </p>
      )}
    </div>
  );
}