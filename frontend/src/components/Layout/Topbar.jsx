import React, { useState, useEffect, useRef } from 'react';
import { Bell, Menu, Check, Info, CheckCircle, AlertTriangle, AlertOctagon } from 'lucide-react';

import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { notificationService } from '../../services/notificationService';
import './Layout.css';

const Topbar = ({ toggleSidebar }) => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef(null);

  const fetchNotifications = async () => {
    if (!user) return;
    try {
      const data = await notificationService.getAll();
      setNotifications(data);
    } catch (err) {
      console.error("Failed to fetch notifications:", err);
    }
  };

  useEffect(() => {
    fetchNotifications();
    const intervalId = setInterval(fetchNotifications, 30000); // Poll every 30s
    return () => clearInterval(intervalId);
  }, [user]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleMarkAsRead = async (id, e) => {
    if (e) e.stopPropagation();
    try {
      await notificationService.markAsRead(id);
      setNotifications(prev => prev.map(n => n._id === id ? { ...n, read: true } : n));
    } catch (err) {
      console.error(err);
    }
  };

  const handleMarkAllAsRead = async () => {
    try {
      await notificationService.markAllAsRead();
      setNotifications(prev => prev.map(n => ({ ...n, read: true })));
    } catch (err) {
      console.error(err);
    }
  };

  const unreadCount = notifications.filter(n => !n.read).length;

  const handleNotificationClick = (notification) => {
    if (!notification.read) {
      handleMarkAsRead(notification._id);
    }
    if (notification.link) {
      setShowDropdown(false);
      navigate(notification.link);
    }
  };

  const getSeverityBadge = (severity, type) => {
    const lev = (severity || type || 'INFO').toUpperCase();
    switch (lev) {
      case 'CRITICAL':
      case 'ERROR':
        return <span className="notification-severity-badge badge-critical">CRITICAL</span>;
      case 'WARNING':
        return <span className="notification-severity-badge badge-warning">WARNING</span>;
      case 'SUCCESS':
        return <span className="notification-severity-badge badge-success">SUCCESS</span>;
      default:
        return <span className="notification-severity-badge badge-info">INFO</span>;
    }
  };

  const getIcon = (severity, type) => {
    const lev = (severity || type || 'INFO').toUpperCase();
    switch (lev) {
      case 'CRITICAL':
        return <AlertOctagon size={16} style={{ color: '#ef4444' }} />;
      case 'ERROR':
        return <AlertTriangle size={16} style={{ color: '#f97316' }} />;
      case 'WARNING':
        return <AlertTriangle size={16} style={{ color: '#f59e0b' }} />;
      case 'SUCCESS':
        return <CheckCircle size={16} style={{ color: '#10b981' }} />;
      default:
        return <Info size={16} style={{ color: '#6366f1' }} />;
    }
  };

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="mobile-menu-btn" onClick={toggleSidebar}>
          <Menu size={24} />
        </button>
        <div className="topbar-search">
        </div>
      </div>
      
      <div className="topbar-actions">
        <div className="notification-wrapper" ref={dropdownRef} style={{ position: 'relative' }}>
          <button className="notification-btn" onClick={() => setShowDropdown(!showDropdown)} id="notification-bell-btn">
            <Bell size={20} />
            {unreadCount > 0 && <span className="notification-badge">{unreadCount}</span>}
          </button>
          
          {showDropdown && (
            <div className="notification-dropdown">
              <div className="notification-header">
                <h3>Notifications</h3>
                {unreadCount > 0 && (
                  <button className="mark-all-btn" onClick={handleMarkAllAsRead}>
                    Mark all read
                  </button>
                )}
              </div>
              <div className="notification-list">
                {notifications.length === 0 ? (
                  <div className="notification-empty">No notifications</div>
                ) : (
                  notifications.map(notification => (
                    <div 
                      key={notification._id} 
                      className={`notification-item ${!notification.read ? 'unread' : ''}`}
                      onClick={() => handleNotificationClick(notification)}
                      style={{ cursor: notification.link ? 'pointer' : 'default' }}
                    >
                      <div className="notification-icon">
                        {getIcon(notification.severity, notification.type)}
                      </div>
                      <div className="notification-content">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '2px' }}>
                          <h4>{notification.title}</h4>
                          {getSeverityBadge(notification.severity, notification.type)}
                        </div>
                        <p>{notification.message}</p>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span className="notification-time">
                            {new Date(notification.created_at).toLocaleDateString()} {new Date(notification.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                          {notification.actor_name && (
                            <span style={{ fontSize: '10.5px', color: 'var(--text-tertiary)', fontWeight: 500 }}>
                              By: {notification.actor_name}
                            </span>
                          )}
                        </div>
                      </div>
                      {!notification.read && (
                        <button className="mark-read-btn" onClick={(e) => { e.stopPropagation(); handleMarkAsRead(notification._id, e); }} title="Mark as read">
                          <Check size={14} />
                        </button>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
        
        <div className="user-profile-menu">
          <div className="user-avatar">
            {(user?.name || user?.email || 'U').charAt(0).toUpperCase()}
          </div>
          <div className="user-info">
            <p className="user-name">{user?.name || 'User'}</p>
            <p className="user-role">{user?.role ? (user.role.toLowerCase() === 'hod' ? 'HOD' : user.role.charAt(0).toUpperCase() + user.role.slice(1)) : 'Faculty'}</p>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Topbar;
