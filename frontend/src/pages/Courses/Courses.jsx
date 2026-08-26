import React, { useState, useEffect } from 'react';
import { BookOpen, Plus, X, Users, CheckCircle, AlertCircle } from 'lucide-react';
import { courseService } from '../../services/courseService';
import { facultyService } from '../../services/facultyService';
import { useAuth } from '../../context/AuthContext';
import './Courses.css';

const Courses = () => {
  const { user } = useAuth();
  const [courses, setCourses] = useState([]);
  const [faculty, setFaculty] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  
  // Form state
  const [formData, setFormData] = useState({
    course_code: '',
    course_name: '',
    department: user?.department || '',
    semester: 1,
    credits: 3,
    faculty_id: user?.id || user?._id || ''
  });

  const fetchData = async () => {
    try {
      setLoading(true);
      const [coursesData, facultyData] = await Promise.all([
        courseService.getAll().catch(() => []),
        facultyService.getAll().catch(() => [])
      ]);
      setCourses(coursesData);
      setFaculty(facultyData);
    } catch (err) {
      console.error("Failed to fetch courses data", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleChange = (e) => {
    const value = e.target.type === 'number' ? parseInt(e.target.value) : e.target.value;
    setFormData({
      ...formData,
      [e.target.name]: value
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    
    try {
      await courseService.create(formData);
      await fetchData(); // Refresh list
      setShowModal(false);
      // Reset form
      setFormData({
        course_code: '',
        course_name: '',
        department: user?.department || '',
        semester: 1,
        credits: 3,
        faculty_id: user?.id || user?._id || ''
      });
    } catch (err) {
      setError(err.uiMessage || 'Failed to create course. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="courses-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Courses</h1>
          <p className="page-subtitle">Manage academic courses and assign faculty members.</p>
        </div>
        {(user?.role === 'admin' || user?.role === 'hod') && (
          <button className="btn btn-primary" onClick={() => setShowModal(true)}>
            <Plus size={18} />
            Add Course
          </button>
        )}
      </div>

      <div className="courses-grid">
        {loading ? (
          <div className="w-100 text-center py-4 text-secondary" style={{ gridColumn: '1 / -1' }}>Loading courses...</div>
        ) : courses.length === 0 ? (
          <div className="empty-state w-100" style={{ gridColumn: '1 / -1' }}>
            <BookOpen size={48} className="empty-icon" />
            <p>
              {user?.role === 'admin' || user?.role === 'hod' 
                ? 'No courses found. Add a course to get started.' 
                : 'You have not been assigned to any courses yet.'}
            </p>
          </div>
        ) : (
          courses.map(course => (
            <div key={course._id || course.id} className="course-card">
              <div className="course-card-header">
                <div className="course-icon bg-blue-light text-blue">
                  <BookOpen size={24} />
                </div>
                <div className="course-badges">
                  <span className="badge badge-outline">Sem {course.semester}</span>
                </div>
              </div>
              <h3 className="course-title">{course.course_name}</h3>
              <p className="course-code">{course.course_code}</p>
              
              <div className="course-details">
                <div className="detail-item">
                  <span className="detail-label">Department</span>
                  <span className="detail-value">{course.department}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Credits</span>
                  <span className="detail-value">{course.credits}</span>
                </div>
              </div>
              
              <div className="course-faculty">
                <Users size={16} />
                <span>
                  {faculty.find(f => (f._id || f.id) === course.faculty_id)?.name || 
                   (course.faculty_id === (user?._id || user?.id) ? 'You (Current User)' : 'Assigned Faculty')}
                </span>
              </div>
            </div>
          ))
        )}
      </div>

      {showModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <h2>Add New Course</h2>
              <button className="btn-icon" onClick={() => setShowModal(false)}><X size={20} /></button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                {error && (
                  <div className="alert alert-error mb-4">
                    <AlertCircle size={16} />
                    <span>{error}</span>
                  </div>
                )}
                
                <div className="form-row" style={{ display: 'flex', gap: '1rem' }}>
                  <div className="form-group mb-4" style={{ flex: 1 }}>
                    <label className="form-label">Course Code</label>
                    <input 
                      type="text" 
                      className="form-control" 
                      name="course_code"
                      value={formData.course_code}
                      onChange={handleChange}
                      placeholder="e.g. CS101"
                      required
                    />
                  </div>
                  <div className="form-group mb-4" style={{ flex: 1 }}>
                    <label className="form-label">Credits</label>
                    <input 
                      type="number" 
                      className="form-control" 
                      name="credits"
                      value={formData.credits}
                      onChange={handleChange}
                      min="1"
                      max="10"
                      required
                    />
                  </div>
                </div>

                <div className="form-group mb-4">
                  <label className="form-label">Course Name</label>
                  <input 
                    type="text" 
                    className="form-control" 
                    name="course_name"
                    value={formData.course_name}
                    onChange={handleChange}
                    placeholder="e.g. Introduction to Computer Science"
                    required
                  />
                </div>

                <div className="form-row" style={{ display: 'flex', gap: '1rem' }}>
                  <div className="form-group mb-4" style={{ flex: 1 }}>
                    <label className="form-label">Department</label>
                    <select 
                      className="form-control" 
                      name="department"
                      value={formData.department}
                      onChange={handleChange}
                      required
                    >
                      <option value="" disabled>Select Department</option>
                      <option value="CSE">Computer Science and Engineering</option>
                      <option value="IT">Information Technology</option>
                      <option value="ECE">Electronics and Communication Engineering</option>
                      <option value="EEE">Electrical and Electronics Engineering</option>
                      <option value="MECH">Mechanical Engineering</option>
                      <option value="CIVIL">Civil Engineering</option>
                      <option value="AIDS">Artificial Intelligence and Data Science</option>
                      <option value="S&H">Science and Humanities</option>
                    </select>
                  </div>
                  <div className="form-group mb-4" style={{ flex: 1 }}>
                    <label className="form-label">Semester</label>
                    <input 
                      type="number" 
                      className="form-control" 
                      name="semester"
                      value={formData.semester}
                      onChange={handleChange}
                      min="1"
                      max="8"
                      required
                    />
                  </div>
                </div>

                <div className="form-group mb-4">
                  <label className="form-label">Assign Faculty</label>
                  <select 
                    className="form-control" 
                    name="faculty_id"
                    value={formData.faculty_id}
                    onChange={handleChange}
                    required
                  >
                    <option value="" disabled>Select a Faculty Member</option>
                    {faculty.map(f => (
                      <option key={f._id || f.id} value={f._id || f.id}>
                        {f.name} ({f.department})
                      </option>
                    ))}
                    {!faculty.find(f => (f._id || f.id) === (user?._id || user?.id)) && (
                      <option value={user?._id || user?.id}>You ({user?.name})</option>
                    )}
                  </select>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? 'Saving...' : 'Create Course'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Courses;
