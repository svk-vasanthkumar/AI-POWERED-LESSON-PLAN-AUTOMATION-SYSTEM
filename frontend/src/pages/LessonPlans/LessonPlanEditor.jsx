import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Save, ArrowLeft, Download, CheckCircle, Clock, Calendar, X, Plus, Trash2 } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { lessonPlanService } from '../../services/lessonPlanService';
import { courseService } from '../../services/courseService';
import { academicCalendarService } from '../../services/academicCalendarService';
import { timetableService } from '../../services/timetableService';
import { facultyService } from '../../services/facultyService';
import { schedulerService } from '../../services/schedulerService';
import './LessonPlanEditor.css';

const LessonPlanEditor = () => {
  const { user } = useAuth();
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
  const [includeExamConfig, setIncludeExamConfig] = useState(false);
  const [examConfigs, setExamConfigs] = useState([{
    exam_type: 'CIA',
    start_date: '',
    end_date: '',
    exam_days: ['Monday', 'Saturday'],
    duration: 2
  }]);

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
                  hours: topic.estimated_hours || 1,
                  topic_id: topic.topic_id,
                  unit_number: unit.unit_number,
                  unit_title: unit.unit_title
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
        hours: 1,
        session_type: 'class'
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
      const [calendars, timetables, courses, faculties] = await Promise.all([
        academicCalendarService.getAll().catch(() => []),
        timetableService.getAll().catch(() => []),
        courseService.getAll().catch(() => []),
        facultyService.getAll().catch(() => [])
      ]);
      setAvailableCalendars(calendars);
      
      // Enrich timetables with course and faculty names for the dropdown
      const enrichedTimetables = timetables.map(tt => {
        const course = courses.find(c => (c.id || c._id) === tt.course_id);
        const faculty = faculties.find(f => (f.id || f._id) === tt.faculty_id);
        const courseStr = course ? `${course.course_code || ''} ${course.course_name || ''}`.trim() || 'Unknown Course' : 'Unknown Course';
        const facultyStr = faculty ? faculty.name : 'Unknown Faculty';
        const ttName = tt.name || (tt.academic_year ? `Timetable ${tt.academic_year}` : (tt.semester ? `Timetable (Sem ${tt.semester})` : 'Timetable'));
        
        return {
          ...tt,
          displayName: `${ttName} | ${facultyStr} | ${courseStr}`
        };
      });
      
      setAvailableTimetables(enrichedTimetables);
      
      if (calendars.length > 0) setSelectedCalendarId(calendars[0]._id || calendars[0].id);
      if (enrichedTimetables.length > 0) setSelectedTimetableId(enrichedTimetables[0]._id || enrichedTimetables[0].id);
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
      const validConfigs = examConfigs.filter(c => c.start_date && c.end_date);
      const payload = includeExamConfig && validConfigs.length > 0 ? validConfigs : undefined;
      const schedule = await schedulerService.generateSchedule(plan.course_id, selectedCalendarId, selectedTimetableId, payload);
      
      // Save the generated sessions to the lesson plan so they persist in the editor
      if (schedule && schedule.sessions && schedule.sessions.length > 0) {
        // Map backend scheduler sessions to the editor format,
        // merging with existing user-edited content by topic name.
        const mergedSessions = schedule.sessions.map((schedSession) => {
          // Find matching existing session by topic text
          const existingSession = sessions.find(s => s.topic === schedSession.topic);
          
          // Format the date for display (backend returns ISO date string e.g. "2026-07-11")
          const dateStr = schedSession.date || '';
          let dayOfWeek = schedSession.day || schedSession.timetable_day || '-';
          
          // Determine the period/hour display
          let periodDisplay = '';
          if (schedSession.period_start !== undefined && schedSession.period_start !== null) {
            periodDisplay = `Hour ${schedSession.period_start}`;
            if (schedSession.period_end && schedSession.period_end !== schedSession.period_start) {
              periodDisplay += `-${schedSession.period_end}`;
            }
          }
          
          return {
            day_of_week: dayOfWeek,
            date: dateStr,
            topic: schedSession.session_type === 'exam' ? `${schedSession.exam_type || 'CIA'} Exam` : (schedSession.topic || ''),
            session_type: schedSession.session_type || 'class',
            exam_type: schedSession.exam_type || 'CIA',
            module: existingSession?.module || `Unit ${schedSession.unit_number || ''}`,
            co: existingSession?.co || 'N/A',
            teaching_method: existingSession?.teaching_method || '-',
            assessment: existingSession?.assessment || '-',
            hours: schedSession.duration_hours || 1,
            period: periodDisplay,
            // Keep scheduler metadata for reference
            session_id: schedSession.session_id,
            topic_id: schedSession.topic_id,
            unit_number: schedSession.unit_number,
            unit_title: schedSession.unit_title,
            status: schedSession.status || 'pending',
          };
        });
        
        // Append any topics that couldn't fit in the timeline (unscheduled)
        // so they aren't lost from the editor.
        if (schedule.unscheduled_topics && schedule.unscheduled_topics.length > 0) {
          schedule.unscheduled_topics.forEach((unsched) => {
            const existingSession = sessions.find(s => s.topic === unsched.topic);
            mergedSessions.push({
              day_of_week: '-',
              date: '',
              topic: unsched.topic || '',
              module: existingSession?.module || `Unit ${unsched.unit_number || ''}`,
              co: existingSession?.co || 'N/A',
              teaching_method: existingSession?.teaching_method || '-',
              assessment: existingSession?.assessment || '-',
              hours: unsched.remaining_hours || 1,
              period: '',
              topic_id: unsched.topic_id,
              unit_number: unsched.unit_number,
              status: 'pending',
            });
          });
        }
        
        await lessonPlanService.update(id, { ...plan, sessions: mergedSessions });
        
        if (schedule.unscheduled_topics && schedule.unscheduled_topics.length > 0) {
          alert(`Schedule generated, but ${schedule.unscheduled_topics.length} topics could not fit before the semester ends! They have been added to the bottom of the list without dates.`);
        } else {
          alert("Schedule generated successfully! All topics were scheduled.");
        }
      } else {
        alert("Schedule generation did not return any sessions.");
      }
      
      setShowScheduleModal(false);
      window.location.reload();
    } catch (error) {
      console.error("Failed to generate schedule:", error);
      const errorDetail = error.response?.data?.detail || error.uiMessage || "Failed to generate schedule.";
      alert(errorDetail);
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
          <button className="btn btn-secondary btn-sm" onClick={() => handleExport('pdf')} disabled={saving} title="Export as PDF">
            <Download size={14} /> PDF
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => handleExport('docx')} disabled={saving} title="Export as Word">
            <Download size={14} /> Word
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => handleExport('xlsx')} disabled={saving} title="Export as Excel">
            <Download size={14} /> Excel
          </button>
          
          {(user?.role === 'hod' || user?.role === 'admin') && plan.status !== 'Approved' && (
            <button className="btn btn-success btn-sm" onClick={handleApprove} disabled={saving}>
              <CheckCircle size={16} /> Approve
            </button>
          )}
          
          <button className="btn btn-accent btn-sm" onClick={openScheduleModal} disabled={saving || generatingSchedule}>
            <Calendar size={16} /> Generate Schedule
          </button>
          
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
                <th width="11%">Date</th>
                <th width="6%">Planned Periods</th>
                <th width="20%">Topic</th>
                <th width="10%">Module</th>
                <th width="10%">CO</th>
                <th width="13%">Teaching Pedagogy</th>
                <th width="13%">Assessment</th>
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
                      type="text" 
                      className="inline-input text-center"
                      value={session.period || ''} 
                      onChange={(e) => handleSessionChange(idx, 'period', e.target.value)}
                    />
                  </td>
                  <td>
                    {session.session_type === 'exam' ? (
                      <div className="d-flex align-items-center h-100 px-2 text-danger fw-bold">
                        {session.exam_type || 'CIA'} Exam
                      </div>
                    ) : (
                      <textarea 
                        className="inline-textarea"
                        value={session.topic || ''}
                        onChange={(e) => handleSessionChange(idx, 'topic', e.target.value)}
                        rows={2}
                      />
                    )}
                  </td>
                  <td>
                    <select 
                      className="inline-input"
                      value={session.module || ''} 
                      onChange={(e) => handleSessionChange(idx, 'module', e.target.value)}
                    >
                      <option value="">-</option>
                      <option value="Unit 1">Unit 1</option>
                      <option value="Unit 2">Unit 2</option>
                      <option value="Unit 3">Unit 3</option>
                      <option value="Unit 4">Unit 4</option>
                      <option value="Unit 5">Unit 5</option>
                    </select>
                  </td>
                  <td>
                    <select 
                      className="inline-input"
                      value={session.co || ''} 
                      onChange={(e) => handleSessionChange(idx, 'co', e.target.value)}
                    >
                      <option value="">-</option>
                      <option value="CO1">CO1</option>
                      <option value="CO2">CO2</option>
                      <option value="CO3">CO3</option>
                      <option value="CO4">CO4</option>
                      <option value="CO5">CO5</option>
                      <option value="CO6">CO6</option>
                    </select>
                  </td>
                  <td>
                    {session.session_type === 'exam' ? (
                      <span className="text-muted">-</span>
                    ) : (
                      <select 
                        className="inline-input"
                        value={session.teaching_method || ''}
                        onChange={(e) => handleSessionChange(idx, 'teaching_method', e.target.value)}
                      >
                        <option value="">-</option>
                        <option value="Chalk & Talk">Chalk & Talk</option>
                        <option value="NPTEL/OBL">NPTEL/OBL</option>
                        <option value="Group Learning and Teaching">Group Learning and Teaching</option>
                        <option value="Individual Learning/Self-study">Individual Learning/Self-study</option>
                        <option value="Game based learning">Game based learning</option>
                        <option value="Technology based learning">Technology based learning</option>
                        <option value="Peer teaching">Peer teaching</option>
                        <option value="Learning through problem solving">Learning through problem solving</option>
                        <option value="Project based learning">Project based learning</option>
                        <option value="Flipped Class room">Flipped Class room</option>
                      </select>
                    )}
                  </td>
                  <td>
                    <select 
                      className="inline-input"
                      value={session.assessment || ''}
                      onChange={(e) => handleSessionChange(idx, 'assessment', e.target.value)}
                    >
                      <option value="">-</option>
                      <option value="Quiz">Quiz</option>
                      <option value="Internal Assessment">Internal Assessment</option>
                      <option value="Assignment">Assignment</option>
                      <option value="Presentation">Presentation</option>
                      <option value="Project Review">Project Review</option>
                      <option value="Viva">Viva</option>
                    </select>
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
                  onChange={(e) => {
                    setSelectedCalendarId(e.target.value);
                    const cal = availableCalendars.find(c => (c._id || c.id) === e.target.value);
                    if (cal && includeExamConfig) {
                      const type = examConfigs[0].exam_type;
                      let dateRange = null;
                      if (type === 'CIA 1') dateRange = cal.cia_1;
                      else if (type === 'CIA 2') dateRange = cal.cia_2;
                      else if (type === 'CIA 3') dateRange = cal.cia_3;
                      else if (type === 'Model Theory') dateRange = cal.model_theory;
                      else if (type === 'Model Practical') dateRange = cal.model_practical;
                      
                      if (dateRange && dateRange.start_date && dateRange.end_date) {
                        setExamConfigs([{
                          ...examConfigs[0],
                          start_date: dateRange.start_date.split('T')[0],
                          end_date: dateRange.end_date.split('T')[0]
                        }]);
                      }
                    }
                  }}
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
                      {tt.displayName || tt.name || (tt.academic_year ? `Timetable ${tt.academic_year}` : (tt.semester ? `Timetable (Sem ${tt.semester})` : 'Timetable'))}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group mb-4">
                <div className="d-flex align-items-center mb-3">
                  <input 
                    type="checkbox" 
                    id="includeExamConfig" 
                    checked={includeExamConfig}
                    onChange={(e) => setIncludeExamConfig(e.target.checked)}
                    className="me-2"
                  />
                  <label htmlFor="includeExamConfig" className="form-label mb-0 fw-bold">Include Exam / Special Scheduling</label>
                </div>
                
                {includeExamConfig && (() => {
                  const cal = availableCalendars.find(c => (c._id || c.id) === selectedCalendarId);
                  
                  // Helper: parse a dateRange from calendar into YYYY-MM-DD string
                  const parseDate = (val) => {
                    if (!val) return null;
                    const s = typeof val === 'string' ? val : (val.$date || String(val));
                    return s.split('T')[0];
                  };
                  
                  // Map exam type to calendar field key
                  const EXAM_TYPE_FIELD_MAP = {
                    'CIA 1': 'cia_1',
                    'CIA 2': 'cia_2',
                    'CIA 3': 'cia_3',
                    'Model Theory': 'model_theory',
                    'Model Practical': 'model_practical',
                    'Semester End Theory': 'semester_end_theory',
                    'Semester End Practical': 'semester_end_practical',
                  };
                  
                  // Build option labels with available dates from calendar
                  const formatOptionLabel = (type) => {
                    const field = EXAM_TYPE_FIELD_MAP[type];
                    if (!field || !cal) return type;
                    const range = cal[field];
                    if (range && range.start_date && range.end_date) {
                      const s = parseDate(range.start_date);
                      const e = parseDate(range.end_date);
                      return `${type}  (${s} → ${e})`;
                    }
                    return `${type}  (no dates in calendar)`;
                  };

                  const handleUpdateConfig = (index, field, value) => {
                    const newConfigs = [...examConfigs];
                    newConfigs[index] = { ...newConfigs[index], [field]: value };
                    
                    if (field === 'exam_type') {
                      const calField = EXAM_TYPE_FIELD_MAP[value];
                      if (cal && calField) {
                        const range = cal[calField];
                        if (range && range.start_date && range.end_date) {
                          newConfigs[index].start_date = parseDate(range.start_date);
                          newConfigs[index].end_date = parseDate(range.end_date);
                        } else {
                          newConfigs[index].start_date = '';
                          newConfigs[index].end_date = '';
                        }
                      }
                    }
                    setExamConfigs(newConfigs);
                  };

                  const handleAddConfig = () => {
                    setExamConfigs([...examConfigs, {
                      exam_type: 'CIA 2',
                      start_date: '',
                      end_date: '',
                      exam_days: ['Monday', 'Saturday'],
                      duration: 2
                    }]);
                  };

                  const handleRemoveConfig = (index) => {
                    const newConfigs = examConfigs.filter((_, i) => i !== index);
                    setExamConfigs(newConfigs.length > 0 ? newConfigs : [{
                      exam_type: 'CIA',
                      start_date: '',
                      end_date: '',
                      exam_days: ['Monday', 'Saturday'],
                      duration: 2
                    }]);
                  };
                  
                  return (
                  <div className="p-3 border rounded bg-light">
                    {examConfigs.map((config, index) => {
                      const selectedField = EXAM_TYPE_FIELD_MAP[config.exam_type];
                      const calDateRange = cal && selectedField ? cal[selectedField] : null;
                      const hasCalendarDates = calDateRange && calDateRange.start_date && calDateRange.end_date;
                      
                      return (
                        <div key={index} className="mb-4 pb-3" style={index < examConfigs.length - 1 ? { borderBottom: '1px solid #dee2e6' } : {}}>
                          {cal && (
                            <div className="d-flex justify-content-between align-items-center mb-3">
                              <div style={{ padding: '0.5rem 0.75rem', borderRadius: '6px', 
                                background: hasCalendarDates ? '#e6f4ea' : '#fff3cd',
                                border: `1px solid ${hasCalendarDates ? '#34a853' : '#ffc107'}`,
                                fontSize: '0.82rem', color: hasCalendarDates ? '#1e7e34' : '#856404'
                              }}>
                                {hasCalendarDates 
                                  ? `✅ Dates auto-filled from ${cal.academic_year} (Sem ${cal.semester}) calendar`
                                  : `⚠️ No dates found for "${config.exam_type}" in the selected calendar. Enter manually below, or update the Academic Calendar first.`
                                }
                              </div>
                              {examConfigs.length > 1 && (
                                <button className="btn btn-sm btn-outline-danger" onClick={() => handleRemoveConfig(index)}>
                                  Remove
                                </button>
                              )}
                            </div>
                          )}
                          <div className="row mb-3">
                            <div className="col-md-6">
                              <label className="form-label">Exam Type</label>
                              <select 
                                className="form-control"
                                value={config.exam_type}
                                onChange={(e) => handleUpdateConfig(index, 'exam_type', e.target.value)}
                              >
                                <option value="CIA">CIA (General)</option>
                                {Object.keys(EXAM_TYPE_FIELD_MAP).map(type => (
                                  <option key={type} value={type}>{formatOptionLabel(type)}</option>
                                ))}
                                <option value="Unit Test">Unit Test</option>
                              </select>
                            </div>
                            <div className="col-md-6">
                              <label className="form-label">Exam Duration (Hours)</label>
                              <input 
                                type="number" 
                                className="form-control"
                                value={config.duration}
                                onChange={(e) => handleUpdateConfig(index, 'duration', parseInt(e.target.value, 10))}
                                min="1" max="7"
                              />
                            </div>
                          </div>
                          
                          <div className="row mb-3">
                            <div className="col-md-6">
                              <label className="form-label">Start Date</label>
                              <input 
                                type="date" 
                                className="form-control"
                                value={config.start_date}
                                onChange={(e) => handleUpdateConfig(index, 'start_date', e.target.value)}
                              />
                            </div>
                            <div className="col-md-6">
                              <label className="form-label">End Date</label>
                              <input 
                                type="date" 
                                className="form-control"
                                value={config.end_date}
                                onChange={(e) => handleUpdateConfig(index, 'end_date', e.target.value)}
                              />
                            </div>
                          </div>
                          
                          <div>
                            <label className="form-label d-block">Exam Days</label>
                            <div className="d-flex flex-wrap gap-2">
                              {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'].map(day => (
                                <div key={day} className="form-check form-check-inline">
                                  <input 
                                    className="form-check-input" 
                                    type="checkbox" 
                                    id={`exam-day-${index}-${day}`}
                                    checked={config.exam_days.includes(day)}
                                    onChange={(e) => {
                                      const newDays = e.target.checked 
                                        ? [...config.exam_days, day]
                                        : config.exam_days.filter(d => d !== day);
                                      handleUpdateConfig(index, 'exam_days', newDays);
                                    }}
                                  />
                                  <label className="form-check-label" htmlFor={`exam-day-${index}-${day}`}>{day}</label>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                    <button className="btn btn-outline-primary btn-sm w-100 mt-2" onClick={handleAddConfig}>
                      + Add Another Exam
                    </button>
                  </div>
                  );
                })()}
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
