import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  ArrowLeft, Calendar, Clock, CheckCircle, XCircle, 
  AlertTriangle, CheckSquare, MessageSquare, BookOpen, SkipForward,
  Edit, Undo, Eye, Send, RefreshCw, Hourglass, ShieldCheck
} from 'lucide-react';
import { schedulerService } from '../../services/schedulerService';
import { useAuth } from '../../context/AuthContext';
import { useAlert } from '../../context/AlertContext';
import CustomSelect from '../../components/common/CustomSelect';
import './CourseProgress.css';

// ── Status Config ──────────────────────────────────────────────────────────
const STATUS_CONFIG = {
  completed: {
    label: 'Completed',
    icon: <CheckCircle size={15} />,
    badgeClass: 'status-chip status-chip-completed',
    markerClass: 'marker-completed',
    markerIcon: <CheckCircle size={20} />,
    cardClass: 'timeline-card-completed',
  },
  rescheduled: {
    label: 'Rescheduled',
    icon: <RefreshCw size={15} />,
    badgeClass: 'status-chip status-chip-rescheduled',
    markerClass: 'marker-rescheduled',
    markerIcon: <RefreshCw size={14} />,
    cardClass: 'timeline-card-rescheduled',
  },
  pending: {
    label: 'Pending',
    icon: <Hourglass size={15} />,
    badgeClass: 'status-chip status-chip-pending',
    markerClass: 'marker-pending',
    markerIcon: null,
    cardClass: '',
  },
  skipped: {
    label: 'Skipped',
    icon: <XCircle size={15} />,
    badgeClass: 'status-chip status-chip-skipped',
    markerClass: 'marker-skipped',
    markerIcon: <XCircle size={20} />,
    cardClass: 'timeline-card-skipped',
  },
};

const getStatusConfig = (status) => STATUS_CONFIG[status] || STATUS_CONFIG.pending;

// ── HOD Remarks Read-Only View (for Admin) ─────────────────────────────────
const HodRemarksView = ({ remarks }) => {
  if (!remarks || remarks.length === 0) return null;
  return (
    <div className="hod-remarks-block">
      <div className="hod-remarks-header">
        <ShieldCheck size={14} />
        <span>Supervisory Feedback</span>
      </div>
      {remarks.map((r, i) => (
        <div key={i} className={`hod-remark-item${i < remarks.length - 1 ? ' hod-remark-item--bordered' : ''}`}>
          <div className="hod-remark-meta">
            <span className="hod-remark-author">{r.author_name}</span>
            <span className="hod-remark-date">{new Date(r.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
          </div>
          <p className="hod-remark-text">{r.remark}</p>
        </div>
      ))}
    </div>
  );
};

// ── Main Component ─────────────────────────────────────────────────────────
const CourseProgress = () => {
  const { courseId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { showAlert, showConfirm } = useAlert();
  
  const [progressData, setProgressData] = useState(null);
  const [availableDates, setAvailableDates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  // Modals state
  const [showCompleteModal, setShowCompleteModal] = useState(false);
  const [showRescheduleModal, setShowRescheduleModal] = useState(false);
  const [showHodRemarkModal, setShowHodRemarkModal] = useState(false);
  const [selectedSession, setSelectedSession] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isEditingComplete, setIsEditingComplete] = useState(false);
  const [hodRemark, setHodRemark] = useState('');

  // Form States
  const [completeData, setCompleteData] = useState({
    actual_hours: '',
    actual_topics: '',
    remarks: '',
    executed_date: '',
    executed_period: ''
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
      const [data, datesData] = await Promise.all([
        schedulerService.getProgress(courseId),
        schedulerService.getAvailableDates(courseId).catch(() => ({ dates: [] }))
      ]);
      setProgressData(data);
      if (datesData && datesData.dates) {
        setAvailableDates(datesData.dates);
      }
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
    
    const executedDate = session.actual_date
      ? session.actual_date.split('T')[0]
      : (session.rescheduled_date ? session.rescheduled_date.split('T')[0] : session.date.split('T')[0]);
    let executedPeriod = '';
    if (session.executed_period_start && session.executed_period_end) {
      executedPeriod = `${session.executed_period_start}-${session.executed_period_end}`;
    }

    setCompleteData({
      actual_hours: session.actual_hours || session.duration_hours || '',
      actual_topics: session.actual_topics || session.topic || '',
      remarks: session.faculty_remarks || '',
      executed_date: executedDate,
      executed_period: executedPeriod
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
    
    let periodStart, periodEnd;
    if (completeData.executed_period) {
      const parts = completeData.executed_period.split('-');
      if (parts.length === 2) {
        periodStart = parseInt(parts[0]);
        periodEnd = parseInt(parts[1]);
      }
    }
    
    try {
      await schedulerService.updateSession(courseId, selectedSession.session_id, {
        status: 'completed',
        executed_date: completeData.executed_date,
        executed_period_start: periodStart,
        executed_period_end: periodEnd,
        actual_hours: completeData.actual_hours || undefined,
        actual_topics: completeData.actual_topics || undefined,
        remarks: completeData.remarks || undefined
      });
      setShowCompleteModal(false);
      fetchProgress();
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
    const confirmed = await showConfirm('Are you sure you want to skip this session?', 'Skip Session');
    if (!confirmed) return;
    try {
      await schedulerService.updateSession(courseId, session.session_id, { status: 'skipped' });
      fetchProgress();
    } catch (err) {
      showAlert(err.response?.data?.detail || 'Failed to skip session', 'error');
    }
  };

  const handleMarkIncomplete = async (session) => {
    const confirmed = await showConfirm('Are you sure you want to mark this session as incomplete (Pending)?', 'Mark Incomplete');
    if (!confirmed) return;
    try {
      await schedulerService.updateSession(courseId, session.session_id, { status: 'pending' });
      fetchProgress();
    } catch (err) {
      showAlert(err.response?.data?.detail || 'Failed to mark incomplete', 'error');
    }
  };

  const handleOpenHodRemark = (session) => {
    setSelectedSession(session);
    setHodRemark('');
    setShowHodRemarkModal(true);
  };

  const handleHodRemarkSubmit = async (e) => {
    e.preventDefault();
    if (!hodRemark.trim()) return;
    setIsSubmitting(true);
    try {
      await schedulerService.addHodRemark(courseId, selectedSession.session_id, hodRemark);
      setShowHodRemarkModal(false);
      setHodRemark('');
      showAlert('Remark added and faculty notified.', 'success');
      fetchProgress();
    } catch (err) {
      showAlert(err.response?.data?.detail || 'Failed to add remark', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Role flags
  const isHod = user?.role === 'hod';
  const isAdmin = user?.role === 'admin';
  const canTakeAction = progressData ? (progressData.is_assigned !== false) : true;

  if (loading) return (
    <div className="cp-loading-screen">
      <div className="spinner" style={{ width: 36, height: 36, borderWidth: 3 }} />
      <p>Loading Progress…</p>
    </div>
  );
  if (error) return <div className="alert alert-error m-4">{error}</div>;
  if (!progressData) {
    return (
      <div className="course-progress-page">
        <div className="page-header flex-between mb-4">
          <div>
            <button className="btn btn-sm btn-secondary mb-2" onClick={() => navigate('/progress')}>
              <ArrowLeft size={16} /> Back to Courses
            </button>
            <h1 className="page-title">Session Progress</h1>
          </div>
        </div>
        <div className="empty-state mt-5 p-5 border rounded text-center" style={{ backgroundColor: 'var(--surface-color)', borderColor: 'var(--border-color)' }}>
          <AlertTriangle size={48} className="text-warning mb-3 mx-auto" style={{ color: '#f59e0b' }} />
          <h3 className="mb-2" style={{ fontWeight: 600, color: 'var(--text-primary)' }}>No Active Schedule Found</h3>
          <p className="text-secondary mb-4" style={{ maxWidth: '400px', margin: '0 auto 1.5rem auto' }}>
            This course does not have an active session schedule yet. Please ensure the lesson plan is approved and a schedule has been generated.
          </p>
          {(isHod || isAdmin) && (
            <button className="btn btn-primary" onClick={() => navigate(`/lesson-plans/${courseId}`)}>
              View Lesson Plan
            </button>
          )}
        </div>
      </div>
    );
  }

  const summary = progressData.summary || {};
  const sessions = progressData.sessions || [];

  // Legend counts
  const completedCount = sessions.filter(s => s.status === 'completed').length;
  const pendingCount = sessions.filter(s => s.status === 'pending').length;
  const rescheduledCount = sessions.filter(s => s.status === 'rescheduled').length;
  const skippedCount = sessions.filter(s => s.status === 'skipped').length;

  return (
    <div className="course-progress-page">
      {/* Page Header */}
      <div className="page-header flex-between mb-4">
        <div>
          <button className="btn btn-sm btn-secondary mb-2" onClick={() => navigate('/progress')}>
            <ArrowLeft size={16} /> Back to Courses
          </button>
          <h1 className="page-title">Session Progress</h1>
          {isAdmin ? (
            <div className="admin-readonly-banner">
              <Eye size={15} />
              <span>Monitoring view — you can view HOD remarks but cannot add them.</span>
            </div>
          ) : canTakeAction ? (
            <p className="page-subtitle">Update session statuses for this course.</p>
          ) : (
            <div className="admin-readonly-banner">
              <Eye size={15} />
              <span>Read-only monitoring view — you are not assigned as faculty for this course.</span>
            </div>
          )}
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

      {/* Status Legend */}
      <div className="status-legend">
        <div className="status-legend-item">
          <span className="status-chip status-chip-completed"><CheckCircle size={12} /> Completed</span>
          <span className="legend-count">{completedCount}</span>
        </div>
        <div className="status-legend-item">
          <span className="status-chip status-chip-pending"><Hourglass size={12} /> Pending</span>
          <span className="legend-count">{pendingCount}</span>
        </div>
        <div className="status-legend-item">
          <span className="status-chip status-chip-rescheduled"><RefreshCw size={12} /> Rescheduled</span>
          <span className="legend-count">{rescheduledCount}</span>
        </div>
        {skippedCount > 0 && (
          <div className="status-legend-item">
            <span className="status-chip status-chip-skipped"><XCircle size={12} /> Skipped</span>
            <span className="legend-count">{skippedCount}</span>
          </div>
        )}
      </div>

      {/* Timeline */}
      <div className="mt-5">
        <h2 className="timeline-heading">Schedule Timeline</h2>
        <div className="sessions-timeline">
          {sessions.map((session) => {
            const sc = getStatusConfig(session.status);
            const isPending = session.status === 'pending';
            const isCompleted = session.status === 'completed';
            const isSkipped = session.status === 'skipped';
            const isRescheduled = session.status === 'rescheduled';

            const displayDate = session.rescheduled_date
              ? session.rescheduled_date.split('T')[0]
              : (session.date ? session.date.split('T')[0] : 'TBD');
            const pStart = session.rescheduled_period_start || session.period_start;
            const pEnd = session.rescheduled_period_end || session.period_end;
            const displayPeriod = pStart === pEnd ? pStart : `${pStart}-${pEnd}`;
            const hasHodRemarks = session.hod_remarks && session.hod_remarks.length > 0;

            return (
              <div key={session.session_id} className={`timeline-item ${sc.cardClass}`}>
                {/* Timeline marker */}
                <div className={`timeline-marker ${sc.markerClass}`}>
                  {sc.markerIcon || <div className="timeline-dot" />}
                </div>

                <div className="timeline-content">
                  {/* Session Header */}
                  <div className="session-header flex-between">
                    <div className="session-date-info">
                      <span className="session-date-chip">
                        <Calendar size={13} /> {displayDate}
                      </span>
                      {displayPeriod && (
                        <span className="session-period-chip">
                          <Clock size={13} /> Hour {displayPeriod}
                        </span>
                      )}
                      {isRescheduled && (
                        <span className="reschedule-from-chip">
                          <RefreshCw size={11} /> From {session.date.split('T')[0]}
                        </span>
                      )}
                    </div>
                    {/* Status Badge */}
                    <span className={sc.badgeClass}>
                      {sc.icon} {sc.label}
                    </span>
                  </div>

                  {/* Topic */}
                  <div className="session-body mt-2">
                    <h4 className="session-topic">{session.topic}</h4>

                    {/* Actually Covered */}
                    {session.actual_topics && session.actual_topics !== session.topic && (
                      <div className="actual-topics-chip">
                        <strong>Actually Covered:</strong> {session.actual_topics}
                      </div>
                    )}

                    {/* Faculty Remarks */}
                    {session.faculty_remarks && (
                      <div className="faculty-remarks-row">
                        <MessageSquare size={14} />
                        <span>{session.faculty_remarks}</span>
                      </div>
                    )}

                    {/* HOD Remarks — always rendered for ADMIN and HOD */}
                    {hasHodRemarks && (isAdmin || isHod) && (
                      <HodRemarksView remarks={session.hod_remarks} />
                    )}
                    
                    {/* If admin but no remarks yet — show quiet indicator */}
                    {isAdmin && !hasHodRemarks && (
                      <div className="no-hod-remarks-hint">
                        <MessageSquare size={12} /> No HOD remarks yet for this session.
                      </div>
                    )}
                  </div>

                  {/* Actions */}
                  {(canTakeAction || isHod || isAdmin) && (
                    <div className="session-actions mt-3 pt-3">
                      {/* Faculty actions (pending / completed) */}
                      {isPending && canTakeAction && !isAdmin && !isHod && (
                        <>
                          <button className="btn btn-sm btn-primary" onClick={() => handleOpenComplete(session)}>
                            <CheckCircle size={14} /> Mark Complete
                          </button>
                          <button className="btn btn-sm btn-outline-warning" onClick={() => handleOpenReschedule(session)}>
                            <Clock size={14} /> Reschedule
                          </button>
                          <button className="btn btn-sm btn-outline-danger" onClick={() => handleSkipSession(session)}>
                            <SkipForward size={14} /> Skip
                          </button>
                        </>
                      )}

                      {isCompleted && canTakeAction && !isAdmin && !isHod && (
                        <>
                          <button className="btn btn-sm btn-outline-primary" onClick={() => handleOpenComplete(session, true)}>
                            <Edit size={14} /> Edit Progress
                          </button>
                          <button className="btn btn-sm btn-outline-warning" onClick={() => handleMarkIncomplete(session)}>
                            <Undo size={14} /> Mark Incomplete
                          </button>
                        </>
                      )}

                      {/* HOD-only: Add Remark button */}
                      {isHod && (
                        <button className="btn btn-sm btn-hod-remark" onClick={() => handleOpenHodRemark(session)}>
                          <MessageSquare size={14} /> Add HOD Remark
                        </button>
                      )}

                      {/* ADMIN: view-only label instead of add button */}
                      {isAdmin && hasHodRemarks && (
                        <div className="admin-view-hint">
                          <Eye size={13} /> Viewing {session.hod_remarks.length} remark{session.hod_remarks.length > 1 ? 's' : ''}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Modals ──────────────────────────────────────────────────── */}

      {/* Complete Modal */}
      {showCompleteModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <h2>{isEditingComplete ? 'Edit Completed Session' : 'Complete Session'}</h2>
              <button className="btn-icon" onClick={() => setShowCompleteModal(false)}><XCircle size={20} /></button>
            </div>
            <form onSubmit={handleCompleteSubmit}>
              <div className="modal-body">
                <div className="form-group mb-3">
                  <label>Executed Date</label>
                  {availableDates.length > 0 ? (
                    <CustomSelect className="form-control" value={completeData.executed_date} onChange={(e) => {
                      const newDate = e.target.value;
                      const dateObj = availableDates.find(d => d.date === newDate);
                      setCompleteData({ ...completeData, executed_date: newDate, executed_period: (dateObj && dateObj.periods.length > 0) ? `${dateObj.periods[0].start}-${dateObj.periods[0].end}` : '' });
                    }} required>
                      <option value="">Select a valid teaching date...</option>
                      {availableDates.map(d => (
                        <option key={d.date} value={d.date}>{d.date} ({d.weekday})</option>
                      ))}
                    </CustomSelect>
                  ) : (
                    <input type="date" className="form-control" value={completeData.executed_date} onChange={(e) => setCompleteData({ ...completeData, executed_date: e.target.value })} required />
                  )}
                </div>
                {availableDates.find(d => d.date === completeData.executed_date)?.periods?.length > 0 && (
                  <div className="form-group mb-3">
                    <label>Executed Period / Hour</label>
                    <CustomSelect className="form-control" value={completeData.executed_period} onChange={(e) => setCompleteData({ ...completeData, executed_period: e.target.value })} required>
                      <option value="">Select a period...</option>
                      {availableDates.find(d => d.date === completeData.executed_date).periods.map(p => (
                        <option key={`${p.start}-${p.end}`} value={`${p.start}-${p.end}`}>
                          {p.start === p.end ? `Hour ${p.start}` : `Hour ${p.start} to ${p.end}`}
                        </option>
                      ))}
                    </CustomSelect>
                  </div>
                )}
                <div className="form-group mb-3">
                  <label>Actual Topics Covered</label>
                  <textarea className="form-control" rows="2" value={completeData.actual_topics} onChange={(e) => setCompleteData({ ...completeData, actual_topics: e.target.value })} placeholder="Did you cover everything planned?" disabled={isEditingComplete} />
                </div>
                <div className="form-group mb-3">
                  <label>Faculty Remarks <span className="text-error">*</span></label>
                  <textarea className="form-control" rows="2" value={completeData.remarks} onChange={(e) => setCompleteData({ ...completeData, remarks: e.target.value })} placeholder="Any observations, pending items, or student feedback..." required disabled={isEditingComplete} />
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
              <button className="btn-icon" onClick={() => setShowRescheduleModal(false)}><XCircle size={20} /></button>
            </div>
            <form onSubmit={handleRescheduleSubmit}>
              <div className="modal-body">
                <div className="form-group mb-3">
                  <label>New Date</label>
                  {availableDates.length > 0 ? (
                    <CustomSelect className="form-control" value={rescheduleData.new_date} onChange={(e) => {
                      const newDate = e.target.value;
                      const dateObj = availableDates.find(d => d.date === newDate);
                      setRescheduleData({
                        ...rescheduleData, new_date: newDate,
                        new_period_start: (dateObj && dateObj.periods.length > 0) ? dateObj.periods[0].start : '',
                        new_period_end: (dateObj && dateObj.periods.length > 0) ? dateObj.periods[0].end : ''
                      });
                    }} required>
                      <option value="">Select a valid teaching date...</option>
                      {availableDates.map(d => (
                        <option key={d.date} value={d.date}>{d.date} ({d.weekday})</option>
                      ))}
                    </CustomSelect>
                  ) : (
                    <input type="date" className="form-control" value={rescheduleData.new_date} onChange={(e) => setRescheduleData({ ...rescheduleData, new_date: e.target.value })} required />
                  )}
                </div>
                {availableDates.find(d => d.date === rescheduleData.new_date)?.periods?.length > 0 ? (
                  <div className="form-group mb-3">
                    <label>New Period / Hour</label>
                    <CustomSelect className="form-control" value={`${rescheduleData.new_period_start}-${rescheduleData.new_period_end}`} onChange={(e) => {
                      const [start, end] = e.target.value.split('-');
                      setRescheduleData({ ...rescheduleData, new_period_start: start, new_period_end: end });
                    }} required>
                      <option value="">Select a period...</option>
                      {availableDates.find(d => d.date === rescheduleData.new_date).periods.map(p => (
                        <option key={`${p.start}-${p.end}`} value={`${p.start}-${p.end}`}>
                          {p.start === p.end ? `Hour ${p.start}` : `Hour ${p.start} to ${p.end}`}
                        </option>
                      ))}
                    </CustomSelect>
                  </div>
                ) : (
                  <div className="flex gap-4 mb-3">
                    <div className="form-group flex-1">
                      <label>New Period Start</label>
                      <input type="number" className="form-control" min="1" max="8" value={rescheduleData.new_period_start} onChange={(e) => setRescheduleData({ ...rescheduleData, new_period_start: e.target.value })} required />
                    </div>
                    <div className="form-group flex-1">
                      <label>New Period End</label>
                      <input type="number" className="form-control" min="1" max="8" value={rescheduleData.new_period_end} onChange={(e) => setRescheduleData({ ...rescheduleData, new_period_end: e.target.value })} required />
                    </div>
                  </div>
                )}
                <div className="form-group mb-3">
                  <label>Remarks / Reason <span className="text-error">*</span></label>
                  <textarea className="form-control" rows="2" value={rescheduleData.remarks} onChange={(e) => setRescheduleData({ ...rescheduleData, remarks: e.target.value })} placeholder="Reason for rescheduling..." required />
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

      {/* HOD Remark Modal — HOD ONLY */}
      {showHodRemarkModal && isHod && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <h2>Add Supervisory Remark</h2>
              <button className="btn-icon" onClick={() => setShowHodRemarkModal(false)}><XCircle size={20} /></button>
            </div>
            <form onSubmit={handleHodRemarkSubmit}>
              <div className="modal-body">
                <p className="mb-3 text-sm text-secondary">
                  Add feedback or notes on this session's progress. This will be visible to the assigned faculty without altering the session's status.
                </p>
                <div className="form-group mb-3">
                  <label>Your Remark <span className="text-error">*</span></label>
                  <textarea
                    className="form-control"
                    rows="4"
                    value={hodRemark}
                    onChange={(e) => setHodRemark(e.target.value)}
                    placeholder="Enter observations, recommendations, or feedback..."
                    required
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowHodRemarkModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={isSubmitting || !hodRemark.trim()}>
                  {isSubmitting ? 'Sending...' : <><Send size={14} /> Send Remark</>}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default CourseProgress;
