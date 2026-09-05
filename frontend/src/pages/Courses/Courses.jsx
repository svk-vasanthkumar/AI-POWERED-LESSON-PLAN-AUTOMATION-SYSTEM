import React, { useState, useEffect } from 'react';
import { BookOpen, Plus, X, Users, CheckCircle, AlertCircle, Copy, Edit2, Trash2 } from 'lucide-react';
import { courseService } from '../../services/courseService';
import { facultyService } from '../../services/facultyService';
import { useAuth } from '../../context/AuthContext';
import './Courses.css';

const Courses = () => {
  const { user } = useAuth();
  const [courses, setCourses] = useState([]);
  const [faculty, setFaculty] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSemester, setSelectedSemester] = useState('All');
  const [selectedAcademicYear, setSelectedAcademicYear] = useState('All');
  const [selectedFaculty, setSelectedFaculty] = useState('All');
  
  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [courseToEditId, setCourseToEditId] = useState(null);
  const [showCloneModal, setShowCloneModal] = useState(false);
  const [courseToClone, setCourseToClone] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  
  // Clone Form state
  const [cloneData, setCloneData] = useState({
    new_faculty_id: '',
    new_academic_year: '2027-2028',
  });
  
  // Form state
  const [formData, setFormData] = useState({
    course_code: '',
    course_name: '',
    department: user?.department || '',
    semester: 1,
    credits: 3,
    academic_year: '2026-2027',
    faculty_id: user?.id || user?._id || '',
    short_form: ''
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

  const openCreateModal = () => {
    setIsEditing(false);
    setCourseToEditId(null);
    setFormData({
      course_code: '',
      course_name: '',
      department: user?.department || '',
      semester: 1,
      credits: 3,
      academic_year: '2026-2027',
      faculty_id: user?.id || user?._id || '',
      short_form: ''
    });
    setError('');
    setShowModal(true);
  };

  const openEditModal = (course) => {
    setIsEditing(true);
    setCourseToEditId(course._id || course.id);
    setFormData({
      course_code: course.course_code,
      course_name: course.course_name,
      department: course.department,
      semester: course.semester,
      credits: course.credits,
      academic_year: course.academic_year || '2026-2027',
      faculty_id: course.faculty_id,
      short_form: course.short_form || ''
    });
    setError('');
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    
    try {
      if (isEditing) {
        const updateData = { ...formData };
        delete updateData.course_code; // Immutable after creation
        await courseService.update(courseToEditId, updateData);
      } else {
        await courseService.create(formData);
      }
      
      await fetchData(); // Refresh list
      setShowModal(false);
    } catch (err) {
      setError(err.response?.data?.detail || `Failed to ${isEditing ? 'update' : 'add'} course`);
    } finally {
      setSaving(false);
    }
  };

  const handleCloneSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    if (!cloneData.new_faculty_id) {
      setError('Please select a faculty member');
      return;
    }
    
    setSaving(true);
    try {
      await courseService.clone(courseToClone._id || courseToClone.id, cloneData);
      setShowCloneModal(false);
      setCourseToClone(null);
      
      // Refresh list
      const updatedCourses = await courseService.getAll();
      setCourses(updatedCourses);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to clone course');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteCourse = async (courseId) => {
    if (!window.confirm("Are you sure you want to delete this course? This action cannot be undone.")) return;
    
    setLoading(true);
    try {
      await courseService.delete(courseId);
      await fetchData(); // Refresh list after deletion
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete course');
    } finally {
      setLoading(false);
    }
  };

  const uniqueSemesters = ['All', ...new Set(courses.map(c => c.semester))].sort((a, b) => {
    if (a === 'All') return -1;
    if (b === 'All') return 1;
    return a - b;
  });

  const uniqueAcademicYears = ['All', ...new Set(courses.map(c => c.academic_year).filter(Boolean))].sort((a, b) => {
    if (a === 'All') return -1;
    if (b === 'All') return 1;
    return a.localeCompare(b);
  });
  
  const uniqueFacultyIds = ['All', ...new Set(courses.map(c => c.faculty_id))];

  const filteredCourses = courses.filter(c => {
    const matchSemester = selectedSemester === 'All' || c.semester.toString() === selectedSemester.toString();
    const matchYear = selectedAcademicYear === 'All' || c.academic_year === selectedAcademicYear;
    const matchFaculty = selectedFaculty === 'All' || c.faculty_id === selectedFaculty;
    return matchSemester && matchYear && matchFaculty;
  });

  return (
    <div className="courses-page">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 className="page-title">Courses</h1>
          <p className="page-subtitle">Manage academic courses and assign faculty members.</p>
        </div>
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
          <select 
            className="form-control" 
            style={{ width: '160px' }}
            value={selectedAcademicYear}
            onChange={(e) => setSelectedAcademicYear(e.target.value)}
          >
            {uniqueAcademicYears.map(year => (
              <option key={year} value={year}>
                {year === 'All' ? 'All Years' : year}
              </option>
            ))}
          </select>
          <select 
            className="form-control" 
            style={{ width: '160px' }}
            value={selectedSemester}
            onChange={(e) => setSelectedSemester(e.target.value)}
          >
            {uniqueSemesters.map(sem => (
              <option key={sem} value={sem}>
                {sem === 'All' ? 'All Semesters' : `Semester ${sem}`}
              </option>
            ))}
          </select>
          <select 
            className="form-control" 
            style={{ width: '180px' }}
            value={selectedFaculty}
            onChange={(e) => setSelectedFaculty(e.target.value)}
          >
            {uniqueFacultyIds.map(fid => {
              if (fid === 'All') return <option key={fid} value={fid}>All Faculty</option>;
              const f = faculty.find(fac => (fac._id || fac.id) === fid);
              return (
                <option key={fid} value={fid}>
                  {f ? f.name : 'Unknown Faculty'}
                </option>
              );
            })}
          </select>
          {(user?.role === 'admin' || user?.role === 'hod') && (
            <button className="btn btn-primary" onClick={openCreateModal}>
              <Plus size={18} />
              Add Course
            </button>
          )}
        </div>
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
        ) : filteredCourses.length === 0 ? (
          <div className="empty-state w-100" style={{ gridColumn: '1 / -1' }}>
            <BookOpen size={48} className="empty-icon" />
            <p>No courses found for the selected filter.</p>
          </div>
        ) : (
          filteredCourses.map(course => (
            <div key={course._id || course.id} className="course-card">
              <div className="course-card-header">
                <div className="course-icon bg-blue-light text-blue">
                  <BookOpen size={24} />
                </div>
                <div className="course-badges" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <span className="badge badge-outline">Sem {course.semester}</span>
                  {(user?.role === 'admin' || user?.role === 'hod') && (
                    <>
                      <button 
                        className="btn-icon text-accent" 
                        style={{ padding: '4px' }}
                        title="Edit Course"
                        onClick={() => openEditModal(course)}
                      >
                        <Edit2 size={16} />
                      </button>
                      <button 
                        className="btn-icon" 
                        style={{ padding: '4px' }}
                        title="Reuse / Clone Course"
                        onClick={() => {
                          setCourseToClone(course);
                          setCloneData({
                            new_faculty_id: course.faculty_id,
                            new_academic_year: '2027-2028'
                          });
                          setShowCloneModal(true);
                        }}
                      >
                        <Copy size={16} />
                      </button>
                      <button 
                        className="btn-icon text-error" 
                        style={{ padding: '4px', color: 'var(--error)' }}
                        title="Delete Course"
                        onClick={() => handleDeleteCourse(course._id || course.id)}
                      >
                        <Trash2 size={16} />
                      </button>
                    </>
                  )}
                </div>
              </div>
              <h3 className="course-title">{course.course_name}</h3>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '1rem' }}>
                <p className="course-code" style={{ marginBottom: 0 }}>{course.course_code}</p>
                {course.short_form && (
                  <span className="badge" style={{ backgroundColor: '#e2e8f0', color: '#475569', fontSize: '0.7rem' }}>
                    {course.short_form}
                  </span>
                )}
              </div>
              
              <div className="course-details">
                <div className="detail-item">
                  <span className="detail-label">Academic Year</span>
                  <span className="detail-value">{course.academic_year || 'N/A'}</span>
                </div>
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
              <h2>{isEditing ? 'Edit Course' : 'Add New Course'}</h2>
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
                      disabled={isEditing}
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

                <div className="form-row" style={{ display: 'flex', gap: '1rem' }}>
                  <div className="form-group mb-4" style={{ flex: 2 }}>
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
                  <div className="form-group mb-4" style={{ flex: 1 }}>
                    <label className="form-label">Short Form (Optional)</label>
                    <input 
                      type="text" 
                      className="form-control" 
                      name="short_form"
                      value={formData.short_form}
                      onChange={handleChange}
                      placeholder="e.g. OOPS LAB"
                    />
                  </div>
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
                  <div className="form-group mb-4" style={{ flex: 1 }}>
                    <label className="form-label">Academic Year</label>
                    <input 
                      type="text" 
                      className="form-control" 
                      name="academic_year"
                      value={formData.academic_year}
                      onChange={handleChange}
                      placeholder="e.g. 2026-2027"
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
                  {saving ? 'Saving...' : (isEditing ? 'Save Changes' : 'Create Course')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      
      {showCloneModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <h2>Reuse Course: {courseToClone?.course_name}</h2>
              <button className="close-btn" onClick={() => setShowCloneModal(false)}>
                <X size={20} />
              </button>
            </div>
            
            {error && (
              <div className="alert alert-error mb-4">
                <AlertCircle size={18} />
                <span>{error}</span>
              </div>
            )}
            
            <form onSubmit={handleCloneSubmit}>
              <div className="form-group">
                <label className="form-label">Assign New Faculty</label>
                <select 
                  className="form-control"
                  value={cloneData.new_faculty_id}
                  onChange={(e) => setCloneData({...cloneData, new_faculty_id: e.target.value})}
                  required
                >
                  <option value="">Select Faculty...</option>
                  {faculty.map(f => (
                    <option key={f._id || f.id} value={f._id || f.id}>
                      {f.name} ({f.department})
                    </option>
                  ))}
                </select>
              </div>
              
              <div className="form-group">
                <label className="form-label">New Academic Year</label>
                <input 
                  type="text" 
                  className="form-control"
                  value={cloneData.new_academic_year}
                  onChange={(e) => setCloneData({...cloneData, new_academic_year: e.target.value})}
                  placeholder="e.g. 2027-2028"
                  required
                />
              </div>
              
              <div className="modal-footer">
                <button 
                  type="button" 
                  className="btn btn-secondary"
                  onClick={() => setShowCloneModal(false)}
                  disabled={saving}
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  className="btn btn-primary"
                  disabled={saving}
                >
                  {saving ? 'Cloning...' : 'Reuse Course'}
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
