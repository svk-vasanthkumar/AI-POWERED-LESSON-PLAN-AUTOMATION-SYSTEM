import React, { useEffect, useState } from 'react';
import { FileText, Clock, CheckCircle, Calendar, Plus, Users, BookOpen, BarChart3 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { lessonPlanService } from '../../services/lessonPlanService';
import { courseService } from '../../services/courseService';
import { facultyService } from '../../services/facultyService';
import { useAuth } from '../../context/AuthContext';
import './Dashboard.css';

const Dashboard = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  
  const [stats, setStats] = useState({
    active: 0,
    pending: 0,
    completed: 0,
    upcoming: 0,
    totalFaculty: 0,
    totalCourses: 0,
    totalPlans: 0
  });
  const [recentPlans, setRecentPlans] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setLoading(true);
        // Fetch all required data
        const [plans, courses, faculties] = await Promise.all([
          lessonPlanService.getAll().catch(e => { console.error(e); return []; }),
          courseService.getAll().catch(e => { console.error("Course fetch error:", e); return []; }),
          user?.role === 'admin' ? facultyService.getAll().catch(e => { console.error(e); return []; }) : Promise.resolve([])
        ]);
        
        // Merge course details into plans
        const enrichedPlans = plans.map(plan => {
          const course = courses.find(c => c._id === plan.course_id || c.id === plan.course_id);
          return {
            ...plan,
            course_name: course ? course.course_name : 'Unknown Course',
            course_code: course ? course.course_code : 'N/A',
            semester: course ? course.semester : 'N/A'
          };
        });
        
        // Simple metric derivation from real data based on status
        const active = enrichedPlans.filter(p => p.status === 'Draft' || p.status === 'Processing').length;
        const pending = enrichedPlans.filter(p => p.status === 'Needs Review').length;
        const completed = enrichedPlans.filter(p => p.status === 'Approved').length;
        
        setStats({
          active,
          pending,
          completed,
          upcoming: completed * 2, // Example calculation
          totalFaculty: faculties.length,
          totalCourses: courses.length,
          totalPlans: plans.length
        });
        
        // Show 5 most recent
        setRecentPlans(enrichedPlans.slice(0, 5));
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

  return (
    <div className="dashboard">
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">Welcome back. Here is your lesson planning overview.</p>
        </div>
        <button 
          className="btn btn-primary" 
          onClick={() => navigate('/lesson-plans/create')}
        >
          <Plus size={18} />
          Create Plan
        </button>
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
            <StatCard title="Upcoming Classes" value={loading ? "..." : stats.upcoming} icon={<Calendar size={24} />} color="navy" onClick={() => navigate('/courses')} />
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
                    <td>{plan.course_name || 'N/A'}</td>
                    <td>{plan.course_code || 'N/A'}</td>
                    <td>Semester {plan.semester || 'N/A'}</td>
                    <td>
                      <span className={`status-badge status-${plan.status?.toLowerCase().replace(' ', '-') || 'draft'}`}>
                        {plan.status || 'Draft'}
                      </span>
                    </td>
                    <td>
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
  );
};

export default Dashboard;
