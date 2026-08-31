import React, { useState, useEffect } from 'react';
import { Users, Plus, X, Edit, Trash2, AlertCircle, Mail } from 'lucide-react';
import { facultyService } from '../../services/facultyService';
import { useAuth } from '../../context/AuthContext';
import './Faculty.css';

const Faculty = () => {
  const { user } = useAuth();
  const [faculty, setFaculty] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showEmailModal, setShowEmailModal] = useState(false);
  const [error, setError] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [currentFacultyId, setCurrentFacultyId] = useState(null);
  
  const [selectedFacultyForEmail, setSelectedFacultyForEmail] = useState(null);
  const [emailPassword, setEmailPassword] = useState('');
  const [sendingEmail, setSendingEmail] = useState(false);
  
  // Form state
  const initialFormState = {
    faculty_id: '',
    name: '',
    email: '',
    department: '',
    designation: '',
    password: ''
  };
  const [formData, setFormData] = useState(initialFormState);

  // RBAC Check
  if (user?.role !== 'admin' && user?.role !== 'hod') {
    return (
      <div className="faculty-page" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '70vh', flexDirection: 'column' }}>
        <AlertCircle size={48} className="text-error mb-4" />
        <h2>Access Denied</h2>
        <p className="text-secondary mt-2">You do not have permission to view or manage the Faculty directory.</p>
      </div>
    );
  }

  const fetchData = async () => {
    try {
      setLoading(true);
      const data = await facultyService.getAll();
      setFaculty(data);
    } catch (err) {
      console.error("Failed to fetch faculty data", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
  };

  const handleEdit = (facultyMember) => {
    setFormData({
      faculty_id: facultyMember.faculty_id,
      name: facultyMember.name,
      email: facultyMember.email,
      department: facultyMember.department,
      designation: facultyMember.designation
    });
    setCurrentFacultyId(facultyMember._id || facultyMember.id);
    setIsEditing(true);
    setShowModal(true);
  };

  const handleDelete = async (id) => {
    if (window.confirm('Are you sure you want to delete this faculty member?')) {
      try {
        await facultyService.delete(id);
        await fetchData();
      } catch (err) {
        alert(err.uiMessage || 'Failed to delete faculty member.');
      }
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    
    try {
      if (isEditing) {
        // Only send fields that can be updated according to schema
        const updateData = {
          name: formData.name,
          email: formData.email,
          department: formData.department,
          designation: formData.designation
        };
        await facultyService.update(currentFacultyId, updateData);
      } else {
        await facultyService.create(formData);
      }
      await fetchData(); // Refresh list
      closeModal();
    } catch (err) {
      setError(err.uiMessage || `Failed to ${isEditing ? 'update' : 'create'} faculty. Please try again.`);
    } finally {
      setSaving(false);
    }
  };

  const closeModal = () => {
    setShowModal(false);
    setIsEditing(false);
    setCurrentFacultyId(null);
    setFormData(initialFormState);
    setError('');
  };

  const handleSendEmail = (faculty) => {
    setSelectedFacultyForEmail(faculty);
    setEmailPassword('');
    setShowEmailModal(true);
  };

  const confirmSendEmail = async (e) => {
    e.preventDefault();
    if (!emailPassword || emailPassword.length < 6) {
      alert("Please enter a valid password (min 6 characters).");
      return;
    }
    
    setSendingEmail(true);
    try {
      await facultyService.sendEmail(selectedFacultyForEmail._id || selectedFacultyForEmail.id, emailPassword);
      alert('Welcome email sent successfully!');
      setShowEmailModal(false);
    } catch (err) {
      alert(err.uiMessage || 'Failed to send email. Please try again.');
    } finally {
      setSendingEmail(false);
    }
  };

  return (
    <div className="faculty-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Faculty Management</h1>
          <p className="page-subtitle">Manage faculty profiles and department assignments.</p>
        </div>
        {(user?.role === 'admin' || user?.role === 'hod') && (
          <button className="btn btn-primary" onClick={() => setShowModal(true)}>
            <Plus size={18} />
            Add Faculty
          </button>
        )}
      </div>

      <div className="table-container mt-4">
        <table className="data-table">
          <thead>
            <tr>
              <th>Faculty ID</th>
              <th>Name</th>
              <th>Email</th>
              <th>Department</th>
              <th>Designation</th>
              {(user?.role === 'admin' || user?.role === 'hod') && <th>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={user?.role === 'admin' || user?.role === 'hod' ? "6" : "5"} className="text-center py-4">
                  Loading faculty...
                </td>
              </tr>
            ) : faculty.length === 0 ? (
              <tr>
                <td colSpan={user?.role === 'admin' || user?.role === 'hod' ? "6" : "5"} className="text-center py-4 text-secondary">
                  No faculty members found.
                </td>
              </tr>
            ) : (
              faculty.map(f => (
                <tr key={f._id || f.id}>
                  <td className="font-medium">{f.faculty_id}</td>
                  <td>{f.name}</td>
                  <td>{f.email}</td>
                  <td>{f.department}</td>
                  <td>{f.designation}</td>
                  {(user?.role === 'admin' || user?.role === 'hod') && (
                    <td>
                      <div className="action-buttons">
                        {f.has_logged_in === false && (
                          <button 
                            className="btn-icon text-info" 
                            onClick={() => handleSendEmail(f)} 
                            title="Send Welcome Email"
                          >
                            <Mail size={18} />
                          </button>
                        )}
                        <button className="btn-icon text-primary" onClick={() => handleEdit(f)} title="Edit">
                          <Edit size={18} />
                        </button>
                        <button className="btn-icon text-error" onClick={() => handleDelete(f._id || f.id)} title="Delete">
                          <Trash2 size={18} />
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showModal && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '600px' }}>
            <div className="modal-header">
              <h2>{isEditing ? 'Edit Faculty' : 'Add New Faculty'}</h2>
              <button className="btn-icon" onClick={closeModal}><X size={20} /></button>
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
                    <label className="form-label">Faculty ID</label>
                    <input 
                      type="text" 
                      className="form-control" 
                      name="faculty_id"
                      value={formData.faculty_id}
                      onChange={handleChange}
                      placeholder="e.g. FAC001"
                      required
                      disabled={isEditing}
                      minLength={6}
                      maxLength={6}
                      pattern=".{6}"
                      title="Faculty ID must be exactly 6 characters"
                    />
                    {isEditing && <small className="text-secondary mt-1">Faculty ID cannot be changed.</small>}
                  </div>
                  <div className="form-group mb-4" style={{ flex: 2 }}>
                    <label className="form-label">Full Name</label>
                    <input 
                      type="text" 
                      className="form-control" 
                      name="name"
                      value={formData.name}
                      onChange={handleChange}
                      placeholder="e.g. Dr. Jane Smith"
                      required
                      minLength={3}
                    />
                  </div>
                </div>

                <div className="form-row" style={{ display: 'flex', gap: '1rem' }}>
                  <div className="form-group mb-4" style={{ flex: 1 }}>
                    <label className="form-label">Email Address</label>
                    <input 
                      type="email" 
                      className="form-control" 
                      name="email"
                      value={formData.email}
                      onChange={handleChange}
                      placeholder="e.g. jane.smith@university.edu"
                      required
                    />
                  </div>
                  {!isEditing && (
                    <div className="form-group mb-4" style={{ flex: 1 }}>
                      <label className="form-label">Temporary Password</label>
                      <input 
                        type="password" 
                        className="form-control" 
                        name="password"
                        value={formData.password}
                        onChange={handleChange}
                        placeholder="Assign an initial password"
                        required={!isEditing}
                        minLength={6}
                      />
                    </div>
                  )}
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
                    <label className="form-label">Designation</label>
                    <select 
                      className="form-control" 
                      name="designation"
                      value={formData.designation}
                      onChange={handleChange}
                      required
                    >
                      <option value="" disabled>Select Designation</option>
                      <option value="Professor">Professor</option>
                      <option value="Associate Professor">Associate Professor</option>
                      <option value="Assistant Professor">Assistant Professor</option>
                      <option value="Lecturer">Lecturer</option>
                      <option value="HOD">Head of Department</option>
                    </select>
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={closeModal}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? 'Saving...' : (isEditing ? 'Save Changes' : 'Add Faculty')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Send Email Modal */}
      {showEmailModal && selectedFacultyForEmail && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '400px' }}>
            <div className="modal-header">
              <h2>Send Credentials</h2>
              <button className="close-btn" onClick={() => setShowEmailModal(false)}>
                <X size={20} />
              </button>
            </div>
            
            <form onSubmit={confirmSendEmail}>
              <div className="modal-body">
                <p style={{ marginBottom: '1rem', color: '#64748b', fontSize: '0.9rem' }}>
                  Enter the temporary password you want to send to <strong>{selectedFacultyForEmail.email}</strong>. 
                  This will securely update their password and send the welcome email.
                </p>
                <div className="form-group mb-4">
                  <label className="form-label">Temporary Password to Send</label>
                  <input 
                    type="text" 
                    className="form-control" 
                    value={emailPassword}
                    onChange={(e) => setEmailPassword(e.target.value)}
                    placeholder="Enter password (min 6 characters)"
                    required
                    minLength={6}
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowEmailModal(false)} disabled={sendingEmail}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={sendingEmail}>
                  {sendingEmail ? 'Sending...' : 'Confirm & Send'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Faculty;
