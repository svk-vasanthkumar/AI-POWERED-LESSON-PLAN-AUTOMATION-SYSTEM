import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Edit2, Download, Trash2, Search, FileText } from 'lucide-react';
import { lessonPlanService } from '../../services/lessonPlanService';
import { courseService } from '../../services/courseService';
import './LessonPlansList.css';

const LessonPlansList = () => {
  const navigate = useNavigate();
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  const fetchPlans = async () => {
    try {
      setLoading(true);
      const [data, courses] = await Promise.all([
        lessonPlanService.getAll(),
        courseService.getAll().catch(e => { console.error(e); return []; })
      ]);
      
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
  }, []);

  const handleDelete = async (id) => {
    if (window.confirm("Are you sure you want to delete this lesson plan?")) {
      try {
        await lessonPlanService.delete(id);
        fetchPlans();
      } catch (error) {
        alert("Failed to delete lesson plan: " + (error.uiMessage || error.message || "Unknown error"));
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
        <button className="btn btn-primary" onClick={() => navigate('/lesson-plans/create')}>
          <Plus size={18} /> New Lesson Plan
        </button>
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

      <div className="table-container mt-4">
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
                <tr key={plan._id}>
                  <td className="font-medium">{plan.course_name || 'N/A'}</td>
                  <td>{plan.course_code || 'N/A'}</td>
                  <td>Sem {plan.semester || '-'}</td>
                  <td>
                    <span className={`status-badge status-${plan.status?.toLowerCase().replace(' ', '-') || 'draft'}`}>
                      {plan.status || 'Draft'}
                    </span>
                  </td>
                  <td className="text-secondary">{new Date().toLocaleDateString()}</td>
                  <td>
                    <div className="action-buttons">
                      <button 
                        className="btn-icon text-accent" 
                        title="Edit Plan"
                        onClick={() => navigate(`/lesson-plans/${plan._id}`)}
                      >
                        <Edit2 size={16} />
                      </button>
                      <button 
                        className="btn-icon text-error" 
                        title="Delete Plan"
                        onClick={() => handleDelete(plan._id || plan.lesson_plan_id)}
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
  );
};

export default LessonPlansList;
