import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Edit2, Download, Trash2, Search, FileText } from 'lucide-react';
import { lessonPlanService } from '../../services/lessonPlanService';
import { courseService } from '../../services/courseService';
import { facultyService } from '../../services/facultyService';
import { useAuth } from '../../context/AuthContext';
import { useAlert } from '../../context/AlertContext';
import './LessonPlansList.css';

const LessonPlansList = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { showAlert, showConfirm } = useAlert();
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [isAllocated, setIsAllocated] = useState(false);

  const fetchPlans = async () => {
    try {
      setLoading(true);
      const [data, courses, faculties] = await Promise.all([
        lessonPlanService.getAll(),
        courseService.getAll().catch(e => { console.error(e); return []; }),
        facultyService.getAll().catch(e => { console.error(e); return []; })
      ]);
      
      const currentUserId = user?.id || user?._id;
      const currentUserFaculty = faculties.find(f => 
        (f.user_id && currentUserId && String(f.user_id) === String(currentUserId)) ||
        (f.email && user?.email && f.email.toLowerCase() === user.email.toLowerCase())
      );

      const userAllocated = courses.some(course => {
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

      setIsAllocated(userAllocated);

      const enrichedPlans = data.map(plan => {
        const course = courses.find(c => c._id === plan.course_id || c.id === plan.course_id);
        return {
          ...plan,
          course_name: course ? course.course_name : 'Unknown Course',
          course_code: course ? course.course_code : 'N/A',
          semester: course ? course.semester : 'N/A'
        };
      });
      
      setPlans(enrichedPlans);
    } catch (error) {
      console.error("Failed to fetch lesson plans", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPlans();
  }, [user]);

  const handleDelete = async (id) => {
    const confirmed = await showConfirm("Are you sure you want to delete this lesson plan?", "Delete Lesson Plan");
    if (confirmed) {
      try {
        await lessonPlanService.delete(id);
        showAlert("Lesson plan deleted successfully", "success");
        fetchPlans();
      } catch (error) {
        showAlert("Failed to delete lesson plan: " + (error.uiMessage || error.message || "Unknown error"), "error");
      }
    }
  };

  const filteredPlans = plans.filter(plan => 
    (plan.course_name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (plan.course_code || '').toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="plans-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Lesson Plans</h1>
          <p className="page-subtitle">Manage, edit, and export your generated lesson plans.</p>
        </div>
        {isAllocated && (
          <button className="btn btn-primary" onClick={() => navigate('/lesson-plans/create')}>
            <Plus size={18} /> New Lesson Plan
          </button>
        )}
      </div>

      <div className="plans-controls">
        <div className="search-box">
          <Search size={18} className="search-icon" />
          <input 
            type="text" 
            placeholder="Search by course name or code..." 
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      <div className="table-responsive plans-table-wrapper mt-4">
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Course Name</th>
                <th>Code</th>
                <th>Semester</th>
                <th>Status</th>
                <th>Last Updated</th>
                <th className="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="6" className="text-center py-4">Loading lesson plans...</td>
                </tr>
              ) : filteredPlans.length === 0 ? (
                <tr>
                  <td colSpan="6" className="text-center py-5">
                    <div className="empty-state-inline">
                      <FileText size={32} className="text-secondary mb-2" />
                      <p>No lesson plans found.</p>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredPlans.map(plan => (
                  <tr key={plan._id || plan.id}>
                    <td data-label="Course Name" className="font-medium">{plan.course_name || 'N/A'}</td>
                    <td data-label="Code">{plan.course_code || 'N/A'}</td>
                    <td data-label="Semester">Sem {plan.semester || '-'}</td>
                    <td data-label="Status">
                      <span className={`status-badge status-${plan.status?.toLowerCase().replace(' ', '-') || 'draft'}`}>
                        {plan.status || 'Draft'}
                      </span>
                    </td>
                    <td data-label="Last Updated" className="text-secondary">{plan.updated_at ? new Date(plan.updated_at).toLocaleDateString() : (plan.created_at ? new Date(plan.created_at).toLocaleDateString() : '-')}</td>
                    <td data-label="Actions">
                      <div className="action-buttons">
                        <button 
                          className="btn-icon text-accent" 
                          title="Edit Plan"
                          onClick={() => navigate(`/lesson-plans/${plan._id || plan.id}`)}
                        >
                          <Edit2 size={16} />
                        </button>
                        <button 
                          className="btn-icon text-error" 
                          title="Delete Plan"
                          onClick={() => handleDelete(plan._id || plan.id)}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
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

export default LessonPlansList;

