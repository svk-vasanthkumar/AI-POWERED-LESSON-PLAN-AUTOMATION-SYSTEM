import React, { useState, useEffect } from 'react';
import UploadCard from '../../components/common/UploadCard';
import { syllabusService } from '../../services/syllabusService';
import { academicCalendarService } from '../../services/academicCalendarService';
import { timetableService } from '../../services/timetableService';
import { courseService } from '../../services/courseService';
import { FileText, Trash2, ExternalLink, CalendarClock, Table } from 'lucide-react';
import './Documents.css';

const Documents = () => {
  const [documents, setDocuments] = useState({ syllabi: [], calendars: [], timetables: [] });
  const [courses, setCourses] = useState([]);
  const [selectedCourse, setSelectedCourse] = useState("");
  const [loading, setLoading] = useState(true);
  const [uploadState, setUploadState] = useState({
    syllabus: { isUploading: false, status: null, message: '', progress: 0 },
    calendar: { isUploading: false, status: null, message: '', progress: 0 },
    timetable: { isUploading: false, status: null, message: '', progress: 0 },
  });

  const fetchAllDocuments = async () => {
    try {
      setLoading(true);
      const coursesData = await courseService.getAll().catch(() => []);
      setCourses(coursesData);
      
      const [syllabiData, calendarsData, timetablesData] = await Promise.all([
        syllabusService.getAll().catch(() => []),
        academicCalendarService.getAll().catch(() => []),
        timetableService.getAll().catch(() => [])
      ]);

      const mergeCourseData = (docs) => docs.map(doc => {
        const course = coursesData.find(c => c._id === doc.course_id || c.id === doc.course_id);
        return {
          ...doc,
          course_name: course ? course.course_name : (doc.course_name || 'Unknown'),
          course_code: course ? course.course_code : (doc.course_code || 'N/A')
        };
      });

      setDocuments({ 
        syllabi: mergeCourseData(syllabiData), 
        calendars: calendarsData, 
        timetables: mergeCourseData(timetablesData) 
      });
    } catch (error) {
      console.error("Failed to fetch documents:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAllDocuments();
  }, []);

  const simulateProgress = (type) => {
    return setInterval(() => {
      setUploadState(prev => ({
        ...prev,
        [type]: { ...prev[type], progress: Math.min(prev[type].progress + 15, 90) }
      }));
    }, 400);
  };

  const handleUpload = async (type, file, serviceCall) => {
    setUploadState(prev => ({
      ...prev,
      [type]: { isUploading: true, status: null, message: 'Processing...', progress: 10 }
    }));
    
    const interval = simulateProgress(type);
    
    try {
      await serviceCall(file, selectedCourse);
      clearInterval(interval);
      setUploadState(prev => ({
        ...prev,
        [type]: { isUploading: false, status: 'success', message: 'Uploaded successfully.', progress: 100 }
      }));
      fetchAllDocuments();
      
      // Reset success state after a few seconds
      setTimeout(() => {
        setUploadState(prev => ({
          ...prev,
          [type]: { isUploading: false, status: null, message: '', progress: 0 }
        }));
      }, 3000);
    } catch (error) {
      clearInterval(interval);
      setUploadState(prev => ({
        ...prev,
        [type]: { isUploading: false, status: 'error', message: error.uiMessage || 'Upload failed.', progress: 0 }
      }));
    }
  };

  const handleDelete = async (type, id, serviceCall) => {
    if (window.confirm(`Are you sure you want to delete this ${type}?`)) {
      try {
        await serviceCall(id);
        fetchAllDocuments();
      } catch (error) {
        alert("Failed to delete document: " + (error.uiMessage || error.message));
      }
    }
  };

  return (
    <div className="documents-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Documents Hub</h1>
          <p className="page-subtitle">Manage Syllabi, Academic Calendars, and Timetables.</p>
        </div>
      </div>

      <div className="documents-grid">
        <div className="upload-section">
          <h2 className="section-title">Upload New Documents</h2>
          
          <div className="upload-card-wrapper">
            <div style={{ marginBottom: '10px' }}>
              <select 
                className="form-control" 
                value={selectedCourse}
                onChange={(e) => setSelectedCourse(e.target.value)}
              >
                <option value="">Select a Course for Syllabus...</option>
                {courses.map(course => (
                  <option key={course._id || course.id} value={course._id || course.id}>
                    {course.course_code} - {course.course_name}
                  </option>
                ))}
              </select>
            </div>
            
            <UploadCard 
              title="Course Syllabus (PDF)"
              acceptedFormats=".pdf"
              onUpload={(file) => {
                if (!selectedCourse) {
                  alert("Please select a course first.");
                  return;
                }
                handleUpload('syllabus', file, syllabusService.upload);
              }}
              isUploading={uploadState.syllabus.isUploading}
              progress={uploadState.syllabus.progress}
              status={uploadState.syllabus.status}
              statusMessage={uploadState.syllabus.message}
            />
          </div>

          <div className="upload-card-wrapper mt-4">
            <UploadCard 
              title="Academic Calendar (PDF/CSV/Img)"
              acceptedFormats=".pdf,.csv,.png,.jpg"
              onUpload={(file) => handleUpload('calendar', file, academicCalendarService.upload)}
              isUploading={uploadState.calendar.isUploading}
              progress={uploadState.calendar.progress}
              status={uploadState.calendar.status}
              statusMessage={uploadState.calendar.message}
            />
          </div>

          <div className="upload-card-wrapper mt-4">
            <UploadCard 
              title="Faculty Timetable (PDF/CSV/Img)"
              acceptedFormats=".pdf,.csv,.png,.jpg"
              onUpload={(file) => handleUpload('timetable', file, timetableService.upload)}
              isUploading={uploadState.timetable.isUploading}
              progress={uploadState.timetable.progress}
              status={uploadState.timetable.status}
              statusMessage={uploadState.timetable.message}
            />
          </div>
        </div>

        <div className="list-section">
          <h2 className="section-title">Uploaded Documents</h2>
          
          <div className="document-list">
            {loading ? (
              <p className="text-secondary text-center py-4">Loading documents...</p>
            ) : (documents.syllabi.length === 0 && documents.calendars.length === 0 && documents.timetables.length === 0) ? (
              <div className="empty-state">
                <FileText size={48} className="empty-icon" />
                <p>No documents uploaded yet.</p>
              </div>
            ) : (
              <>
                {documents.syllabi.map(doc => (
                  <div key={`syl-${doc.id}`} className="document-card">
                    <div className="doc-icon-wrapper bg-blue-light text-blue">
                      <FileText size={20} />
                    </div>
                    <div className="doc-details">
                      <h4 className="doc-title">{doc.course_code || 'Unknown'} - {doc.course_name || 'Syllabus'}</h4>
                      <p className="doc-meta">Semester {doc.semester || 'N/A'} • Syllabus</p>
                    </div>
                    <div className="doc-actions" style={{ display: 'flex', gap: '0.5rem' }}>
                      <button className="btn-icon text-blue" onClick={() => window.open(`/preview/syllabus/${doc._id || doc.id}`, '_blank')} title="Preview">
                        <ExternalLink size={18} />
                      </button>
                      <button className="btn-icon text-error" onClick={() => handleDelete('syllabus', doc._id || doc.id, syllabusService.delete)} title="Delete">
                        <Trash2 size={18} />
                      </button>
                    </div>
                  </div>
                ))}

                {documents.calendars.map(doc => (
                  <div key={`cal-${doc.id}`} className="document-card">
                    <div className="doc-icon-wrapper bg-amber-light text-amber">
                      <CalendarClock size={20} />
                    </div>
                    <div className="doc-details">
                      <h4 className="doc-title">{doc.name || 'Academic Calendar'}</h4>
                      <p className="doc-meta">{doc.academic_year || 'Unknown Year'} • Academic Calendar</p>
                    </div>
                    <div className="doc-actions" style={{ display: 'flex', gap: '0.5rem' }}>
                      <button className="btn-icon text-blue" onClick={() => window.open(`/preview/calendar/${doc._id || doc.id}`, '_blank')} title="Preview">
                        <ExternalLink size={18} />
                      </button>
                      <button className="btn-icon text-error" onClick={() => handleDelete('calendar', doc._id || doc.id, academicCalendarService.delete)} title="Delete">
                        <Trash2 size={18} />
                      </button>
                    </div>
                  </div>
                ))}

                {documents.timetables.map(doc => (
                  <div key={`tt-${doc.id}`} className="document-card">
                    <div className="doc-icon-wrapper bg-green-light text-green">
                      <Table size={20} />
                    </div>
                    <div className="doc-details">
                      <h4 className="doc-title">{doc.name || 'Timetable'}</h4>
                      <p className="doc-meta">Timetable</p>
                    </div>
                    <div className="doc-actions" style={{ display: 'flex', gap: '0.5rem' }}>
                      <button className="btn-icon text-blue" onClick={() => window.open(`/preview/timetable/${doc._id || doc.id}`, '_blank')} title="Preview">
                        <ExternalLink size={18} />
                      </button>
                      <button className="btn-icon text-error" onClick={() => handleDelete('timetable', doc._id || doc.id, timetableService.delete)} title="Delete">
                        <Trash2 size={18} />
                      </button>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Documents;
