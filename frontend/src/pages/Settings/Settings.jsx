import React, { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { authService } from '../../services/authService';
import { User, Lock, Bell, Palette, Save } from 'lucide-react';
import './Settings.css';

const Settings = () => {
  const { user, updateUser } = useAuth();
  const [activeTab, setActiveTab] = useState('Profile');
  
  // Profile State
  const [profileData, setProfileData] = useState({
    name: user?.name || '',
    department: user?.department || ''
  });
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [profileStatus, setProfileStatus] = useState({ loading: false, message: '', error: false });

  // Security State
  const [securityData, setSecurityData] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: ''
  });
  const [securityStatus, setSecurityStatus] = useState({ loading: false, message: '', error: false });

  // Preferences State
  const [preferences, setPreferences] = useState({
    email_notifications: true,
    push_notifications: false,
    dark_mode: false
  });
  const [prefStatus, setPrefStatus] = useState({ loading: false, message: '', error: false });

  // Load initial preferences
  useEffect(() => {
    if (user?.preferences) {
      setPreferences(user.preferences);
      // Apply dark mode
      if (user.preferences.dark_mode) {
        document.body.classList.add('dark-theme');
      } else {
        document.body.classList.remove('dark-theme');
      }
    }
  }, [user]);

  // Handle Profile Update
  const handleProfileSubmit = async (e) => {
    e.preventDefault();
    if (!isEditingProfile) {
      setIsEditingProfile(true);
      return;
    }
    
    setProfileStatus({ loading: true, message: '', error: false });
    try {
      await authService.updateProfile(profileData);
      updateUser(profileData);
      setProfileStatus({ loading: false, message: 'Profile updated successfully!', error: false });
      setIsEditingProfile(false);
    } catch (err) {
      setProfileStatus({ loading: false, message: err.response?.data?.detail || 'Failed to update profile', error: true });
    }
    setTimeout(() => setProfileStatus(prev => ({ ...prev, message: '' })), 3000);
  };

  // Handle Security Update
  const handleSecuritySubmit = async (e) => {
    e.preventDefault();
    if (securityData.newPassword !== securityData.confirmPassword) {
      setSecurityStatus({ loading: false, message: 'Passwords do not match', error: true });
      return;
    }
    
    setSecurityStatus({ loading: true, message: '', error: false });
    try {
      await authService.resetPassword(user.email, securityData.currentPassword, securityData.newPassword);
      setSecurityStatus({ loading: false, message: 'Password changed successfully!', error: false });
      setSecurityData({ currentPassword: '', newPassword: '', confirmPassword: '' });
    } catch (err) {
      setSecurityStatus({ loading: false, message: err.response?.data?.detail || 'Failed to change password', error: true });
    }
    setTimeout(() => setSecurityStatus(prev => ({ ...prev, message: '' })), 3000);
  };

  // Handle Preferences Update
  const handlePreferenceChange = async (key, value) => {
    const newPrefs = { ...preferences, [key]: value };
    setPreferences(newPrefs);
    
    if (key === 'dark_mode') {
      if (value) document.body.classList.add('dark-theme');
      else document.body.classList.remove('dark-theme');
    }
    
    setPrefStatus({ loading: true, message: '', error: false });
    try {
      await authService.updatePreferences(newPrefs);
      updateUser({ preferences: newPrefs });
      setPrefStatus({ loading: false, message: 'Preferences saved!', error: false });
    } catch (err) {
      setPrefStatus({ loading: false, message: 'Failed to save preferences', error: true });
      // Revert if failed
      setPreferences(preferences);
    }
    setTimeout(() => setPrefStatus(prev => ({ ...prev, message: '' })), 3000);
  };

  const renderContent = () => {
    switch (activeTab) {
      case 'Profile':
        return (
          <div className="settings-card">
            <h3 className="settings-section-title">Profile Information</h3>
            <form onSubmit={handleProfileSubmit}>
              <div className="form-group mb-4">
                <label>Full Name</label>
                <input 
                  type="text" 
                  className="form-control" 
                  value={profileData.name} 
                  onChange={(e) => setProfileData({...profileData, name: e.target.value})}
                  readOnly={!isEditingProfile} 
                />
              </div>
              <div className="form-group mb-4">
                <label>Email Address</label>
                <input type="email" className="form-control" value={user?.email || ''} readOnly />
                <small className="text-secondary mt-1">Email address cannot be changed.</small>
              </div>
              <div className="form-group mb-4">
                <label>Department</label>
                <input 
                  type="text" 
                  className="form-control" 
                  value={profileData.department} 
                  onChange={(e) => setProfileData({...profileData, department: e.target.value})}
                  readOnly={!isEditingProfile} 
                />
              </div>
              <div className="form-group mb-4">
                <label>Role</label>
                <input type="text" className="form-control" value={user?.role || ''} readOnly />
              </div>
              
              {profileStatus.message && (
                <div className={`alert ${profileStatus.error ? 'alert-error' : 'alert-success'} mb-4`}>
                  {profileStatus.message}
                </div>
              )}
              
              <div className="flex gap-4 mt-6">
                {isEditingProfile ? (
                  <div style={{ display: 'flex', gap: '10px' }}>
                    <button type="submit" className="btn btn-primary" disabled={profileStatus.loading}>
                      {profileStatus.loading ? 'Saving...' : 'Save Changes'}
                    </button>
                    <button 
                      type="button" 
                      className="btn btn-secondary" 
                      onClick={() => {
                        setIsEditingProfile(false);
                        setProfileData({ name: user?.name, department: user?.department });
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button type="submit" className="btn btn-primary">Edit Profile</button>
                )}
              </div>
            </form>
          </div>
        );
      case 'Security':
        return (
          <div className="settings-card">
            <h3 className="settings-section-title">Change Password</h3>
            <form onSubmit={handleSecuritySubmit}>
              <div className="form-group mb-4">
                <label>Current Password</label>
                <input 
                  type="password" 
                  className="form-control" 
                  value={securityData.currentPassword}
                  onChange={(e) => setSecurityData({...securityData, currentPassword: e.target.value})}
                  required 
                />
              </div>
              <div className="form-group mb-4">
                <label>New Password</label>
                <input 
                  type="password" 
                  className="form-control" 
                  value={securityData.newPassword}
                  onChange={(e) => setSecurityData({...securityData, newPassword: e.target.value})}
                  required 
                  minLength={6}
                />
              </div>
              <div className="form-group mb-4">
                <label>Confirm New Password</label>
                <input 
                  type="password" 
                  className="form-control" 
                  value={securityData.confirmPassword}
                  onChange={(e) => setSecurityData({...securityData, confirmPassword: e.target.value})}
                  required 
                  minLength={6}
                />
              </div>
              
              {securityStatus.message && (
                <div className={`alert ${securityStatus.error ? 'alert-error' : 'alert-success'} mb-4`}>
                  {securityStatus.message}
                </div>
              )}
              
              <button type="submit" className="btn btn-primary mt-2" disabled={securityStatus.loading}>
                {securityStatus.loading ? 'Updating...' : 'Update Password'}
              </button>
            </form>
          </div>
        );
      case 'Notifications':
        return (
          <div className="settings-card">
            <h3 className="settings-section-title">Notification Preferences</h3>
            <div className="preferences-list">
              <div className="preference-item mb-4" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h4 style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Email Notifications</h4>
                  <p style={{ fontSize: '14px', color: 'var(--text-secondary)', margin: 0 }}>Receive updates and alerts via email.</p>
                </div>
                <label className="switch">
                  <input 
                    type="checkbox" 
                    checked={preferences.email_notifications} 
                    onChange={(e) => handlePreferenceChange('email_notifications', e.target.checked)} 
                  />
                  <span className="slider round"></span>
                </label>
              </div>
              <hr style={{ margin: '16px 0', borderColor: 'var(--border-color)' }} />
              <div className="preference-item mb-4" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h4 style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Push Notifications</h4>
                  <p style={{ fontSize: '14px', color: 'var(--text-secondary)', margin: 0 }}>Receive in-app push notifications.</p>
                </div>
                <label className="switch">
                  <input 
                    type="checkbox" 
                    checked={preferences.push_notifications} 
                    onChange={(e) => handlePreferenceChange('push_notifications', e.target.checked)} 
                  />
                  <span className="slider round"></span>
                </label>
              </div>
            </div>
            {prefStatus.message && (
              <div className={`alert ${prefStatus.error ? 'alert-error' : 'alert-success'} mt-4`}>
                {prefStatus.message}
              </div>
            )}
          </div>
        );
      case 'Appearance':
        return (
          <div className="settings-card">
            <h3 className="settings-section-title">Appearance Settings</h3>
            <div className="preferences-list">
              <div className="preference-item mb-4" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h4 style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Dark Mode</h4>
                  <p style={{ fontSize: '14px', color: 'var(--text-secondary)', margin: 0 }}>Switch to dark theme for easier reading in low light.</p>
                </div>
                <label className="switch">
                  <input 
                    type="checkbox" 
                    checked={preferences.dark_mode} 
                    onChange={(e) => handlePreferenceChange('dark_mode', e.target.checked)} 
                  />
                  <span className="slider round"></span>
                </label>
              </div>
            </div>
            {prefStatus.message && (
              <div className={`alert ${prefStatus.error ? 'alert-error' : 'alert-success'} mt-4`}>
                {prefStatus.message}
              </div>
            )}
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="settings-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">Manage your account preferences and application settings.</p>
        </div>
      </div>

      <div className="settings-layout">
        <div className="settings-sidebar">
          <button 
            className={`settings-tab ${activeTab === 'Profile' ? 'active' : ''}`}
            onClick={() => setActiveTab('Profile')}
          >
            <User size={18} /> Profile
          </button>
          <button 
            className={`settings-tab ${activeTab === 'Security' ? 'active' : ''}`}
            onClick={() => setActiveTab('Security')}
          >
            <Lock size={18} /> Security
          </button>
          <button 
            className={`settings-tab ${activeTab === 'Notifications' ? 'active' : ''}`}
            onClick={() => setActiveTab('Notifications')}
          >
            <Bell size={18} /> Notifications
          </button>
          <button 
            className={`settings-tab ${activeTab === 'Appearance' ? 'active' : ''}`}
            onClick={() => setActiveTab('Appearance')}
          >
            <Palette size={18} /> Appearance
          </button>
        </div>

        <div className="settings-content">
          {renderContent()}
        </div>
      </div>
    </div>
  );
};

export default Settings;
