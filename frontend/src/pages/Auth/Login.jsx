import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { LogIn, BookOpen, UserPlus } from 'lucide-react';
import './Login.css';

const Login = () => {
  const [isResettingPassword, setIsResettingPassword] = useState(false);
  const [isForgotPassword, setIsForgotPassword] = useState(false);
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    newPassword: ''
  });
  
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [loading, setLoading] = useState(false);
  const { login, resetPassword, user } = useAuth();
  const navigate = useNavigate();

  React.useEffect(() => {
    if (user) {
      navigate('/dashboard', { replace: true });
    }
  }, [user, navigate]);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccessMsg('');
    setLoading(true);
    
    try {
      if (isForgotPassword) {
        const { authService } = await import('../../services/authService');
        const res = await authService.forgotPassword(formData.email);
        setSuccessMsg(res.message || "Reset link sent to your email.");
      } else if (isResettingPassword) {
        await resetPassword(formData.email, formData.password, formData.newPassword);
        setIsResettingPassword(false);
        setFormData({ ...formData, password: '', newPassword: '' });
        setSuccessMsg("Password reset successfully. Please log in with your new password.");
      } else {
        await login(formData.email, formData.password);
        navigate('/dashboard');
      }
    } catch (err) {
      if (isForgotPassword) {
        setError(err.uiMessage || 'Failed to send reset link.');
      } else {
        setError(err.uiMessage || `Failed to ${isResettingPassword ? 'reset password' : 'login'}. Please check your information.`);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo bg-primary text-white">
            <BookOpen size={24} />
          </div>
          <h2>Edu<span>AI</span></h2>
          <p>{isForgotPassword ? 'Reset your password' : isResettingPassword ? 'Reset your temporary password' : 'Sign in to your academic dashboard'}</p>
        </div>
        
        <form onSubmit={handleSubmit} className="login-form">
          
          <div className="form-group">
            <label>Email Address</label>
            <input 
              type="email" 
              name="email"
              required
              placeholder="faculty@university.edu"
              value={formData.email}
              onChange={handleChange}
              className="form-control"
            />
          </div>
          
          {!isForgotPassword && (
            <div className="form-group">
              <label>
                {isResettingPassword ? "Current / Temporary Password" : "Password"}
              </label>
              <input 
                type="password" 
                name="password"
                required
                placeholder="••••••••"
                value={formData.password}
                onChange={handleChange}
                className="form-control"
              />
            </div>
          )}
          
          {isResettingPassword && !isForgotPassword && (
            <div className="form-group">
              <label>New Password</label>
              <input 
                type="password" 
                name="newPassword"
                required
                placeholder="••••••••"
                value={formData.newPassword}
                onChange={handleChange}
                className="form-control"
                minLength={6}
              />
            </div>
          )}
          
          {!isResettingPassword && !isForgotPassword && (
            <div style={{ textAlign: 'right', marginBottom: '1rem' }}>
              <button 
                type="button" 
                className="toggle-auth-btn" 
                style={{ fontSize: '0.85rem' }}
                onClick={() => { setIsForgotPassword(true); setError(''); setSuccessMsg(''); }}
              >
                Forgot Password?
              </button>
            </div>
          )}
          
          {error && <div className="login-error">{error}</div>}
          {successMsg && <div className="login-error" style={{ backgroundColor: 'rgba(46, 204, 113, 0.1)', color: '#2ecc71', borderLeftColor: '#2ecc71' }}>{successMsg}</div>}
          
          <button type="submit" className="btn btn-primary login-btn" disabled={loading}>
            {loading ? 'Processing...' : (
              isForgotPassword ? 'Send Reset Link' : isResettingPassword ? 'Change Password' : <><LogIn size={18} /> Sign In</>
            )}
          </button>
        </form>
        
        <div className="login-footer">
          <p>
            {isForgotPassword || isResettingPassword ? 'Remembered your password? ' : "First time logging in? "}
            <button 
              className="toggle-auth-btn" 
              onClick={() => { 
                if (isForgotPassword || isResettingPassword) {
                  setIsForgotPassword(false); 
                  setIsResettingPassword(false);
                } else {
                  setIsResettingPassword(true);
                }
                setError('');
                setSuccessMsg('');
              }}
              type="button"
            >
              {isForgotPassword || isResettingPassword ? 'Sign In' : 'Change Password'}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
};

export default Login;
