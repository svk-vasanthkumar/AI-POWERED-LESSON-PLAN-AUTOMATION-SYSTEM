import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useAlert } from '../../context/AlertContext';
import { authService } from '../../services/authService';
import { User, Lock, Bell, Palette, Edit3, Check, X, ShieldAlert, Eye, EyeOff, Mail, Building2 } from 'lucide-react';
import './Settings.css';

// ── Password Strength Meter ────────────────────────────────────────────────
const getPasswordStrength = (pw) => {
  if (!pw) return { level: 0, label: '', color: '' };
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  if (score <= 1) return { level: 1, label: 'Weak', color: '#ef4444' };
  if (score === 2) return { level: 2, label: 'Fair', color: '#f59e0b' };
  if (score === 3) return { level: 3, label: 'Good', color: '#3b82f6' };
  return { level: 4, label: 'Strong', color: '#10b981' };
};

// ── Confirm Dialog (Email Change Warning) ─────────────────────────────────
const ConfirmDialog = ({ isOpen, onConfirm, onCancel, newEmail }) => {
  if (!isOpen) return null;
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" style={{ maxWidth: 440 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 36, height: 36, borderRadius: 8, background: 'var(--warning-light)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <ShieldAlert size={18} style={{ color: 'var(--warning-text)' }} />
            </div>
            <h2>Confirm Email Change</h2>
          </div>
          <button className="btn-icon" onClick={onCancel}><X size={18} /></button>
        </div>
        <div className="modal-body">
          <p style={{ margin: 0, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
            You are about to change your login email to:
          </p>
          <p style={{ margin: '10px 0', fontWeight: 700, color: 'var(--text-primary)', fontSize: 15 }}>
            {newEmail}
          </p>
          <div style={{ background: 'var(--warning-light)', border: '1px solid #fde68a', borderRadius: 8, padding: '10px 14px', marginTop: 12 }}>
            <p style={{ margin: 0, fontSize: 13, color: 'var(--warning-text)', lineHeight: 1.6 }}>
              ⚠️ You will be <strong>logged out immediately</strong> and must sign in again with the new email address.
            </p>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
          <button className="btn btn-primary" onClick={onConfirm}>Yes, Change Email</button>
        </div>
      </div>
    </div>
  );
};

// ── Main Component ─────────────────────────────────────────────────────────
const Settings = () => {
  const { user, updateUser, logout } = useAuth();
  const { showAlert } = useAlert();
  const [activeTab, setActiveTab] = useState('Profile');

  const isAdmin = user?.role === 'admin';

  // Profile State
  const [profileData, setProfileData] = useState({
    name: user?.name || '',
    email: user?.email || '',
    department: user?.department || ''
  });
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);
  const [showEmailConfirm, setShowEmailConfirm] = useState(false);
  const originalProfile = useRef({ name: '', email: '', department: '' });

  // Security State
  const [securityData, setSecurityData] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: ''
  });
  const [securityLoading, setSecurityLoading] = useState(false);
  const [showCurrentPw, setShowCurrentPw] = useState(false);
  const [showNewPw, setShowNewPw] = useState(false);
  const [showConfirmPw, setShowConfirmPw] = useState(false);

  // Preferences State
  const [preferences, setPreferences] = useState({
    email_notifications: true,
    push_notifications: false,
    dark_mode: false
  });

  // Load initial data
  useEffect(() => {
    if (user?.preferences) {
      setPreferences(user.preferences);
      if (user.preferences.dark_mode) document.body.classList.add('dark-theme');
      else document.body.classList.remove('dark-theme');
    }
    if (user) {
      const data = {
        name: user.name || '',
        email: user.email || '',
        department: user.department || ''
      };
      setProfileData(data);
      originalProfile.current = data;
    }
  }, [user]);

  // ── Profile Handlers ─────────────────────────────────────────────────────
  const handleEditProfile = () => {
    originalProfile.current = { ...profileData };
    setIsEditingProfile(true);
  };

  const handleCancelEdit = () => {
    setProfileData({ ...originalProfile.current });
    setIsEditingProfile(false);
  };

  const handleProfileSubmit = async (e) => {
    e.preventDefault();
    const emailChanged = isAdmin && profileData.email.toLowerCase() !== (user?.email || '').toLowerCase();
    if (emailChanged) {
      setShowEmailConfirm(true);
      return;
    }
    await submitProfileUpdate();
  };

  const submitProfileUpdate = async () => {
    setShowEmailConfirm(false);
    setProfileLoading(true);
    try {
      const payload = {
        name: profileData.name,
        department: profileData.department || undefined,
      };
      if (isAdmin) payload.email = profileData.email;

      const result = await authService.updateProfile(payload);
      updateUser({ name: profileData.name, department: profileData.department });
      showAlert('Profile updated successfully.', 'success', 'Profile Updated');
      setIsEditingProfile(false);

      if (result?.email_changed) {
        showAlert('Email changed — you will be logged out now.', 'info', 'Re-login Required');
        setTimeout(() => logout(), 1800);
      }
    } catch (err) {
      showAlert(err?.response?.data?.detail || err.uiMessage || 'Failed to update profile.', 'error');
    } finally {
      setProfileLoading(false);
    }
  };

  // ── Security Handler ─────────────────────────────────────────────────────
  const handleSecuritySubmit = async (e) => {
    e.preventDefault();
    if (securityData.newPassword !== securityData.confirmPassword) {
      showAlert('New passwords do not match.', 'error');
      return;
    }
    setSecurityLoading(true);
    try {
      await authService.resetPassword(user.email, securityData.currentPassword, securityData.newPassword);
      showAlert('Your password has been changed successfully.', 'success', 'Security Updated');
      setSecurityData({ currentPassword: '', newPassword: '', confirmPassword: '' });
    } catch (err) {
      showAlert(err?.response?.data?.detail || err.uiMessage || 'Failed to change password.', 'error');
    } finally {
      setSecurityLoading(false);
    }
  };

  // ── Preferences Handler ──────────────────────────────────────────────────
  const urlBase64ToUint8Array = (base64String) => {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
      .replace(/\-/g, '+')
      .replace(/_/g, '/');

    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  };

  const handlePreferenceChange = async (key, value) => {
    const newPrefs = { ...preferences, [key]: value };
    setPreferences(newPrefs);
    
    if (key === 'dark_mode') {
      if (value) document.body.classList.add('dark-theme');
      else document.body.classList.remove('dark-theme');
    }

    if (key === 'push_notifications' && value === true) {
      if ('serviceWorker' in navigator && 'PushManager' in window) {
        try {
          const permission = await Notification.requestPermission();
          if (permission === 'granted') {
            const registration = await navigator.serviceWorker.ready;
            const vapidPublicKey = import.meta.env.VITE_VAPID_PUBLIC_KEY;
            const convertedVapidKey = urlBase64ToUint8Array(vapidPublicKey);
            
            const subscription = await registration.pushManager.subscribe({
              userVisibleOnly: true,
              applicationServerKey: convertedVapidKey
            });
            
            // Send subscription to backend
            const { notificationService } = await import('../../services/notificationService');
            await notificationService.subscribeToPush(subscription);
            showAlert('Push notifications enabled successfully.', 'success');
          } else {
            showAlert('Notification permission denied by user.', 'warning');
            newPrefs.push_notifications = false;
            setPreferences(newPrefs);
          }
        } catch (err) {
          console.error("Push subscription failed:", err);
          showAlert('Failed to subscribe to push notifications.', 'error');
          newPrefs.push_notifications = false;
          setPreferences(newPrefs);
        }
      } else {
        showAlert('Push notifications are not supported in this browser.', 'error');
        newPrefs.push_notifications = false;
        setPreferences(newPrefs);
      }
    }

    try {
      await authService.updatePreferences(newPrefs);
      updateUser({ preferences: newPrefs });
    } catch (err) {
      if (key !== 'push_notifications') {
        showAlert('Failed to save preferences.', 'error');
      }
      setPreferences(preferences);
      if (key === 'dark_mode') {
        if (preferences.dark_mode) document.body.classList.add('dark-theme');
        else document.body.classList.remove('dark-theme');
      }
    }
  };

  const pwStrength = getPasswordStrength(securityData.newPassword);

  const tabs = [
    { id: 'Profile', icon: <User size={18} />, label: 'Profile' },
    { id: 'Security', icon: <Lock size={18} />, label: 'Security' },
    { id: 'Notifications', icon: <Bell size={18} />, label: 'Notifications' },
    { id: 'Appearance', icon: <Palette size={18} />, label: 'Appearance' }
  ];

  // ── Tab Content ──────────────────────────────────────────────────────────
  const renderContent = () => {
    switch (activeTab) {
      case 'Profile':
        return (
          <div className="settings-card">
            {/* Profile Header */}
            <div className="profile-hero">
              <div className="profile-hero-avatar">
                {(user?.name || user?.email || 'U').charAt(0).toUpperCase()}
              </div>
              <div className="profile-hero-info">
                <h3 className="profile-hero-name">{user?.name || 'User'}</h3>
                <p className="profile-hero-meta">
                  <span className="role-pill">{user?.role ? (user.role.toLowerCase() === 'hod' ? 'HOD' : user.role.charAt(0).toUpperCase() + user.role.slice(1)) : 'Faculty'}</span>
                  {user?.department && <span className="dept-pill">{user.department}</span>}
                </p>
                <p className="profile-hero-email">{user?.email}</p>
              </div>
              {!isEditingProfile && (
                <button type="button" className="btn btn-secondary settings-edit-btn" onClick={handleEditProfile}>
                  <Edit3 size={15} /> Edit Profile
                </button>
              )}
            </div>

            <div className="settings-divider" />

            <form onSubmit={handleProfileSubmit}>
              <div className="settings-form-grid">
                {/* Full Name */}
                <div className="form-group">
                  <label className="form-label">Full Name</label>
                  <input
                    type="text"
                    className={`form-control${!isEditingProfile ? ' input-readonly' : ''}`}
                    value={profileData.name}
                    onChange={(e) => setProfileData({ ...profileData, name: e.target.value })}
                    readOnly={!isEditingProfile}
                    required
                    minLength={3}
                    id="settings-name"
                  />
                </div>

                {/* Email Address */}
                <div className="form-group">
                  <label className="form-label">
                    <Mail size={13} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
                    Email Address
                  </label>
                  <input
                    type="email"
                    className={`form-control${(!isAdmin || !isEditingProfile) ? ' input-readonly' : ''}`}
                    value={profileData.email}
                    onChange={(e) => setProfileData({ ...profileData, email: e.target.value })}
                    readOnly={!isAdmin || !isEditingProfile}
                    required
                    id="settings-email"
                  />
                  {isAdmin && isEditingProfile ? (
                    <p className="form-hint form-hint-warning">
                      ⚠️ Changing your email will log you out — you must sign in with the new address.
                    </p>
                  ) : !isAdmin ? (
                    <p className="form-hint">Contact your administrator to change your email.</p>
                  ) : null}
                </div>

                {/* Department */}
                <div className="form-group">
                  <label className="form-label">
                    <Building2 size={13} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
                    Department
                  </label>
                  <input
                    type="text"
                    className={`form-control${(!isAdmin || !isEditingProfile) ? ' input-readonly' : ''}`}
                    value={profileData.department}
                    onChange={(e) => setProfileData({ ...profileData, department: e.target.value })}
                    readOnly={!isAdmin || !isEditingProfile}
                    placeholder={isAdmin && isEditingProfile ? 'Enter department name' : (profileData.department || '—')}
                    id="settings-department"
                  />
                  {!isAdmin && (
                    <p className="form-hint">Department is managed by your administrator.</p>
                  )}
                </div>

                {/* Role (always readonly) */}
                <div className="form-group">
                  <label className="form-label">Role</label>
                  <input
                    type="text"
                    className="form-control input-readonly"
                    value={user?.role ? (user.role.toLowerCase() === 'hod' ? 'HOD' : user.role.charAt(0).toUpperCase() + user.role.slice(1)) : ''}
                    readOnly
                    id="settings-role"
                  />
                  <p className="form-hint">Role cannot be changed from here.</p>
                </div>
              </div>

              {isEditingProfile && (
                <div className="settings-form-actions">
                  <button type="submit" className="btn btn-primary" disabled={profileLoading} id="settings-save-btn">
                    {profileLoading ? (
                      <><span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Saving…</>
                    ) : (
                      <><Check size={15} /> Save Changes</>
                    )}
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={handleCancelEdit} disabled={profileLoading} id="settings-cancel-btn">
                    <X size={15} /> Cancel
                  </button>
                </div>
              )}
            </form>

            <ConfirmDialog
              isOpen={showEmailConfirm}
              newEmail={profileData.email}
              onConfirm={submitProfileUpdate}
              onCancel={() => setShowEmailConfirm(false)}
            />
          </div>
        );

      case 'Security':
        return (
          <div className="settings-card">
            <h3 className="settings-section-title">Change Password</h3>
            <form onSubmit={handleSecuritySubmit}>
              {/* Current Password */}
              <div className="form-group mb-4">
                <label className="form-label">Current Password</label>
                <div className="pw-input-wrapper">
                  <input
                    type={showCurrentPw ? 'text' : 'password'}
                    className="form-control"
                    value={securityData.currentPassword}
                    onChange={(e) => setSecurityData({ ...securityData, currentPassword: e.target.value })}
                    required
                    id="current-password"
                  />
                  <button type="button" className="pw-toggle-btn" onClick={() => setShowCurrentPw(v => !v)} tabIndex={-1}>
                    {showCurrentPw ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              {/* New Password */}
              <div className="form-group mb-4">
                <label className="form-label">New Password</label>
                <div className="pw-input-wrapper">
                  <input
                    type={showNewPw ? 'text' : 'password'}
                    className="form-control"
                    value={securityData.newPassword}
                    onChange={(e) => setSecurityData({ ...securityData, newPassword: e.target.value })}
                    required
                    minLength={8}
                    id="new-password"
                  />
                  <button type="button" className="pw-toggle-btn" onClick={() => setShowNewPw(v => !v)} tabIndex={-1}>
                    {showNewPw ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                {/* Strength meter */}
                {securityData.newPassword && (
                  <div className="pw-strength-bar-container">
                    <div className="pw-strength-bar">
                      {[1, 2, 3, 4].map(i => (
                        <div
                          key={i}
                          className="pw-strength-segment"
                          style={{ background: i <= pwStrength.level ? pwStrength.color : 'var(--border-color)' }}
                        />
                      ))}
                    </div>
                    <span className="pw-strength-label" style={{ color: pwStrength.color }}>
                      {pwStrength.label}
                    </span>
                  </div>
                )}
                <p className="form-hint">Min 8 characters. Use uppercase, numbers & symbols for a stronger password.</p>
              </div>

              {/* Confirm Password */}
              <div className="form-group mb-4">
                <label className="form-label">Confirm New Password</label>
                <div className="pw-input-wrapper">
                  <input
                    type={showConfirmPw ? 'text' : 'password'}
                    className={`form-control${securityData.confirmPassword && securityData.confirmPassword !== securityData.newPassword ? ' input-error' : ''}`}
                    value={securityData.confirmPassword}
                    onChange={(e) => setSecurityData({ ...securityData, confirmPassword: e.target.value })}
                    required
                    minLength={8}
                    id="confirm-password"
                  />
                  <button type="button" className="pw-toggle-btn" onClick={() => setShowConfirmPw(v => !v)} tabIndex={-1}>
                    {showConfirmPw ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                {securityData.confirmPassword && securityData.confirmPassword !== securityData.newPassword && (
                  <p className="form-hint form-hint-error">Passwords do not match.</p>
                )}
              </div>

              <div className="mt-6">
                <button type="submit" className="btn btn-primary" disabled={securityLoading} id="update-password-btn">
                  {securityLoading ? (
                    <><span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Updating…</>
                  ) : 'Update Password'}
                </button>
              </div>
            </form>
          </div>
        );

      case 'Notifications':
        return (
          <div className="settings-card">
            <h3 className="settings-section-title">Notification Preferences</h3>
            <div className="preferences-list">
              <div className="preference-item">
                <div className="preference-info">
                  <h4>Email Notifications</h4>
                  <p>Receive updates and alerts via email.</p>
                </div>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={preferences.email_notifications}
                    onChange={(e) => handlePreferenceChange('email_notifications', e.target.checked)}
                    id="pref-email-notif"
                  />
                  <span className="slider" />
                </label>
              </div>

              <div className="preference-item">
                <div className="preference-info">
                  <h4>Push Notifications</h4>
                  <p>Receive in-app push notifications.</p>
                </div>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={preferences.push_notifications}
                    onChange={(e) => handlePreferenceChange('push_notifications', e.target.checked)}
                    id="pref-push-notif"
                  />
                  <span className="slider" />
                </label>
              </div>
            </div>
          </div>
        );

      case 'Appearance':
        return (
          <div className="settings-card">
            <h3 className="settings-section-title">Appearance Settings</h3>
            <div className="preferences-list">
              <div className="preference-item">
                <div className="preference-info">
                  <h4>Dark Mode</h4>
                  <p>Switch to dark theme for easier reading in low light.</p>
                </div>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={preferences.dark_mode}
                    onChange={(e) => handlePreferenceChange('dark_mode', e.target.checked)}
                    id="pref-dark-mode"
                  />
                  <span className="slider" />
                </label>
              </div>
            </div>
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
          <p className="page-subtitle">Manage your account preferences and security.</p>
        </div>
      </div>

      <div className="settings-layout">
        <aside className="settings-sidebar">
          {tabs.map(tab => (
            <button
              key={tab.id}
              className={`settings-tab ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
              id={`settings-tab-${tab.id.toLowerCase()}`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </aside>

        <main className="settings-content">
          {renderContent()}
        </main>
      </div>
    </div>
  );
};

export default Settings;
