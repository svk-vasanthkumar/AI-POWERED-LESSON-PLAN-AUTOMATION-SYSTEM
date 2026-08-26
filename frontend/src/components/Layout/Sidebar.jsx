import React from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, FileText, FileSpreadsheet, Settings, LogOut, BarChart3, BookOpen, Users, X } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import './Layout.css';

const Sidebar = ({ isOpen, closeSidebar }) => {
  const { logout, user } = useAuth();

  const navItems = [
    { name: 'Dashboard', path: '/dashboard', icon: <LayoutDashboard size={20} /> },
    { name: 'Courses', path: '/courses', icon: <BookOpen size={20} /> },
    ...(user?.role === 'admin' || user?.role === 'hod' ? [{ name: 'Faculty', path: '/faculty', icon: <Users size={20} /> }] : []),
    { name: 'Lesson Plans', path: '/lesson-plans', icon: <FileSpreadsheet size={20} /> },
    { name: 'Documents', path: '/documents', icon: <FileText size={20} /> },
    { name: 'Reports', path: '/reports', icon: <BarChart3 size={20} /> },
    { name: 'Settings', path: '/settings', icon: <Settings size={20} /> },
  ];

  return (
    <aside className={`sidebar ${isOpen ? 'open' : ''}`}>
      <div className="sidebar-header">
        <div className="logo-container">
          <div className="logo-icon">EA</div>
          <h2>Edu<span>AI</span></h2>
        </div>
        <button className="close-sidebar-btn" onClick={closeSidebar}>
          <X size={20} />
        </button>
      </div>
      
      <nav className="sidebar-nav">
        <ul>
          {navItems.map((item) => (
            <li key={item.path}>
              <NavLink 
                to={item.path} 
                className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}
                onClick={closeSidebar}
              >
                {item.icon}
                <span>{item.name}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      
      <div className="sidebar-footer">
        <div className="user-profile">
          <div className="user-avatar">{user?.email?.charAt(0).toUpperCase() || 'U'}</div>
          <div className="user-info">
            <p className="user-name">{user?.name || 'User'}</p>
            <p className="user-role">{user?.role || 'Faculty'}</p>
          </div>
        </div>
        <button onClick={logout} className="logout-btn">
          <LogOut size={18} />
          <span>Logout</span>
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
