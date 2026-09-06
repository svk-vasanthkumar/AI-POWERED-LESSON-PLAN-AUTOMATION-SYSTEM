import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  ArrowLeft, Calendar, Clock, CheckCircle, XCircle, 
  AlertTriangle, CheckSquare, MessageSquare, BookOpen, SkipForward,
  Edit, Undo
} from 'lucide-react';
import { schedulerService } from '../../services/schedulerService';
import { useAlert } from '../../context/AlertContext';
import './CourseProgress.css';

const CourseProgress = () => {
  const { courseId } = useParams();
  const navigate = useNavigate();
  const { showAlert } = useAlert();
  
  const [progressData, setProgressData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  // Modals state
  const [showCompleteModal, setShowCompleteModal] = useState(false);
  const [showRescheduleModal, setShowRescheduleModal] = useState(false);
  const [selectedSession, setSelectedSession] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isEditingComplete, setIsEditingComplete] = useState(false);
  
  // Form States
  const [completeData, setCompleteData] = useState({
    actual_hours: '',
    actual_topics: '',
    remarks: '',
    executed_date: ''
  });
  
  const [rescheduleData, setRescheduleData] = useState({
    new_date: '',
    new_period_start: '',
    new_period_end: '',
    remarks: ''
  });

  const fetchProgress = async () => {
    try {
      setLoading(true);
      const data = await schedulerService.getProgress(courseId);
      setProgressData(data);
    } catch (err) {
      console.error(err);
      setError(err.response?.data?.detail || 'Failed to load progress data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProgress();
  }, [courseId]);

  const handleOpenComplete = (session, isEdit = false) => {
    setSelectedSession(session);
    setIsEditingComplete(isEdit);
    setCompleteData({
      actual_hours: session.actual_hours || session.duration_hours || '',
      actual_topics: session.actual_topics || session.topic || '',
      remarks: session.faculty_remarks || '',
      executed_date: session.actual_date ? session.actual_date.split('T')[0] : (session.rescheduled_date ? session.rescheduled_date.split('T')[0] : session.date.split('T')[0])
    });
    setShowCompleteModal(true);
  };

  const handleOpenReschedule = (session) => {
    setSelectedSession(session);
    setRescheduleData({
      new_date: '',
      new_period_start: session.period_start || '',
      new_period_end: session.period_end || '',
      remarks: ''
    });
    setShowRescheduleModal(true);
  };

  const handleCompleteSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await schedulerService.updateSession(courseId, selectedSession.session_id, {
        status: 'completed',
        executed_date: completeData.executed_date,
        actual_hours: completeData.actual_hours || undefined,
        actual_topics: completeData.actual_topics || undefined,
        remarks: completeData.remarks || undefined
      });
      setShowCompleteModal(false);
      fetchProgress(); // Refresh data
    } catch (err) {
      showAlert(err.response?.data?.detail || 'Failed to complete session', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRescheduleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await schedulerService.rescheduleSession(courseId, selectedSession.session_id, {
        new_date: rescheduleData.new_date,
        new_period_start: rescheduleData.new_period_start ? parseInt(rescheduleData.new_period_start) : undefined,
        new_period_end: rescheduleData.new_period_end ? parseInt(rescheduleData.new_period_end) : undefined,
        remarks: rescheduleData.remarks || undefined
      });
      setShowRescheduleModal(false);
      fetchProgress();
    } catch (err) {
      showAlert(err.response?.data?.detail || 'Failed to reschedule session', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSkipSession = async (session) => {
    if(!window.confirm('Are you sure you want to skip this session?')) return;
    try {
      await schedulerService.updateSession(courseId, session.session_id, {
        status: 'skipped'
      });
      fetchProgress();
    } catch(err) {
      showAlert(err.response?.data?.detail || 'Failed to skip session', 'error');
    }
  };

  const handleMarkIncomplete = async (session) => {
    if(!window.confirm('Are you sure you want to mark this session as incomplete (Pending)?')) return;
    try {
      await schedulerService.updateSession(courseId, session.session_id, {
        status: 'pending'
      });
      fetchProgress();
    } catch(err) {
      showAlert(err.response?.data?.detail || 'Failed to mark incomplete', 'error');
    }
  };

  if (loading) return <div className="text-center py-5">Loading Progress...</div>;
  if (error) return <div className="alert alert-error m-4">{error}</div>;
  if (!progressData) return <div className="text-center py-5">No active schedule found for this course.</div>;

  const summary = progressData.summary || {};
  const sessions = progressData.sessions || [];

  return (
    <div className="course-progress-page">
      <div className="page-header flex-between mb-4">
        <div>
          <button className="btn btn-outline text-secondary mb-2" onClick={() => navigate('/progress')}>
            <ArrowLeft size={16} className="mr-2" /> Back to Courses
          </button>
          <h1 className="page-title">Session Progress</h1>
          <p className="page-subtitle">Update session statuses for this course.</p>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="progress-summary-grid">
        <div className="summary-card">
          <div className="summary-icon bg-blue-light text-blue"><CheckSquare size={24} /></div>
          <div>
            <h3>{summary.completion_percentage}%</h3>
            <p>Overall Completion</p>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon bg-green-light text-green"><BookOpen size={24} /></div>
          <div>
            <h3>{summary.completed_sessions} / {summary.total_sessions}</h3>
            <p>Sessions Completed</p>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon bg-orange-light text-orange"><Clock size={24} /></div>
          <div>
            <h3>{summary.pending_sessions}</h3>
            <p>Pending Sessions</p>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon bg-red-light text-red"><AlertTriangle size={24} /></div>
          <div>
            <h3>{summary.deviation_percentage}%</h3>
            <p>Deviation Rate</p>
          </div>
        </div>
      </div>

      {/* Timeline */}
      <div className="mt-5">
        <h2 className="mb-4">Schedule Timeline</h2>
        <div className="sessions-timeline">
        {sessions.map((session, index) => {
          const isPending = session.status === 'pending' || session.status === 'rescheduled';
          const isCompleted = session.status === 'completed';
          const isSkipped = session.status === 'skipped';
          const isRescheduled = session.status === 'rescheduled';
          
          let statusBadgeClass = 'badge-secondary';
          if(isCompleted) statusBadgeClass = 'badge-success';
          if(isRescheduled) statusBadgeClass = 'badge-warning';
          if(isSkipped) statusBadgeClass = 'badge-error';

          // Determine display date
          const displayDate = session.rescheduled_date ? session.rescheduled_date.split('T')[0] : (session.date ? session.date.split('T')[0] : 'TBD');
          const pStart = session.rescheduled_period_start || session.period_start;
          const pEnd = session.rescheduled_period_end || session.period_end;
          const displayPeriod = pStart === pEnd ? pStart : `${pStart}-${pEnd}`;

          return (
            <div key={session.session_id} className={`timeline-item ${isCompleted ? 'completed' : ''}`}>
              <div className="timeline-marker">
                {isCompleted ? <CheckCircle size={20} className="text-success" /> : 
                 isSkipped ? <XCircle size={20} className="text-error" /> : 
                 <div className="timeline-dot"></div>}
              </div>
              <div className="timeline-content">
                <div className="session-header flex-between">
                  <div className="session-date-info flex items-center">
                    <span className="font-semibold" style={{ display: 'flex', alignItems: 'center', marginRight: '12px' }}>
                      <Calendar size={14} style={{ marginRight: '4px' }}/> {displayDate}
                    </span>
                    <span className="text-secondary" style={{ display: 'flex', alignItems: 'center' }}>
                      <Clock size={14} style={{ marginRight: '4px' }}/> {displayPeriod ? `Hour ${displayPeriod}` : ''}
                    </span>
                    {isRescheduled && <span style={{ marginLeft: '8px' }} className="text-warning text-sm">(Rescheduled from {session.date.split('T')[0]})</span>}
                  </div>
                  <span className={`badge ${statusBadgeClass}`} style={{ textTransform: 'uppercase', fontSize: '0.75rem' }}>{session.status || 'pending'}</span>
                </div>
                
                <div className="session-body mt-2">
                  <h4 className="font-semibold text-lg">{session.topic}</h4>
                  
                  {/* Important Feature: Faculty Remarks and Actual Topics */}
                  {session.actual_topics && session.actual_topics !== session.topic && (
                    <div className="actual-topics" style={{ marginTop: '8px', padding: '8px', backgroundColor: '#f8fafc', borderRadius: '4px', border: '1px solid #e2e8f0', fontSize: '0.9rem' }}>
                      <strong>Actually Covered:</strong> {session.actual_topics}
                    </div>
                  )}
                  {session.faculty_remarks && (
                    <div className="faculty-remarks" style={{ marginTop: '8px', display: 'flex', alignItems: 'flex-start', color: 'var(--text-secondary)' }}>
                      <MessageSquare size={16} style={{ marginRight: '8px', marginTop: '3px', flexShrink: 0 }} />
                      <span style={{ fontStyle: 'italic' }}>{session.faculty_remarks}</span>
                    </div>
                  )}
                </div>

                {/* Actions */}
                {isPending && (
                  <div className="session-actions mt-3 pt-3 border-t">
                    <button className="btn btn-sm btn-primary mr-2" onClick={() => handleOpenComplete(session)}>
                      <CheckCircle size={14} className="mr-1" /> Mark Complete
                    </button>
                    <button className="btn btn-sm btn-outline text-warning border-warning mr-2" onClick={() => handleOpenReschedule(session)}>
                      <Clock size={14} className="mr-1" /> Reschedule
                    </button>
                    <button className="btn btn-sm btn-outline text-error border-error" onClick={() => handleSkipSession(session)}>
                      <SkipForward size={14} className="mr-1" /> Skip
                    </button>
                  </div>
                )}
                {isCompleted && (
                  <div className="session-actions mt-3 pt-3 border-t">
                    <button className="btn btn-sm btn-outline text-primary border-primary mr-2" onClick={() => handleOpenComplete(session, true)}>
                      <Edit size={14} className="mr-1" /> Edit Progress
                    </button>
                    <button className="btn btn-sm btn-outline text-warning border-warning" onClick={() => handleMarkIncomplete(session)}>
                      <Undo size={14} className="mr-1" /> Mark Incomplete
                    </button>
                  </div>
                )}
              </div>
            </div>
          )
        })}
        </div>
      </div>

      {/* Complete Modal */}
      {showCompleteModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <h2>{isEditingComplete ? 'Edit Completed Session' : 'Complete Session'}</h2>
              <button className="btn-icon" onClick={() => setShowCompleteModal(false)}><XCircle size={20}/></button>
            </div>
            <form onSubmit={handleCompleteSubmit}>
              <div className="modal-body">
                <div className="form-group mb-3">
                  <label>Executed Date</label>
                  <input type="date" className="form-control" value={completeData.executed_date} onChange={(e) => setCompleteData({...completeData, executed_date: e.target.value})} required/>
                </div>
                <div className="form-group mb-3">
                  <label>Actual Topics Covered</label>
                  <textarea className="form-control" rows="2" value={completeData.actual_topics} onChange={(e) => setCompleteData({...completeData, actual_topics: e.target.value})} placeholder="Did you cover everything planned?" disabled={isEditingComplete}></textarea>
                </div>
                <div className="form-group mb-3">
                  <label>Faculty Remarks <span className="text-error">*</span></label>
                  <textarea className="form-control" rows="2" value={completeData.remarks} onChange={(e) => setCompleteData({...completeData, remarks: e.target.value})} placeholder="Any observations, pending items, or student feedback..." required disabled={isEditingComplete}></textarea>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowCompleteModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={isSubmitting}>{isSubmitting ? 'Saving...' : 'Save'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Reschedule Modal */}
      {showRescheduleModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <h2>Reschedule Session</h2>
              <button className="btn-icon" onClick={() => setShowRescheduleModal(false)}><XCircle size={20}/></button>
            </div>
            <form onSubmit={handleRescheduleSubmit}>
              <div className="modal-body">
                <div className="form-group mb-3">
                  <label>New Date</label>
                  <input type="date" className="form-control" value={rescheduleData.new_date} onChange={(e) => setRescheduleData({...rescheduleData, new_date: e.target.value})} required/>
                </div>
                <div className="flex gap-4 mb-3">
                  <div className="form-group flex-1">
                    <label>New Period Start</label>
                    <input type="number" className="form-control" min="1" max="8" value={rescheduleData.new_period_start} onChange={(e) => setRescheduleData({...rescheduleData, new_period_start: e.target.value})}/>
                  </div>
                  <div className="form-group flex-1">
                    <label>New Period End</label>
                    <input type="number" className="form-control" min="1" max="8" value={rescheduleData.new_period_end} onChange={(e) => setRescheduleData({...rescheduleData, new_period_end: e.target.value})}/>
                  </div>
                </div>
                <div className="form-group mb-3">
                  <label>Remarks / Reason <span className="text-error">*</span></label>
                  <textarea className="form-control" rows="2" value={rescheduleData.remarks} onChange={(e) => setRescheduleData({...rescheduleData, remarks: e.target.value})} placeholder="Reason for rescheduling..." required></textarea>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowRescheduleModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={isSubmitting}>{isSubmitting ? 'Saving...' : 'Reschedule'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
};

export default CourseProgress;
