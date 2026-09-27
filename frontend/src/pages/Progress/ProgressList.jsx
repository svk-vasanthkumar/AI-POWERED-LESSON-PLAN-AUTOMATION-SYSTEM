import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { TrendingUp, BookOpen, AlertCircle, ChevronRight } from 'lucide-react';
import { courseService } from '../../services/courseService';
import { reportsService } from '../../services/reportsService';
import { useAuth } from '../../context/AuthContext';
import './ProgressList.css';

const ProgressList = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchProgress = async () => {
      try {
        setLoading(true);
        // We'll fetch the user's courses and their setup progress
        let coursesData = [];
        if (user?.role === 'admin' || user?.role === 'hod') {
          coursesData = await courseService.getAll();
        } else {
          // Fallback if needed, but courseService.getAll() is filtered by RBAC on backend
          coursesData = await courseService.getAll();
        }
        
        const progressData = await reportsService.getCourseProgress().catch(() => []);
        
        // Merge progress data into courses
        const merged = coursesData.map(c => {
          const p = progressData.find(pd => pd.course_code === c.course_code);
          return {
            ...c,
            progress_percentage: p?.progress_percentage || 0,
            status: p?.status || 'Not Started'
          };
        });
        
        setCourses(merged);
      } catch (err) {
        console.error("Failed to fetch course progress", err);
        setError('Failed to load course progress data.');
      } finally {
        setLoading(false);
      }
    };

    fetchProgress();
  }, [user]);

  return (
    <div className="progress-list-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Progress Monitoring</h1>
          <p className="page-subtitle">Track and update the execution of your lesson plans.</p>
        </div>
      </div>

      {error && (
        <div className="alert alert-error mb-4">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      <div className="progress-courses-grid">
        {loading ? (
          <div className="w-100 text-center py-4 text-secondary">Loading courses...</div>
        ) : courses.length === 0 ? (
          <div className="empty-state w-100">
            <TrendingUp size={48} className="empty-icon" />
            <p>No courses available for progress tracking.</p>
          </div>
        ) : (
          courses.map((course) => (
            <div 
              key={course._id || course.id} 
              className={`progress-course-card ${course.status !== 'Ready' ? 'opacity-75' : ''}`}
              onClick={() => navigate(`/progress/${course._id || course.id}`)}
            >
              <div className="progress-course-header">
                <div className="course-icon bg-indigo-light text-indigo">
                  <BookOpen size={24} />
                </div>
                <div className="course-status-badge">
                  <span className={`badge ${course.status === 'Ready' ? 'badge-success' : 'badge-warning'}`}>
                    {course.status || 'Active'}
                  </span>
                </div>
              </div>
              <h3 className="course-title">{course.course_name}</h3>
              <p className="course-code">{course.course_code}</p>
              
              <div className="progress-section mt-4">
                <div className="progress-header">
                  <span className="progress-label">Setup Completion</span>
                  <span className="progress-value">{course.progress_percentage}%</span>
                </div>
                <div className="progress-bar-container">
                  <div 
                    className={`progress-bar ${
                      course.progress_percentage < 50 ? 'bg-danger' : 
                      course.progress_percentage < 100 ? 'bg-warning' : 'bg-success'
                    }`}
                    style={{ width: `${course.progress_percentage}%` }}
                  ></div>
                </div>
              </div>

              <div className="card-footer mt-4" style={{ borderTop: '1px solid var(--border-color)', paddingTop: '14px' }}>
                <button
                  className={`btn btn-sm w-100 ${course.status !== 'Ready' ? 'btn-secondary' : 'btn-outline-primary'}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(`/progress/${course._id || course.id}`);
                  }}
                >
                  {course.status !== 'Ready' ? 'View Setup Status' : (user?.role === 'faculty' ? 'Update Progress' : 'Track Execution')} <ChevronRight size={15} />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default ProgressList;
