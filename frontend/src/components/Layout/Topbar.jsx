import React, { useState, useEffect, useRef } from 'react';
import { Bell, User, Menu, Check, Info, CheckCircle, AlertTriangle } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { notificationService } from '../../services/notificationService';
import './Layout.css';

const Topbar = ({ toggleSidebar }) => {
  const { user } = useAuth();
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
    e.stopPropagation();
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

  const getIcon = (type) => {
    switch(type) {
      case 'success': return <CheckCircle size={16} className="text-success" />;
      case 'warning': return <AlertTriangle size={16} className="text-warning" />;
      default: return <Info size={16} className="text-primary" />;
    }
  };

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="mobile-menu-btn" onClick={toggleSidebar}>
          <Menu size={24} />
        </button>
        <div className="topbar-search">
          {/* Search could go here if needed later */}
        </div>
      </div>
      
      <div className="topbar-actions">
        <div className="notification-wrapper" ref={dropdownRef} style={{ position: 'relative' }}>
          <button className="notification-btn" onClick={() => setShowDropdown(!showDropdown)}>
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
                    <div key={notification._id} className={`notification-item ${!notification.read ? 'unread' : ''}`}>
                      <div className="notification-icon">
                        {getIcon(notification.type)}
                      </div>
                      <div className="notification-content">
                        <h4>{notification.title}</h4>
                        <p>{notification.message}</p>
                        <span className="notification-time">
                          {new Date(notification.created_at).toLocaleDateString()} {new Date(notification.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                      {!notification.read && (
                        <button className="mark-read-btn" onClick={(e) => handleMarkAsRead(notification._id, e)} title="Mark as read">
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
          <div className="user-avatar bg-primary-light text-primary">
            <User size={18} />
          </div>
          <div className="user-info">
            <p className="user-name">{user?.name || 'User'}</p>
            <p className="user-role">{user?.role ? user.role.charAt(0).toUpperCase() + user.role.slice(1) : 'Faculty'}</p>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Topbar;
