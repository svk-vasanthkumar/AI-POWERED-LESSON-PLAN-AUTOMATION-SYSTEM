import React, { useEffect, useRef } from 'react';
import { AlertCircle, CheckCircle, Info, AlertTriangle, X } from 'lucide-react';

const CONFIG = {
  success: {
    icon: CheckCircle,
    iconClass: 'alert-modal-icon success',
    headerClass: 'alert-modal-header-title success',
  },
  error: {
    icon: AlertCircle,
    iconClass: 'alert-modal-icon error',
    headerClass: 'alert-modal-header-title error',
  },
  warning: {
    icon: AlertTriangle,
    iconClass: 'alert-modal-icon warning',
    headerClass: 'alert-modal-header-title warning',
  },
  info: {
    icon: Info,
    iconClass: 'alert-modal-icon info',
    headerClass: 'alert-modal-header-title info',
  },
};

const AlertModal = ({ isOpen, title, message, type = 'info', onClose, isConfirm = false, onConfirm, onCancel }) => {
  const okButtonRef = useRef(null);
  const cfg = CONFIG[type] || CONFIG.info;
  const Icon = cfg.icon;

  useEffect(() => {
    if (isOpen && okButtonRef.current) okButtonRef.current.focus();
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (isConfirm) onCancel();
        else onClose();
      } else if (e.key === 'Enter') {
        if (isConfirm) onConfirm();
        else onClose();
      }
    };
    if (isOpen) window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose, isConfirm, onConfirm, onCancel]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" style={{ zIndex: 9999 }}>
      <div className="alert-modal-card">
        <button className="alert-modal-close" onClick={isConfirm ? onCancel : onClose} aria-label="Close">
          <X size={18} />
        </button>

        <div className={cfg.iconClass}>
          <Icon size={28} />
        </div>

        <h3 className={cfg.headerClass}>{title}</h3>
        <p className="alert-modal-message">{message}</p>

        {isConfirm ? (
          <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', marginTop: '24px' }}>
            <button className="btn btn-secondary" onClick={onCancel}>
              Cancel
            </button>
            <button ref={okButtonRef} className={`btn btn-${type === 'error' || type === 'warning' ? 'danger' : 'primary'}`} onClick={onConfirm}>
              Confirm
            </button>
          </div>
        ) : (
          <button ref={okButtonRef} className="btn btn-primary alert-modal-btn" onClick={onClose} style={{ marginTop: '24px' }}>
            Got it
          </button>
        )}
      </div>

      <style>{`
        .alert-modal-card {
          background: var(--surface-color);
          border-radius: var(--radius-xl);
          padding: 36px 32px 32px;
          max-width: 380px;
          width: 100%;
          text-align: center;
          box-shadow: var(--shadow-xl);
          border: 1px solid var(--border-color);
          position: relative;
          animation: modalSlideUp 0.28s var(--ease-spring);
        }
        .alert-modal-close {
          position: absolute;
          top: 14px;
          right: 14px;
          background: transparent;
          border: none;
          color: var(--text-tertiary);
          cursor: pointer;
          padding: 5px;
          border-radius: var(--radius-xs);
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all var(--transition-fast);
        }
        .alert-modal-close:hover {
          background: var(--surface-hover);
          color: var(--text-primary);
        }
        .alert-modal-icon {
          width: 60px;
          height: 60px;
          border-radius: var(--radius-full);
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 0 auto 20px;
        }
        .alert-modal-icon.success { background: var(--success-light); color: var(--success); }
        .alert-modal-icon.error   { background: var(--error-light);   color: var(--error); }
        .alert-modal-icon.warning { background: var(--warning-light); color: var(--warning); }
        .alert-modal-icon.info    { background: var(--info-light);    color: var(--info); }
        .alert-modal-header-title {
          margin: 0 0 10px;
          font-size: 18px;
          font-weight: 800;
          letter-spacing: -0.02em;
        }
        .alert-modal-header-title.success { color: var(--success-text); }
        .alert-modal-header-title.error   { color: var(--error-text); }
        .alert-modal-header-title.warning { color: var(--warning-text); }
        .alert-modal-header-title.info    { color: var(--text-primary); }
        .alert-modal-message {
          color: var(--text-secondary);
          margin: 0 0 24px;
          font-size: 14px;
          line-height: 1.65;
        }
        .alert-modal-btn { width: 100%; }
      `}</style>
    </div>
  );
};

export default AlertModal;
