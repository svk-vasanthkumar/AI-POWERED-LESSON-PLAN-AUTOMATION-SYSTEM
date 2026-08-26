import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Save, ArrowLeft, Download, CheckCircle, Clock, Calendar, X, Plus, Trash2 } from 'lucide-react';
import { lessonPlanService } from '../../services/lessonPlanService';
import { courseService } from '../../services/courseService';
import { academicCalendarService } from '../../services/academicCalendarService';
import { timetableService } from '../../services/timetableService';
import { schedulerService } from '../../services/schedulerService';
import './LessonPlanEditor.css';

const LessonPlanEditor = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  
  // Create a local copy of sessions for editing
  const [sessions, setSessions] = useState([]);

  // Schedule Generation Modal State
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [availableCalendars, setAvailableCalendars] = useState([]);
  const [availableTimetables, setAvailableTimetables] = useState([]);
  const [selectedCalendarId, setSelectedCalendarId] = useState('');
  const [selectedTimetableId, setSelectedTimetableId] = useState('');
  const [generatingSchedule, setGeneratingSchedule] = useState(false);

  useEffect(() => {
    const fetchPlan = async () => {
      try {
        setLoading(true);
        const [data, courses] = await Promise.all([
          lessonPlanService.getById(id),
          courseService.getAll().catch(e => { console.error(e); return []; })
        ]);
        
        const course = courses.find(c => c._id === data.course_id || c.id === data.course_id);
        const enrichedPlan = {
          ...data,
          course_name: course ? course.course_name : 'Unknown Course',
          course_code: course ? course.course_code : 'N/A',
          semester: course ? course.semester : 'N/A'
        };
        
        let initialSessions = enrichedPlan.sessions || [];
        if (initialSessions.length === 0 && enrichedPlan.structured_plan && enrichedPlan.structured_plan.units) {
          enrichedPlan.structured_plan.units.forEach((unit) => {
            if (unit.topics) {
              unit.topics.forEach((topic) => {
                initialSessions.push({
                  day_of_week: '-',
                  date: '',
                  topic: topic.topic,
                  module: `Unit ${unit.unit_number}`,
                  co: (topic.learning_outcomes || []).join(', ') || 'N/A',
                  teaching_method: (topic.teaching_methods || []).join(', ') || '-',
                  assessment: (topic.assessment_methods || []).join(', ') || '-',
                  hours: topic.estimated_hours || 1
                });
              });
            }
          });
        }
        
        setPlan(enrichedPlan);
        setSessions(initialSessions);
      } catch (error) {
        console.error("Failed to fetch plan:", error);
        alert("Could not load lesson plan.");
      } finally {
        setLoading(false);
      }
    };
    
    if (id) {
      fetchPlan();
    }
  }, [id]);

  const handleSessionChange = (index, field, value) => {
    const newSessions = [...sessions];
    newSessions[index] = { ...newSessions[index], [field]: value };
    
    // Auto-calculate Day if Date changes
    if (field === 'date' && value) {
      const [year, month, day] = value.split('-');
      if (year && month && day) {
        const dateObj = new Date(year, month - 1, day);
        const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
        newSessions[index].day_of_week = days[dateObj.getDay()];
      }
    }
    
    setSessions(newSessions);
  };

  const handleAddSession = () => {
    setSessions([
      ...sessions,
      {
        day_of_week: '-',
        date: '',
        topic: '',
        module: '',
        co: '',
        teaching_method: '',
        assessment: '',
        hours: 1
      }
    ]);
  };

  const handleRemoveSession = (index) => {
    const newSessions = [...sessions];
    newSessions.splice(index, 1);
    setSessions(newSessions);
  };

  const handleExport = async (format = 'pdf') => {
    try {
      setSaving(true);
      let blob;
      if (format === 'pdf') blob = await lessonPlanService.exportPdf(id);
      else if (format === 'docx') blob = await lessonPlanService.exportDocx(id);
      else if (format === 'xlsx') blob = await lessonPlanService.exportXlsx(id);
      
      const url = window.URL.createObjectURL(new Blob([blob]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `Lesson_Plan_${plan.course_code}.${format}`);
      document.body.appendChild(link);
      link.click();
      link.parentNode.removeChild(link);
    } catch (error) {
      console.error("Failed to export:", error);
      alert("Failed to export lesson plan.");
    } finally {
      setSaving(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      const payload = { ...plan, sessions };
      await lessonPlanService.update(id, payload);
      alert("Lesson plan saved successfully!");
    } catch (error) {
      console.error("Failed to save:", error);
      alert("Failed to save changes.");
    } finally {
      setSaving(false);
    }
  };

  const handleApprove = async () => {
    try {
      setSaving(true);
      const payload = { ...plan, sessions, status: 'Approved' };
      await lessonPlanService.update(id, payload);
      setPlan(payload);
      alert("Lesson plan approved!");
    } catch (error) {
      console.error("Failed to approve:", error);
      alert("Failed to approve lesson plan.");
    } finally {
      setSaving(false);
    }
  };

  const openScheduleModal = async () => {
    try {
      setGeneratingSchedule(true);
      const [calendars, timetables] = await Promise.all([
        academicCalendarService.getAll().catch(() => []),
        timetableService.getAll().catch(() => [])
      ]);
      setAvailableCalendars(calendars);
      setAvailableTimetables(timetables);
      if (calendars.length > 0) setSelectedCalendarId(calendars[0].id || calendars[0]._id);
      if (timetables.length > 0) setSelectedTimetableId(timetables[0].id || timetables[0]._id);
      setShowScheduleModal(true);
    } catch (error) {
      console.error("Failed to fetch schedule assets:", error);
    } finally {
      setGeneratingSchedule(false);
    }
  };

  const handleGenerateSchedule = async () => {
    try {
      setGeneratingSchedule(true);
      await schedulerService.generateSchedule(plan.course_id, selectedCalendarId, selectedTimetableId);
      alert("Schedule generated successfully! The dates will now reflect the generated schedule.");
      setShowScheduleModal(false);
      // Refresh the plan to get the updated dates from the schedule (if applicable) or redirect
      window.location.reload();
    } catch (error) {
      console.error("Failed to generate schedule:", error);
      alert(error.uiMessage || "Failed to generate schedule.");
    } finally {
      setGeneratingSchedule(false);
    }
  };

  if (loading) {
    return <div className="editor-loading"><div className="spinner-large"></div><p>Loading Editor...</p></div>;
  }

  if (!plan) {
    return <div className="editor-error">Lesson Plan not found.</div>;
  }

  return (
    <div className="editor-page">
      <div className="editor-top-bar">
        <div className="top-bar-left">
          <button className="btn-icon" onClick={() => navigate('/lesson-plans')}>
            <ArrowLeft size={20} />
          </button>
          <div>
            <h1 className="editor-title">{plan.course_name} ({plan.course_code})</h1>
            <div className="editor-meta">
              <span className={`status-badge status-${plan.status?.toLowerCase().replace(' ', '-') || 'draft'}`}>
                {plan.status || 'Draft'}
              </span>
              <span className="meta-divider">•</span>
              <span>Semester {plan.semester}</span>
            </div>
          </div>
        </div>
        
        <div className="top-bar-actions">
          <button className="btn btn-secondary btn-sm" onClick={() => handleExport('pdf')} disabled={saving}>
            <Download size={16} /> Export
          </button>
          {plan.status !== 'Approved' && (
            <button className="btn btn-success btn-sm" onClick={handleApprove} disabled={saving}>
              <CheckCircle size={16} /> Approve
            </button>
          )}
          {plan.status === 'Approved' && (
            <button className="btn btn-accent btn-sm" onClick={openScheduleModal} disabled={saving || generatingSchedule}>
              <Calendar size={16} /> Generate Schedule
            </button>
          )}
          <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
            <Save size={16} /> {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>

      <div className="editor-content">
        <div className="editor-table-wrapper">
          <table className="editor-table">
            <thead>
              <tr>
                <th width="4%">No.</th>
                <th width="10%">Day</th>
                <th width="10%">Date</th>
                <th width="5%">Hrs</th>
                <th width="20%">Topic</th>
                <th width="10%">Module</th>
                <th width="10%">CO</th>
                <th width="14%">Methodology</th>
                <th width="14%">Assessment</th>
                <th width="3%"></th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((session, idx) => (
                <tr key={idx}>
                  <td className="text-center">{idx + 1}</td>
                  <td>
                    <select 
                      className="inline-input"
                      value={session.day_of_week || '-'}
                      onChange={(e) => handleSessionChange(idx, 'day_of_week', e.target.value)}
                    >
                      <option value="-">-</option>
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
                      type="date" 
                      className="inline-input"
                      value={session.date || ''} 
                      onChange={(e) => handleSessionChange(idx, 'date', e.target.value)}
                    />
                  </td>
                  <td>
                    <input 
                      type="number" 
                      className="inline-input text-center"
                      value={session.hours || 1} 
                      onChange={(e) => handleSessionChange(idx, 'hours', parseInt(e.target.value, 10))}
                      min="1"
                      max="10"
                    />
                  </td>
                  <td>
                    <textarea 
                      className="inline-textarea"
                      value={session.topic || ''}
                      onChange={(e) => handleSessionChange(idx, 'topic', e.target.value)}
                      rows={2}
                    />
                  </td>
                  <td>
                    <input 
                      type="text" 
                      className="inline-input"
                      value={session.module || ''} 
                      onChange={(e) => handleSessionChange(idx, 'module', e.target.value)}
                    />
                  </td>
                  <td>
                    <input 
                      type="text" 
                      className="inline-input"
                      value={session.co || ''} 
                      onChange={(e) => handleSessionChange(idx, 'co', e.target.value)}
                    />
                  </td>
                  <td>
                    <textarea 
                      className="inline-textarea"
                      value={session.teaching_method || ''}
                      onChange={(e) => handleSessionChange(idx, 'teaching_method', e.target.value)}
                      rows={2}
                    />
                  </td>
                  <td>
                    <textarea 
                      className="inline-textarea"
                      value={session.assessment || ''}
                      onChange={(e) => handleSessionChange(idx, 'assessment', e.target.value)}
                      rows={2}
                    />
                  </td>
                  <td className="text-center align-middle">
                    <button 
                      className="btn-icon text-danger opacity-50 hover-opacity-100" 
                      onClick={() => handleRemoveSession(idx)}
                      title="Remove Session"
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="editor-table-footer p-3 border-top d-flex justify-content-center">
          <button className="btn btn-secondary btn-sm d-flex align-items-center gap-2" onClick={handleAddSession}>
            <Plus size={16} /> Add Session Row
          </button>
        </div>
      </div>

      {showScheduleModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <h2>Generate Schedule</h2>
              <button className="btn-icon" onClick={() => setShowScheduleModal(false)}><X size={20} /></button>
            </div>
            <div className="modal-body">
              <p className="mb-4 text-secondary">
                Select the Academic Calendar and Faculty Timetable to use for scheduling this course. 
                The system will automatically allocate the topics to the available dates and periods.
              </p>
              
              <div className="form-group mb-4">
                <label className="form-label">Academic Calendar</label>
                <select 
                  className="form-control" 
                  value={selectedCalendarId} 
                  onChange={(e) => setSelectedCalendarId(e.target.value)}
                >
                  {availableCalendars.length === 0 && <option value="">No Calendars Available</option>}
                  {availableCalendars.map(cal => (
                    <option key={cal._id || cal.id} value={cal._id || cal.id}>
                      {cal.name || `${cal.academic_year} (Sem ${cal.semester})`}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group mb-4">
                <label className="form-label">Faculty Timetable</label>
                <select 
                  className="form-control" 
                  value={selectedTimetableId} 
                  onChange={(e) => setSelectedTimetableId(e.target.value)}
                >
                  {availableTimetables.length === 0 && <option value="">No Timetables Available</option>}
                  {availableTimetables.map(tt => (
                    <option key={tt._id || tt.id} value={tt._id || tt.id}>
                      {tt.name || `Timetable ${tt.academic_year}`}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowScheduleModal(false)}>Cancel</button>
              <button 
                className="btn btn-primary" 
                onClick={handleGenerateSchedule} 
                disabled={generatingSchedule || !selectedCalendarId || !selectedTimetableId}
              >
                {generatingSchedule ? 'Generating...' : 'Generate Schedule'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LessonPlanEditor;
