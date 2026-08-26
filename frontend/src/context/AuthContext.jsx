import React, { createContext, useContext, useState, useEffect } from 'react';
import { authService } from '../services/authService';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchUser = async () => {
      const token = localStorage.getItem('jwt_token');
      if (token) {
        try {
          const profile = await authService.getProfile();
          setUser(profile);
        } catch (error) {
          console.error("Failed to fetch user profile", error);
          authService.logout();
        }
      }
      setLoading(false);
    };

    fetchUser();
  }, []);

  const login = async (email, password) => {
    const data = await authService.login(email, password);
    const profile = await authService.getProfile();
    setUser(profile);
    return profile;
  };

  const resetPassword = async (email, current_password, new_password) => {
    return await authService.resetPassword(email, current_password, new_password);
  };

  const logout = () => {
    authService.logout();
    setUser(null);
  };

  const updateUser = (updatedUser) => {
    setUser({ ...user, ...updatedUser });
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, resetPassword, logout, updateUser }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
