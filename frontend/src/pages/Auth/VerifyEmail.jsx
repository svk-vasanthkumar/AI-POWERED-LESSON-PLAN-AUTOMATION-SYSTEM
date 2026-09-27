import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { authService } from '../../services/authService';
import { BookOpen, CheckCircle, XCircle, Loader, Mail } from 'lucide-react';
import './Login.css';

const VerifyEmail = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState('verifying'); // 'verifying' | 'success' | 'error'
  const [message, setMessage] = useState('');
  const [resendEmail, setResendEmail] = useState('');
  const [resendStatus, setResendStatus] = useState('');
  const [resendLoading, setResendLoading] = useState(false);

  useEffect(() => {
    const token = searchParams.get('token');
    if (!token) {
      setStatus('error');
      setMessage('No verification token found. The link may be invalid or incomplete.');
      return;
    }

    authService.verifyEmail(token)
      .then((data) => {
        setStatus('success');
        setMessage(data.message || 'Email verified successfully! You can now log in.');
      })
      .catch((err) => {
        setStatus('error');
        const detail = err.response?.data?.detail || 'This verification link has expired or is invalid.';
        setMessage(detail);
      });
  }, [searchParams]);

  const handleResend = async (e) => {
    e.preventDefault();
    if (!resendEmail) return;
    setResendLoading(true);
    setResendStatus('');
    try {
      const data = await authService.resendVerification(resendEmail);
      setResendStatus(data.message);
    } catch {
      setResendStatus('Something went wrong. Please try again.');
    } finally {
      setResendLoading(false);
    }
  };

  return (
    <div className="login-page">
      {/* Branding Panel */}
      <div className="login-brand-panel">
        <div className="login-brand-content">
          <div className="login-brand-logo">
            <div className="login-brand-logo-icon">
              <BookOpen size={22} />
            </div>
            <h2>EduAI</h2>
          </div>
          <p className="login-brand-tagline">AI-Powered Lesson Plan Automation</p>
          <p className="login-brand-sub">
            Your email verification ensures your account is secure and ready to use.
          </p>
        </div>
      </div>

      {/* Status Panel */}
      <div className="login-form-panel">
        <div className="login-form-inner">
          <div className="login-mobile-logo">
            <div className="login-mobile-logo-icon">EA</div>
            <h2>Edu<span>AI</span></h2>
          </div>

          {status === 'verifying' && (
            <div style={{ textAlign: 'center', padding: '40px 0' }}>
              <Loader size={48} style={{ color: '#4f46e5', animation: 'spin 1s linear infinite', margin: '0 auto 16px', display: 'block' }} />
              <h2 style={{ fontSize: '1.3rem', marginBottom: '8px' }}>Verifying your email…</h2>
              <p style={{ color: 'var(--text-tertiary)' }}>Please wait while we confirm your email address.</p>
            </div>
          )}

          {status === 'success' && (
            <div style={{ textAlign: 'center', padding: '40px 0' }}>
              <CheckCircle size={56} style={{ color: '#10b981', margin: '0 auto 16px', display: 'block' }} />
              <h1 style={{ fontSize: '1.4rem', marginBottom: '10px' }}>Email Verified!</h1>
              <p style={{ color: 'var(--text-secondary)', marginBottom: '28px' }}>{message}</p>
              <button className="login-submit-btn" onClick={() => navigate('/login')}>
                Continue to Sign In →
              </button>
            </div>
          )}

          {status === 'error' && (
            <div style={{ padding: '32px 0' }}>
              <div style={{ textAlign: 'center', marginBottom: '24px' }}>
                <XCircle size={56} style={{ color: '#ef4444', margin: '0 auto 16px', display: 'block' }} />
                <h1 style={{ fontSize: '1.3rem', marginBottom: '10px' }}>Verification Failed</h1>
                <p style={{ color: 'var(--text-secondary)' }}>{message}</p>
              </div>

              <div style={{ borderTop: '1px solid var(--border)', paddingTop: '24px' }}>
                <p style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, marginBottom: '12px' }}>
                  <Mail size={16} /> Resend verification email
                </p>
                <form onSubmit={handleResend}>
                  <div className="form-group">
                    <label className="form-label" htmlFor="resend-email">Your Email Address</label>
                    <input
                      id="resend-email"
                      type="email"
                      className="form-control"
                      placeholder="you@university.edu"
                      value={resendEmail}
                      onChange={(e) => setResendEmail(e.target.value)}
                      required
                    />
                  </div>
                  {resendStatus && (
                    <div className="login-message success" style={{ marginBottom: '12px' }}>{resendStatus}</div>
                  )}
                  <button type="submit" className="login-submit-btn" disabled={resendLoading}>
                    {resendLoading ? 'Sending…' : 'Resend Verification Email'}
                  </button>
                </form>
                <div style={{ marginTop: '16px', textAlign: 'center' }}>
                  <button type="button" className="toggle-auth-btn" onClick={() => navigate('/login')}>
                    ← Back to sign in
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default VerifyEmail;
