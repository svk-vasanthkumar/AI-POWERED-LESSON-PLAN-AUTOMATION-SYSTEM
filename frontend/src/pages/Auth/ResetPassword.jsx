import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { authService } from '../../services/authService';
import { BookOpen, CheckCircle } from 'lucide-react';
import './Login.css';

const ResetPassword = () => {
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [token, setToken] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    // Extract token from URL search params
    const searchParams = new URLSearchParams(location.search);
    const tokenParam = searchParams.get('token');
    
    if (tokenParam) {
      setToken(tokenParam);
    } else {
      setError("Invalid or missing reset token.");
    }
  }, [location]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    
    if (newPassword.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }

    setLoading(true);
    try {
      await authService.resetPasswordWithToken(token, newPassword);
      setSuccess(true);
    } catch (err) {
      setError(err.uiMessage || 'Failed to reset password. The link may be expired.');
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
          <p>Create a new secure password</p>
        </div>
        
        {success ? (
          <div className="text-center p-4">
            <CheckCircle size={48} className="text-success mx-auto mb-4" />
            <h3 className="mb-2">Password Reset Successful</h3>
            <p className="mb-4 text-muted">Your password has been successfully updated.</p>
            <Link to="/login" className="btn btn-primary w-100" style={{ display: 'block', textAlign: 'center' }}>
              Return to Login
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="login-form">
            <div className="form-group">
              <label>New Password</label>
              <input 
                type="password" 
                required
                placeholder="••••••••"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="form-control"
                minLength={6}
                disabled={!token}
              />
            </div>
            
            <div className="form-group">
              <label>Confirm New Password</label>
              <input 
                type="password" 
                required
                placeholder="••••••••"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="form-control"
                minLength={6}
                disabled={!token}
              />
            </div>
            
            {error && <div className="login-error">{error}</div>}
            
            <button type="submit" className="btn btn-primary login-btn" disabled={loading || !token}>
              {loading ? 'Processing...' : 'Reset Password'}
            </button>
            
            <div className="text-center mt-4" style={{ textAlign: 'center', marginTop: '1rem' }}>
              <Link to="/login" className="toggle-auth-btn" style={{ fontSize: '0.85rem' }}>
                Cancel and return to Login
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

export default ResetPassword;
