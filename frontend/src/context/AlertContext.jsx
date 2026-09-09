import React, { createContext, useContext, useState } from 'react';
import AlertModal from '../components/common/AlertModal';

const AlertContext = createContext(null);

export function AlertProvider({ children }) {
  const [alertState, setAlertState] = useState({
    isOpen: false,
    title: '',
    message: '',
    type: 'info',
    isConfirm: false,
    onClose: null,
    onConfirm: null,
    onCancel: null,
  });

  const showAlert = (message, type = 'info', title = null) => {
    return new Promise((resolve) => {
      setAlertState({
        isOpen: true,
        message,
        type,
        title: title || (type === 'error' ? 'Error' : type === 'success' ? 'Success' : type === 'warning' ? 'Warning' : 'Notice'),
        isConfirm: false,
        onClose: () => resolve(true),
      });
    });
  };

  const showConfirm = (message, title = 'Confirm Action', type = 'warning') => {
    return new Promise((resolve) => {
      setAlertState({
        isOpen: true,
        message,
        type,
        title,
        isConfirm: true,
        onConfirm: () => {
          setAlertState(prev => ({ ...prev, isOpen: false }));
          resolve(true);
        },
        onCancel: () => {
          setAlertState(prev => ({ ...prev, isOpen: false }));
          resolve(false);
        },
      });
    });
  };

  const closeAlert = () => {
    if (alertState.onClose) alertState.onClose();
    setAlertState((prev) => ({ ...prev, isOpen: false }));
  };

  return (
    <AlertContext.Provider value={{ showAlert, showConfirm }}>
      {children}
      {alertState.isOpen && (
        <AlertModal
          isOpen={alertState.isOpen}
          title={alertState.title}
          message={alertState.message}
          type={alertState.type}
          onClose={closeAlert}
          isConfirm={alertState.isConfirm}
          onConfirm={alertState.onConfirm}
          onCancel={alertState.onCancel}
        />
      )}
    </AlertContext.Provider>
  );
}

export function useAlert() {
  const ctx = useContext(AlertContext);
  if (!ctx) throw new Error('useAlert must be used within an AlertProvider');
  return ctx;
}
