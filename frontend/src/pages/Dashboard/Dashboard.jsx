import React, { useEffect, useState } from 'react';
import { FileText, Clock, CheckCircle, Calendar, Plus, Users, BookOpen, BarChart3, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { lessonPlanService } from '../../services/lessonPlanService';
import { courseService } from '../../services/courseService';
import { facultyService } from '../../services/facultyService';
import { schedulerService } from '../../services/schedulerService';
import { useAuth } from '../../context/AuthContext';
import './Dashboard.css';

const Dashboard = () => {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [stats, setStats] = useState({
    active: 0,
    pending: 0,
    completed: 0,
    upcoming: 'View',
    totalFaculty: 0,
    totalCourses: 0,
    totalPlans: 0
  });
  const [recentPlans, setRecentPlans] = useState([]);
  const [loading, setLoading] = useState(true);

  const [isAllocated, setIsAllocated] = useState(false);
  
  const [assignedCourses, setAssignedCourses] = useState([]);
  const [showUpcomingModal, setShowUpcomingModal] = useState(false);
  const [upcomingClasses, setUpcomingClasses] = useState([]);
  const [loadingUpcoming, setLoadingUpcoming] = useState(false);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setLoading(true);
        // Fetch all required data
        const [plans, courses, faculties] = await Promise.all([
          lessonPlanService.getAll().catch(e => { console.error(e); return []; }),
          courseService.getAll().catch(e => { console.error("Course fetch error:", e); return []; }),
          facultyService.getAll().catch(e => { console.error(e); return []; })
        ]);

        const safePlans = Array.isArray(plans) ? plans : [];
        const safeCourses = Array.isArray(courses) ? courses : [];
        const safeFaculties = Array.isArray(faculties) ? faculties : [];

        const currentUserId = user?.id || user?._id;
        const currentUserFaculty = safeFaculties.find(f =>
          (f.user_id && currentUserId && String(f.user_id) === String(currentUserId)) ||
          (f.email && user?.email && f.email.toLowerCase() === user.email.toLowerCase())
        );

        const uAllocatedCourses = safeCourses.filter(course => {
          const courseFacultyIds = Array.isArray(course?.faculty_ids) && course.faculty_ids.length > 0
            ? course.faculty_ids
            : (course?.faculty_id ? [course.faculty_id] : (course?.assigned_faculty_id ? [course.assigned_faculty_id] : []));

          return courseFacultyIds.some(fid =>
            String(fid) === String(currentUserId) ||
            (currentUserFaculty && (
              String(fid) === String(currentUserFaculty._id) ||
              String(fid) === String(currentUserFaculty.id) ||
              String(fid) === String(currentUserFaculty.faculty_id)
            ))
          );
        });
        
        setAssignedCourses(user?.role === 'admin' ? safeCourses : uAllocatedCourses);
        const userAllocated = uAllocatedCourses.length > 0;

        setIsAllocated(userAllocated);

        // Merge course details into plans
        const enrichedPlans = safePlans.map(plan => {
          const course = safeCourses.find(c => c._id === plan.course_id || c.id === plan.course_id);
          return {
            ...plan,
            course_name: course ? course.course_name : 'Unknown Course',
            course_code: course ? course.course_code : 'N/A',
            semester: course ? course.semester : 'N/A'
          };
        });

        let relevantPlans = enrichedPlans;

        if (user?.role === 'faculty') {
          relevantPlans = enrichedPlans.filter(plan => {
            const course = safeCourses.find(c => c._id === plan.course_id || c.id === plan.course_id);
            const courseFacultyIds = course ? (Array.isArray(course?.faculty_ids) && course.faculty_ids.length > 0
              ? course.faculty_ids
              : (course?.faculty_id ? [course.faculty_id] : (course?.assigned_faculty_id ? [course.assigned_faculty_id] : []))) : [];

            return courseFacultyIds.some(fid =>
              String(fid) === String(currentUserId) ||
              (currentUserFaculty && (
                String(fid) === String(currentUserFaculty._id) ||
                String(fid) === String(currentUserFaculty.id) ||
                String(fid) === String(currentUserFaculty.faculty_id)
              ))
            ) || (plan.faculty_id && (
              String(plan.faculty_id) === String(currentUserId) ||
              (currentUserFaculty && (String(plan.faculty_id) === String(currentUserFaculty._id) || String(plan.faculty_id) === String(currentUserFaculty.id) || String(plan.faculty_id) === String(currentUserFaculty.faculty_id)))
            ));
          });
        }

        // Simple metric derivation from real data based on status
        const active = relevantPlans.filter(p => !['Approved', 'Pending Approval'].includes(p.status)).length;
        const pending = relevantPlans.filter(p => p.status === 'Pending Approval').length;
        const completed = relevantPlans.filter(p => p.status === 'Approved').length;

        setStats({
          active,
          pending,
          completed,
          upcoming: '...',
          totalFaculty: safeFaculties.length,
          totalCourses: safeCourses.length,
          totalPlans: safePlans.length
        });

        // Show 5 most recent
        setRecentPlans(relevantPlans.reverse().slice(0, 5));

        // Fetch upcoming count lazily so it doesn't block main render
        const fetchUpcomingCount = async (courses) => {
          try {
            const dateObj = new Date();
            const localDate = new Date(dateObj.getTime() - (dateObj.getTimezoneOffset() * 60000)).toISOString().split('T')[0];
            let count = 0;
            for (const course of courses) {
              try {
                const progressData = await schedulerService.getProgress(course._id || course.id);
                if (progressData && progressData.sessions) {
                  count += progressData.sessions.filter(s => s.date === localDate && s.status !== 'completed').length;
                }
              } catch (err) {}
            }
            setStats(prev => ({ ...prev, upcoming: count }));
          } catch (err) {
             setStats(prev => ({ ...prev, upcoming: 'Error' }));
          }
        };
        
        fetchUpcomingCount(user?.role === 'admin' ? safeCourses : uAllocatedCourses);
      } catch (error) {
        console.error("Failed to fetch dashboard data:", error);
      } finally {
        setLoading(false);
      }
    };

    if (user) {
      fetchDashboardData();
    }
  }, [user]);

  const handleViewUpcoming = async () => {
    setShowUpcomingModal(true);
    setLoadingUpcoming(true);
    try {
      // Local date in YYYY-MM-DD
      const dateObj = new Date();
      const localDate = new Date(dateObj.getTime() - (dateObj.getTimezoneOffset() * 60000)).toISOString().split('T')[0];
      let allUpcoming = [];
      
      for (const course of assignedCourses) {
        try {
          const progressData = await schedulerService.getProgress(course._id || course.id);
          if (progressData && progressData.sessions) {
            const todaySessions = progressData.sessions.filter(s => s.date === localDate && s.status !== 'completed');
            for (const session of todaySessions) {
               allUpcoming.push({
                 ...session,
                 course_name: course.course_name,
                 course_code: course.course_code
               });
            }
          }
        } catch(err) {
           console.error("Failed to fetch schedule for course", course.course_name);
        }
      }
      
      allUpcoming.sort((a, b) => (a.period_start || a.period || 0) - (b.period_start || b.period || 0));
      setUpcomingClasses(allUpcoming);
    } catch (error) {
      console.error("Failed to fetch upcoming classes", error);
    } finally {
      setLoadingUpcoming(false);
    }
  };

  const StatCard = ({ title, value, icon, color, onClick }) => (
    <div
      className={`stat-card ${onClick ? 'clickable-card' : ''}`}
      onClick={onClick}
    >
      <div className="stat-content">
        <h3 className="stat-title">{title}</h3>
        <p className="stat-value">{value}</p>
      </div>
      <div className={`stat-icon-wrapper bg-${color}-light text-${color}`}>
        {icon}
      </div>
    </div>
  );

  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 18) return 'Good afternoon';
    return 'Good evening';
  };

  return (
    <div className="dashboard">
      <div className="page-header">
        <div>
          <h1 className="page-title">{getGreeting()}, {user?.name || 'User'}!</h1>
          <p className="page-subtitle">Here is your lesson planning overview.</p>
        </div>
        {isAllocated && (
          <button
            className="btn btn-primary"
            onClick={() => navigate('/lesson-plans/create')}
          >
            <Plus size={18} />
            Create Plan
          </button>
        )}
      </div>

      <div className="stats-grid">
        {user?.role === 'admin' ? (
          <>
            <StatCard title="Total Faculty" value={loading ? "..." : stats.totalFaculty} icon={<Users size={24} />} color="blue" onClick={() => navigate('/faculty')} />
            <StatCard title="Total Courses" value={loading ? "..." : stats.totalCourses} icon={<BookOpen size={24} />} color="purple" onClick={() => navigate('/courses')} />
            <StatCard title="Total Lesson Plans" value={loading ? "..." : stats.totalPlans} icon={<FileText size={24} />} color="amber" onClick={() => navigate('/lesson-plans')} />
            <StatCard title="System Reports" value={loading ? "..." : "View"} icon={<BarChart3 size={24} />} color="green" onClick={() => navigate('/reports')} />
          </>
        ) : (
          <>
            <StatCard title="Active Plans" value={loading ? "..." : stats.active} icon={<FileText size={24} />} color="blue" onClick={() => navigate('/lesson-plans')} />
            <StatCard title="Pending Review" value={loading ? "..." : stats.pending} icon={<Clock size={24} />} color="amber" onClick={() => navigate('/lesson-plans')} />
            <StatCard title="Approved Plans" value={loading ? "..." : stats.completed} icon={<CheckCircle size={24} />} color="green" onClick={() => navigate('/lesson-plans')} />
            <StatCard title="Upcoming Classes" value={loading ? "..." : stats.upcoming} icon={<Calendar size={24} />} color="navy" onClick={handleViewUpcoming} />
          </>
        )}
      </div>

      <div className="recent-section">
        <div className="section-header">
          <h2 className="section-title">Recent Lesson Plans</h2>
          <button className="btn btn-secondary btn-sm" onClick={() => navigate('/lesson-plans')}>
            View All
          </button>
        </div>

        <div className="table-responsive table-scroll-wrapper">
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Subject</th>
                  <th>Course Code</th>
                  <th>Semester</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan="5" className="text-center py-4">Loading data...</td>
                  </tr>
                ) : recentPlans.length === 0 ? (
                  <tr>
                    <td colSpan="5" className="text-center py-4 text-secondary">
                      No lesson plans found. Create one to get started.
                    </td>
                  </tr>
                ) : (
                  recentPlans.map((plan) => (
                    <tr key={plan._id || plan.id}>
                      <td data-label="Subject">{plan.course_name || 'N/A'}</td>
                      <td data-label="Course Code">{plan.course_code || 'N/A'}</td>
                      <td data-label="Semester">Semester {plan.semester || 'N/A'}</td>
                      <td data-label="Status">
                        <span className={`status-badge status-${plan.status?.toLowerCase().replace(' ', '-') || 'draft'}`}>
                          {plan.status || 'Draft'}
                        </span>
                      </td>
                      <td data-label="Action">
                        <button
                          className="btn btn-link btn-sm"
                          onClick={() => navigate(`/lesson-plans/${plan._id || plan.id}`)}
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {showUpcomingModal && (
        <div className="modal-overlay" onClick={() => setShowUpcomingModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '650px', width: '90%' }}>
            <div className="modal-header">
              <h2>Upcoming Classes Today</h2>
              <button className="close-btn" onClick={() => setShowUpcomingModal(false)}>
                <X size={20} />
              </button>
            </div>
            <div className="modal-body">
              {loadingUpcoming ? (
                <div className="text-center py-4">Fetching schedules from all assigned courses...</div>
              ) : upcomingClasses.length === 0 ? (
                <div className="text-center py-4 text-secondary">
                  No classes scheduled for today across your assigned courses.
                </div>
              ) : (
                <div className="table-responsive">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Course</th>
                        <th>Period / Time</th>
                        <th>Topic</th>
                      </tr>
                    </thead>
                    <tbody>
                      {upcomingClasses.map((cls, idx) => (
                        <tr key={idx}>
                          <td>
                            <div style={{ fontWeight: 500 }}>{cls.course_name}</div>
                            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{cls.course_code}</div>
                          </td>
                          <td>
                            <span className="badge-info" style={{ padding: '2px 6px', borderRadius: '4px', fontSize: '12px' }}>
                              Period {cls.period_start ? (cls.period_start === cls.period_end ? cls.period_start : `${cls.period_start}-${cls.period_end}`) : (cls.period || '-')}
                            </span>
                            {cls.start_time && (
                              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                                {cls.start_time} - {cls.end_time}
                              </div>
                            )}
                          </td>
                          <td>{cls.topic || 'N/A'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            <div className="modal-footer" style={{ marginTop: '16px', display: 'flex', justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setShowUpcomingModal(false)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
