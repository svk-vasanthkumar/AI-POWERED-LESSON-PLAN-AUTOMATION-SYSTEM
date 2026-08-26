import React from 'react';
import { Bell, User, Menu } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import './Layout.css';

const Topbar = ({ toggleSidebar }) => {
  const { user } = useAuth();

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
        <button className="notification-btn">
          <Bell size={20} />
          <span className="notification-badge">3</span>
        </button>
        
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
