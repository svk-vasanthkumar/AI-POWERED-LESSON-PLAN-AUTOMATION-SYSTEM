import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { syllabusService } from '../../services/syllabusService';
import { academicCalendarService } from '../../services/academicCalendarService';
import { timetableService } from '../../services/timetableService';
import { FileText, CalendarClock, Table } from 'lucide-react';
import './DocumentPreview.css';

const DocumentPreview = () => {
  const { type, id } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchDocument = async () => {
      setLoading(true);
      setError(null);
      try {
        let result;
        if (type === 'syllabus') {
          result = await syllabusService.getById(id);
        } else if (type === 'calendar') {
          result = await academicCalendarService.getById(id);
        } else if (type === 'timetable') {
          result = await timetableService.getById(id);
        } else {
          throw new Error('Unknown document type');
        }
        setData(result);
      } catch (err) {
        console.error(err);
        setError('Failed to load the document preview.');
      } finally {
        setLoading(false);
      }
    };
    fetchDocument();
  }, [type, id]);

  const renderSyllabus = () => {
    return (
      <div className="preview-content syllabus-preview">
        <div className="preview-header">
          <FileText size={32} className="text-blue" />
          <h2>Course Syllabus</h2>
        </div>
        <div className="meta-info">
          <p><strong>Course ID:</strong> {data.course_id}</p>
          <p><strong>Original File:</strong> {data.original_filename}</p>
        </div>
        
        <div className="parsed-data">
          <h3>Extracted Text</h3>
          <pre className="text-content">{data.extracted_text || 'No text extracted.'}</pre>
        </div>
      </div>
    );
  };

  const renderCalendar = () => {
    return (
      <div className="preview-content calendar-preview">
        <div className="preview-header">
          <CalendarClock size={32} className="text-amber" />
          <h2>Academic Calendar</h2>
        </div>
        <div className="meta-info">
          <p><strong>Academic Year:</strong> {data.academic_year}</p>
          <p><strong>Semester:</strong> {data.semester}</p>
        </div>
        
        <div className="parsed-data">
          <h3>Scheduled Events</h3>
          {data.events && data.events.length > 0 ? (
            <table className="preview-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Type</th>
                  <th>Event Name</th>
                </tr>
              </thead>
              <tbody>
                {data.events.map((event, index) => {
                  let dateStr = 'TBD';
                  if (event.date) {
                    dateStr = new Date(event.date).toLocaleDateString();
                  } else if (event.start_date && event.end_date) {
                    dateStr = event.start_date === event.end_date 
                      ? new Date(event.start_date).toLocaleDateString() 
                      : `${new Date(event.start_date).toLocaleDateString()} - ${new Date(event.end_date).toLocaleDateString()}`;
                  } else if (event.start_date) {
                    dateStr = new Date(event.start_date).toLocaleDateString();
                  }
                  
                  return (
                    <tr key={index}>
                      <td className="font-medium">{dateStr}</td>
                      <td><span className="badge">{event.type}</span></td>
                      <td>{event.name}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <p className="text-secondary">No events found in this calendar.</p>
          )}
        </div>
      </div>
    );
  };

  const renderTimetable = () => {
    return (
      <div className="preview-content timetable-preview">
        <div className="preview-header">
          <Table size={32} className="text-green" />
          <h2>Faculty Timetable</h2>
        </div>
        <div className="meta-info">
          <p><strong>Faculty ID:</strong> {data.faculty_id}</p>
          <p><strong>Course ID:</strong> {data.course_id}</p>
          <p><strong>Semester:</strong> {data.semester}</p>
        </div>
        
        <div className="parsed-data">
          <h3>Schedule Details</h3>
          {data.schedule && data.schedule.length > 0 ? (
            <table className="preview-table">
              <thead>
                <tr>
                  <th>Day</th>
                  <th>Period (Start - End)</th>
                  <th>Subject</th>
                </tr>
              </thead>
              <tbody>
                {data.schedule.map((item, index) => (
                  <tr key={index}>
                    <td className="font-medium capitalize">{item.day}</td>
                    <td>
                      {item.period_start && item.period_end
                        ? `Hour ${item.period_start} - ${item.period_end}`
                        : `${item.start_time || ''} - ${item.end_time || ''}`}
                    </td>
                    <td>{item.subject || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-secondary">No schedule blocks found in this timetable.</p>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="document-preview-page">
      <div className="preview-container">
        {loading ? (
          <div className="loading-state">Loading document preview...</div>
        ) : error ? (
          <div className="error-state text-error">{error}</div>
        ) : data ? (
          <>
            {type === 'syllabus' && renderSyllabus()}
            {type === 'calendar' && renderCalendar()}
            {type === 'timetable' && renderTimetable()}
          </>
        ) : (
          <div className="empty-state">No data available.</div>
        )}
      </div>
    </div>
  );
};

export default DocumentPreview;
