import React, { createContext, useContext, useState } from 'react';
import AlertModal from '../components/common/AlertModal';

const AlertContext = createContext();

export const AlertProvider = ({ children }) => {
  const [alertState, setAlertState] = useState({
    isOpen: false,
    title: '',
    message: '',
    type: 'info', // 'info', 'success', 'error', 'warning'
    onClose: null
  });

  const showAlert = (message, type = 'info', title = null) => {
    return new Promise((resolve) => {
      setAlertState({
        isOpen: true,
        message,
        type,
        title: title || (type === 'error' ? 'Error' : type === 'success' ? 'Success' : type === 'warning' ? 'Warning' : 'Notice'),
        onClose: () => resolve(true)
      });
    });
  };

  const closeAlert = () => {
    if (alertState.onClose) {
      alertState.onClose();
    }
    setAlertState(prev => ({ ...prev, isOpen: false }));
  };

  return (
    <AlertContext.Provider value={{ showAlert }}>
      {children}
      {alertState.isOpen && (
        <AlertModal 
          isOpen={alertState.isOpen}
          title={alertState.title}
          message={alertState.message}
          type={alertState.type}
          onClose={closeAlert}
        />
      )}
    </AlertContext.Provider>
  );
};

export const useAlert = () => useContext(AlertContext);
