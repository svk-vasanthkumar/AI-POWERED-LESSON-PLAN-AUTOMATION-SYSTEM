import React, { useEffect, useRef } from 'react';
import { AlertCircle, CheckCircle, Info, AlertTriangle, X } from 'lucide-react';

const AlertModal = ({ isOpen, title, message, type, onClose }) => {
  const modalRef = useRef(null);
  const okButtonRef = useRef(null);

  useEffect(() => {
    if (isOpen && okButtonRef.current) {
      okButtonRef.current.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      } else if (e.key === 'Enter') {
        onClose();
      }
    };
    
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
    }
    
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const getIcon = () => {
    switch (type) {
      case 'success':
        return <CheckCircle size={32} className="text-success" />;
      case 'error':
        return <AlertCircle size={32} className="text-error" />;
      case 'warning':
        return <AlertTriangle size={32} className="text-warning" />;
      case 'info':
      default:
        return <Info size={32} className="text-primary" />;
    }
  };

  const getHeaderStyle = () => {
    switch (type) {
      case 'error':
        return { color: 'var(--error)' };
      case 'success':
        return { color: 'var(--success)' };
      case 'warning':
        return { color: 'var(--warning)' };
      default:
        return { color: 'var(--text-primary)' };
    }
  };

  return (
    <div className="modal-overlay" style={{ zIndex: 9999 }}>
      <div 
        className="modal-content" 
        ref={modalRef}
        style={{ 
          maxWidth: '400px', 
          textAlign: 'center',
          animation: 'fadeIn 0.2s ease-out' 
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1rem' }}>
          {getIcon()}
        </div>
        <h3 style={{ ...getHeaderStyle(), marginBottom: '0.75rem', fontSize: '1.25rem' }}>
          {title}
        </h3>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem', lineHeight: '1.5' }}>
          {message}
        </p>
        <button 
          ref={okButtonRef}
          className="btn btn-primary w-100" 
          onClick={onClose}
        >
          OK
        </button>
      </div>
    </div>
  );
};

export default AlertModal;
