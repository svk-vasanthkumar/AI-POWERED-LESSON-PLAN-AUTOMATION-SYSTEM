import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { syllabusService } from '../../services/syllabusService';
import { academicCalendarService } from '../../services/academicCalendarService';
import { timetableService } from '../../services/timetableService';
import { courseService } from '../../services/courseService';
import { facultyService } from '../../services/facultyService';
import { FileText, CalendarClock, Table } from 'lucide-react';
import './DocumentPreview.css';

const DocumentPreview = () => {
  const { type, id } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editSchedule, setEditSchedule] = useState([]);
  const [isEditing, setIsEditing] = useState(false);
  const [courses, setCourses] = useState([]);
  const [faculties, setFaculties] = useState([]);

  useEffect(() => {
    const fetchDocument = async () => {
      setLoading(true);
      setError(null);
      try {
        const [courseList, facultyList] = await Promise.all([
          courseService.getAll().catch(() => []),
          facultyService.getAll().catch(() => [])
        ]);
        setCourses(courseList);
        setFaculties(facultyList);

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
        if (type === 'timetable' && result.schedule) {
          const normalized = result.schedule.map(s => {
            let dayStr = s.day || 'Monday';
            const dayLower = dayStr.toLowerCase().trim();
            if (dayLower.startsWith('mon')) dayStr = 'Monday';
            else if (dayLower.startsWith('tue')) dayStr = 'Tuesday';
            else if (dayLower.startsWith('wed')) dayStr = 'Wednesday';
            else if (dayLower.startsWith('thu')) dayStr = 'Thursday';
            else if (dayLower.startsWith('fri')) dayStr = 'Friday';
            else if (dayLower.startsWith('sat')) dayStr = 'Saturday';
            else dayStr = 'Monday';

            let order = parseInt(s.day_order);
            if (isNaN(order) || order < 1) order = 1;

            let start = parseInt(s.period_start) || 1;
            let end = parseInt(s.period_end) || start;

            return {
              ...s,
              day: dayStr,
              day_order: order,
              period_start: start,
              period_end: end
            };
          });
          setEditSchedule(normalized);
        }
      } catch (err) {
        console.error(err);
        setError('Failed to load the document preview.');
      } finally {
        setLoading(false);
      }
    };
    fetchDocument();
  }, [type, id]);

  const handleTimetableChange = (index, field, value) => {
    const newSchedule = [...editSchedule];
    newSchedule[index][field] = value;
    setEditSchedule(newSchedule);
  };

  const handleAddRow = () => {
    setEditSchedule([
      ...editSchedule,
      { day: 'Monday', day_order: 1, period_start: 1, period_end: 1, subject: '', faculty: '', room: '' }
    ]);
  };

  const handleDeleteRow = (index) => {
    setEditSchedule(editSchedule.filter((_, i) => i !== index));
  };

  const handleVerifyTimetable = async () => {
    try {
      setLoading(true);
      const cleanSchedule = editSchedule.map(s => {
        let start = parseInt(s.period_start) || 1;
        let end = parseInt(s.period_end) || start;
        if (start > end) end = start;

        let order = parseInt(s.day_order);
        if (isNaN(order) || order < 1) order = 1;

        let dayStr = s.day || 'Monday';
        const dayLower = dayStr.toLowerCase().trim();
        if (dayLower.startsWith('mon')) dayStr = 'Monday';
        else if (dayLower.startsWith('tue')) dayStr = 'Tuesday';
        else if (dayLower.startsWith('wed')) dayStr = 'Wednesday';
        else if (dayLower.startsWith('thu')) dayStr = 'Thursday';
        else if (dayLower.startsWith('fri')) dayStr = 'Friday';
        else if (dayLower.startsWith('sat')) dayStr = 'Saturday';
        else dayStr = 'Monday';

        return {
          ...s,
          day: dayStr,
          day_order: order,
          period_start: start,
          period_end: end,
          subject: s.subject || 'Unassigned',
          faculty: s.faculty || '',
          room: s.room || '',
        };
      });

      await timetableService.update(id, { schedule: cleanSchedule, status: 'VERIFIED' });
      const updated = await timetableService.getById(id);
      setData(updated);
      setIsEditing(false);
      alert('Timetable saved successfully!');
    } catch (err) {
      console.error(err);
      let errorMsg = err.message;
      if (err.response?.data?.detail) {
        const d = err.response.data.detail;
        if (typeof d === 'string') {
          errorMsg = d;
        } else if (Array.isArray(d)) {
          errorMsg = d.map(item => `${item.loc?.join('.') || 'field'}: ${item.msg}`).join('\n');
        } else {
          errorMsg = JSON.stringify(d);
        }
      }
      alert('Failed to verify timetable:\n' + errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const getCourseName = (courseId) => {
    if (!courseId) return 'N/A';
    const course = courses.find(c => (c._id || c.id) === courseId);
    return course ? `${course.course_code} - ${course.course_name}` : courseId;
  };

  const getFacultyName = (facultyId) => {
    if (!facultyId) return 'N/A';
    const faculty = faculties.find(f => (f._id || f.id) === facultyId);
    return faculty ? `${faculty.name} (${faculty.faculty_id || ''})` : facultyId;
  };

  const renderSyllabus = () => {
    return (
      <div className="preview-content syllabus-preview">
        <div className="preview-header">
          <FileText size={32} className="text-blue" />
          <h2>Course Syllabus</h2>
        </div>
        <div className="meta-info">
          <p><strong>Course:</strong> {getCourseName(data.course_id)}</p>
          <p><strong>Original File:</strong> {data.original_filename}</p>
        </div>
        
        <div className="parsed-data">
          <h3>Extracted Text</h3>
          <pre className="text-content">{data.text || data.extracted_text || 'No text extracted.'}</pre>
        </div>
      </div>
    );
  };

  const renderCalendar = () => {
    const formatDate = (val) => {
      if (!val) return '';
      const s = typeof val === 'string' ? val : String(val);
      return s.split('T')[0]; // YYYY-MM-DD for input[type=date]
    };

    const EXAM_FIELDS = [
      { key: 'cia_1', label: 'CIA 1', eventTypes: ['cia', 'cia_1', 'CIA', 'Continuous Internal Assessment - I', 'cia 1'] },
      { key: 'cia_2', label: 'CIA 2', eventTypes: ['cia_2', 'CIA_2', 'cia 2', 'Continuous Internal Assessment - II', 'Continuous Internal Assessment-II'] },
      { key: 'cia_3', label: 'CIA 3', eventTypes: ['cia_3', 'CIA_3', 'cia 3', 'Continuous Internal Assessment - III', 'Continuous Internal Assessment-III'] },
      { key: 'model_theory', label: 'Model Theory', eventTypes: ['model_theory', 'Model_theory', 'Model Theory', 'model theory'] },
      { key: 'model_practical', label: 'Model Practical', eventTypes: ['model_practical', 'Model_practical', 'Model Practical', 'model practical'] },
      { key: 'semester_end_theory', label: 'Semester End Theory', eventTypes: ['semester_end_theory', 'Semester_end_theory', 'Semester End Theory'] },
      { key: 'semester_end_practical', label: 'Semester End Practical', eventTypes: ['semester_end_practical', 'Semester_end_practical', 'Semester End Practical'] },
      { key: 'winter_vacation', label: 'Winter Vacation', eventTypes: ['winter_vacation', 'Winter_vacation', 'Winter Vacation', 'winter vacation'] },
    ];

    // Auto-fill exam date ranges from events if the structured fields are empty
    const autoFillFromEvents = () => {
      const events = data.events || [];
      const updates = {};
      EXAM_FIELDS.forEach(({ key, eventTypes }) => {
        if (data[key] && data[key].start_date && data[key].end_date) return; // already has data
        // Find a matching event by type (case-insensitive, also partial match on name)
        const match = events.find(ev => {
          const evType = (ev.type || '').toLowerCase().replace(/[\s_-]/g, '');
          const evName = (ev.name || '').toLowerCase();
          return eventTypes.some(t => {
            const norm = t.toLowerCase().replace(/[\s_-]/g, '');
            return evType === norm || evName.includes(norm) || norm.includes(evType);
          });
        });
        if (match && (match.start_date || match.date) && (match.end_date || match.date)) {
          updates[key] = {
            start_date: formatDate(match.start_date || match.date),
            end_date: formatDate(match.end_date || match.date),
          };
        }
      });
      if (Object.keys(updates).length > 0) {
        setData(prev => ({ ...prev, ...updates }));
      }
    };

    // Trigger auto-fill once if we have events but missing structured fields
    const hasMissingFields = EXAM_FIELDS.some(({ key }) => !data[key] || !data[key].start_date);
    const hasEvents = (data.events || []).length > 0;
    if (hasMissingFields && hasEvents) {
      // Use a ref check to avoid infinite re-renders - we call this inline only once
      // by checking a sentinel on the data object
      if (!data._autoFilled) {
        setTimeout(() => autoFillFromEvents(), 0);
      }
    }

    const handleExamDateChange = (key, field, value) => {
      setData(prev => ({
        ...prev,
        _autoFilled: true,
        [key]: {
          ...(prev[key] || {}),
          [field]: value,
        }
      }));
    };

    const handleAutoFill = () => {
      // Manual trigger for auto-fill button
      const events = data.events || [];
      const updates = { _autoFilled: true };
      EXAM_FIELDS.forEach(({ key, eventTypes }) => {
        const match = events.find(ev => {
          const evType = (ev.type || '').toLowerCase().replace(/[\s_-]/g, '');
          const evName = (ev.name || '').toLowerCase();
          return eventTypes.some(t => {
            const norm = t.toLowerCase().replace(/[\s_-]/g, '');
            return evType === norm || evName.includes(norm) || norm.includes(evType);
          });
        });
        if (match && (match.start_date || match.date) && (match.end_date || match.date)) {
          updates[key] = {
            start_date: formatDate(match.start_date || match.date),
            end_date: formatDate(match.end_date || match.date),
          };
        }
      });
      setData(prev => ({ ...prev, ...updates }));
    };

    const handleSaveCalendar = async () => {
      try {
        setLoading(true);
        // Build the payload with exam date ranges
        const examRanges = {};
        EXAM_FIELDS.forEach(({ key }) => {
          const range = data[key];
          if (range && range.start_date && range.end_date) {
            examRanges[key] = { start_date: range.start_date, end_date: range.end_date };
          } else {
            examRanges[key] = null;
          }
        });

        const payload = {
          academic_year: data.academic_year,
          semester: data.semester,
          semester_start: formatDate(data.semester_start),
          semester_end: formatDate(data.semester_end),
          working_days: data.working_days || [],
          monthly_working_days: data.monthly_working_days || [],
          total_working_days: data.total_working_days || null,
          holidays: (data.holidays || []).map(h => ({ date: formatDate(h.date), name: h.name })),
          events: data.events || [],
          special_days: (data.special_days || []).map(s => ({ date: formatDate(s.date), timetable_day: s.timetable_day })),
          ...examRanges,
          internal_exams: data.internal_exams || [],
        };

        await academicCalendarService.confirm(id, payload);
        alert('Calendar exam dates saved and confirmed successfully!');
        window.location.reload();
      } catch (err) {
        console.error(err);
        alert('Failed to save calendar: ' + (err?.response?.data?.detail || err.message));
      } finally {
        setLoading(false);
      }
    };

    return (
      <div className="preview-content calendar-preview">
        <div className="preview-header">
          <CalendarClock size={32} className="text-amber" />
          <h2>Academic Calendar</h2>
        </div>
        <div className="meta-info">
          <p><strong>Academic Year:</strong> {data.academic_year}</p>
          <p><strong>Semester:</strong> {data.semester}</p>
          <p><strong>Status:</strong> <span className={`badge badge-${data.status === 'confirmed' ? 'success' : 'warning'}`}>{data.status || 'pending_review'}</span></p>
          
          <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
            <div>
              <label style={{ fontSize: '0.85rem', fontWeight: 'bold', display: 'block', marginBottom: '0.25rem' }}>Semester Start</label>
              <input
                type="date"
                className="form-control"
                value={formatDate(data.semester_start)}
                onChange={e => setData(prev => ({ ...prev, semester_start: e.target.value }))}
                style={{ width: 'auto' }}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.85rem', fontWeight: 'bold', display: 'block', marginBottom: '0.25rem' }}>Semester End</label>
              <input
                type="date"
                className="form-control"
                value={formatDate(data.semester_end)}
                onChange={e => setData(prev => ({ ...prev, semester_end: e.target.value }))}
                style={{ width: 'auto' }}
              />
            </div>
          </div>

          {/* Working Days */}
          <div style={{ marginTop: '1.5rem', padding: '1rem', background: '#f8f9fa', borderRadius: '8px', border: '1px solid #dee2e6' }}>
            <h3 style={{ marginBottom: '0.5rem', fontSize: '0.95rem' }}>🗓️ Working Days</h3>
            <p style={{ fontSize: '0.8rem', color: '#666', marginBottom: '1rem' }}>
              Select the days of the week when classes are taught.
            </p>
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
              {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map(day => (
                <label key={day} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer', fontSize: '0.9rem' }}>
                  <input
                    type="checkbox"
                    checked={(data.working_days || []).includes(day)}
                    onChange={(e) => {
                      const current = data.working_days || [];
                      if (e.target.checked) {
                        setData(prev => ({ ...prev, working_days: [...current, day] }));
                      } else {
                        setData(prev => ({ ...prev, working_days: current.filter(d => d !== day) }));
                      }
                    }}
                  />
                  {day}
                </label>
              ))}
            </div>
          </div>
        </div>

        {/* Exam Date Ranges */}
        <div className="parsed-data" style={{ marginTop: '1.5rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>📅 Exam & Holiday Date Ranges</h3>
          <p style={{ fontSize: '0.85rem', color: '#666', marginBottom: '1rem' }}>
            Fill in the date ranges for each exam type. These will be used to auto-fill dates in the Schedule Generator.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '1rem' }}>
            {EXAM_FIELDS.map(({ key, label }) => {
              const range = data[key] || {};
              const hasData = range.start_date && range.end_date;
              return (
                <div key={key} style={{ 
                  padding: '1rem', borderRadius: '8px', border: '1px solid', 
                  borderColor: hasData ? '#34a853' : '#d0d7de',
                  background: hasData ? '#f0faf4' : '#f9f9f9'
                }}>
                  <div style={{ fontWeight: '600', marginBottom: '0.5rem', fontSize: '0.9rem', 
                    color: hasData ? '#1e7e34' : '#333'
                  }}>
                    {hasData ? '✅ ' : ''}{label}
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <div style={{ flex: 1 }}>
                      <label style={{ fontSize: '0.75rem', color: '#666' }}>Start Date</label>
                      <input
                        type="date"
                        className="form-control"
                        style={{ fontSize: '0.85rem' }}
                        value={formatDate(range.start_date)}
                        onChange={e => handleExamDateChange(key, 'start_date', e.target.value)}
                      />
                    </div>
                    <div style={{ flex: 1 }}>
                      <label style={{ fontSize: '0.75rem', color: '#666' }}>End Date</label>
                      <input
                        type="date"
                        className="form-control"
                        style={{ fontSize: '0.85rem' }}
                        value={formatDate(range.end_date)}
                        onChange={e => handleExamDateChange(key, 'end_date', e.target.value)}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <div style={{ marginTop: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <button 
              className="btn btn-secondary" 
              onClick={handleAutoFill}
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
            >
              ✨ Auto-Fill from Events Below
            </button>
            <button className="btn btn-primary" onClick={handleSaveCalendar} disabled={loading}>
              {loading ? 'Saving...' : '💾 Save & Confirm Calendar'}
            </button>
          </div>
        </div>

        {/* Events table */}
        <div className="parsed-data" style={{ marginTop: '2rem' }}>
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
          <p><strong>Faculty:</strong> {getFacultyName(data.faculty_id)}</p>
          <p><strong>Course:</strong> {getCourseName(data.course_id)}</p>
          <p><strong>Semester:</strong> {data.semester}</p>
        </div>
        
        <div className="parsed-data">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3>Schedule Details {data.status === 'DRAFT' && '(Draft Mode)'}</h3>
            <div>
              {data.status === 'VERIFIED' && !isEditing && (
                <button className="btn btn-secondary mr-2" onClick={() => setIsEditing(true)}>
                  Edit Timetable
                </button>
              )}
              {(data.status === 'DRAFT' || isEditing) && (
                <>
                  {isEditing && (
                    <button className="btn btn-secondary mr-2" onClick={() => {
                        setIsEditing(false);
                        setEditSchedule(data.schedule || []);
                    }}>
                      Cancel
                    </button>
                  )}
                  <button className="btn btn-primary" onClick={handleVerifyTimetable}>
                    {data.status === 'DRAFT' ? 'Confirm & Verify' : 'Save Changes'}
                  </button>
                </>
              )}
            </div>
          </div>
          
          {data.status === 'DRAFT' || isEditing ? (
            <div>
              <table className="preview-table">
                <thead>
                  <tr>
                    <th>Day</th>
                    <th>Day Order</th>
                    <th>Period (Start/End)</th>
                    <th>Subject</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {editSchedule.map((item, index) => (
                    <tr key={index}>
                      <td>
                        <select
                          className="form-control"
                          value={item.day || 'Monday'}
                          onChange={(e) => handleTimetableChange(index, 'day', e.target.value)}
                        >
                          <option value="Monday">Monday</option>
                          <option value="Tuesday">Tuesday</option>
                          <option value="Wednesday">Wednesday</option>
                          <option value="Thursday">Thursday</option>
                          <option value="Friday">Friday</option>
                          <option value="Saturday">Saturday</option>
                        </select>
                      </td>
                      <td>
                        <input
                          className="form-control"
                          type="number"
                          min="1"
                          max="6"
                          placeholder="Order"
                          value={item.day_order ?? 1}
                          onChange={(e) => handleTimetableChange(index, 'day_order', e.target.value)}
                        />
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <select
                            className="form-control"
                            value={item.period_start ?? 1}
                            onChange={(e) => handleTimetableChange(index, 'period_start', e.target.value)}
                          >
                            {[1, 2, 3, 4, 5, 6, 7].map(p => (
                              <option key={p} value={p}>Hour {p}</option>
                            ))}
                          </select>
                          <select
                            className="form-control"
                            value={item.period_end ?? item.period_start ?? 1}
                            onChange={(e) => handleTimetableChange(index, 'period_end', e.target.value)}
                          >
                            {[1, 2, 3, 4, 5, 6, 7].map(p => (
                              <option key={p} value={p}>Hour {p}</option>
                            ))}
                          </select>
                        </div>
                      </td>
                      <td style={{ width: '40%' }}>
                        <input className="form-control" placeholder="Subject" value={item.subject || ''} onChange={(e) => handleTimetableChange(index, 'subject', e.target.value)} style={{ width: '100%', minWidth: '250px' }} />
                      </td>
                      <td>
                        <button className="btn btn-secondary text-error" onClick={() => handleDeleteRow(index)}>Remove</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button className="btn btn-secondary mt-3" onClick={handleAddRow}>+ Add Row</button>
            </div>
          ) : (
            data.schedule && data.schedule.length > 0 ? (
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
            )
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
