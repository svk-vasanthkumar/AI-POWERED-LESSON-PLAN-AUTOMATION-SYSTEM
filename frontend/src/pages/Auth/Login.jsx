import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { LogIn, BookOpen, Sparkles, ShieldCheck, Zap } from 'lucide-react';
import { authService } from '../../services/authService';
import PasswordStrength, { checkPasswordStrength } from '../../components/common/PasswordStrength';
import './Login.css';

const Login = () => {
  const [mode, setMode] = useState('login'); // 'login' | 'reset' | 'forgot'
  const [formData, setFormData] = useState({ email: '', password: '', newPassword: '' });
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [loading, setLoading] = useState(false);

  const { login, resetPassword, user } = useAuth();
  const navigate = useNavigate();
  const [unverifiedEmail, setUnverifiedEmail] = useState(''); // Tracks if user needs to verify
  const [resendStatus, setResendStatus] = useState('');
  const [resendLoading, setResendLoading] = useState(false);


  React.useEffect(() => {
    if (user) navigate('/dashboard', { replace: true });
  }, [user, navigate]);

  const handleChange = (e) =>
    setFormData({ ...formData, [e.target.name]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccessMsg('');

    if (mode === 'reset') {
      const { isStrong } = checkPasswordStrength(formData.newPassword);
      if (!isStrong) {
        setError('Password does not meet all strength requirements. Please fulfill all criteria below.');
        return;
      }
    }

    setLoading(true);

    try {
      if (mode === 'forgot') {
        const { authService } = await import('../../services/authService');
        const res = await authService.forgotPassword(formData.email);
        setSuccessMsg(res.message || 'Reset link sent to your email.');
      } else if (mode === 'reset') {
        await resetPassword(formData.email, formData.password, formData.newPassword);
        setMode('login');
        setFormData({ ...formData, password: '', newPassword: '' });
        setSuccessMsg('Password changed successfully. Please sign in with your new password.');
      } else {
        try {
          await login(formData.email, formData.password);
          navigate('/dashboard');
        } catch (loginErr) {
          // Check if the backend signaled that email is not verified
          const detail = loginErr.response?.data?.detail || loginErr.message || '';
          if (detail.includes('EMAIL_NOT_VERIFIED') || detail.includes('verify your email')) {
            setUnverifiedEmail(formData.email);
            setError('Please verify your email address before logging in. Check your inbox for the verification link.');
          } else {
            throw loginErr;
          }
        }
      }
    } catch (err) {
      setError(err.uiMessage || `Failed to ${mode === 'forgot' ? 'send reset link' : mode === 'reset' ? 'reset password' : 'sign in'}. Please try again.`);
    } finally {
      setLoading(false);
    }
  };



  const handleResendVerification = async () => {
    if (!unverifiedEmail) return;
    setResendLoading(true);
    setResendStatus('');
    try {
      const data = await authService.resendVerification(unverifiedEmail);
      setResendStatus(data.message);
    } catch {
      setResendStatus('Could not resend email. Please try again.');
    } finally {
      setResendLoading(false);
    }
  };

  const titles = {
    login: 'Welcome back',
    reset: 'Change password',
    forgot: 'Forgot password',
  };

  const subtitles = {
    login: 'Sign in to your academic dashboard to continue.',
    reset: 'Enter your current password and choose a new one.',
    forgot: "Enter your email and we'll send you a reset link.",
  };

  const btnLabels = {
    login: (
      <>
        <LogIn size={17} /> Sign In
      </>
    ),
    reset: 'Change Password',
    forgot: 'Send Reset Link',
  };

  return (
    <div className="login-page">
      {/* ── Branding Panel ── */}
      <div className="login-brand-panel">
        <div className="login-brand-content">
          <div className="login-brand-logo">
            <div className="login-brand-logo-icon">
              <BookOpen size={22} />
            </div>
            <h2>EduAI</h2>
          </div>

          <p className="login-brand-tagline">
            AI-Powered Lesson Plan Automation
          </p>
          <p className="login-brand-sub">
            Create structured, curriculum-aligned lesson plans in minutes.
            Let AI handle the heavy lifting so you can focus on teaching.
          </p>

          <div className="login-brand-badges">
            <span className="login-brand-badge"><Sparkles size={12} /> AI-Generated</span>
            <span className="login-brand-badge"><ShieldCheck size={12} /> Secure</span>
            <span className="login-brand-badge"><Zap size={12} /> Fast</span>
          </div>
        </div>
      </div>

      {/* ── Form Panel ── */}
      <div className="login-form-panel">
        <div className="login-form-inner">
          {/* Mobile-only logo */}
          <div className="login-mobile-logo">
            <div className="login-mobile-logo-icon">EA</div>
            <h2>Edu<span>AI</span></h2>
          </div>

          <div className="login-form-header">
            <h1 className="login-form-title">{titles[mode]}</h1>
            <p className="login-form-subtitle">{subtitles[mode]}</p>
          </div>

          <form onSubmit={handleSubmit} className="login-form">
            {/* ── Email-not-verified banner ── */}
            {unverifiedEmail && mode === 'login' && (
              <div style={{ background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.4)', borderRadius: '8px', padding: '12px 14px', marginBottom: '16px', fontSize: '0.88rem' }}>
                <p style={{ margin: '0 0 6px', fontWeight: 600, color: '#d97706' }}>📧 Email not verified</p>
                <p style={{ margin: '0 0 8px', color: 'var(--text-secondary)' }}>Check your inbox and click the verification link.</p>
                {resendStatus ? (
                  <p style={{ margin: 0, color: '#10b981', fontWeight: 500 }}>{resendStatus}</p>
                ) : (
                  <button
                    type="button"
                    style={{ background: 'none', border: 'none', color: '#4f46e5', fontWeight: 600, cursor: 'pointer', padding: 0, fontSize: '0.88rem' }}
                    onClick={handleResendVerification}
                    disabled={resendLoading}
                  >
                    {resendLoading ? 'Sending…' : 'Resend verification email →'}
                  </button>
                )}
              </div>
            )}
            <div className="form-group">
              <label className="form-label" htmlFor="login-email">Email Address</label>
              <input
                id="login-email"
                type="email"
                name="email"
                required
                placeholder="you@university.edu"
                value={formData.email}
                onChange={handleChange}
                className="form-control"
                autoComplete="email"
              />
            </div>

            {mode !== 'forgot' && (
              <div className="form-group">
                <label className="form-label" htmlFor="login-password">
                  {mode === 'reset' ? 'Current Password' : 'Password'}
                </label>
                <input
                  id="login-password"
                  type="password"
                  name="password"
                  required
                  placeholder="••••••••"
                  value={formData.password}
                  onChange={handleChange}
                  className="form-control"
                  autoComplete={mode === 'reset' ? 'current-password' : 'current-password'}
                />
              </div>
            )}

            {mode === 'reset' && (
              <div className="form-group">
                <label className="form-label" htmlFor="login-newpass">New Password</label>
                <input
                  id="login-newpass"
                  type="password"
                  name="newPassword"
                  required
                  placeholder="Min. 8 characters with upper, lower, number, special char"
                  value={formData.newPassword}
                  onChange={handleChange}
                  className="form-control"
                  minLength={8}
                  autoComplete="new-password"
                />
                <PasswordStrength password={formData.newPassword} />
              </div>
            )}

            {mode === 'login' && (
              <div className="login-forgot-row">
                <button
                  type="button"
                  className="toggle-auth-btn"
                  onClick={() => { setMode('forgot'); setError(''); setSuccessMsg(''); }}
                >
                  Forgot Password?
                </button>
              </div>
            )}

            {error && <div className="login-message error">{error}</div>}
            {successMsg && <div className="login-message success">{successMsg}</div>}

            <button
              type="submit"
              className="login-submit-btn"
              disabled={loading}
              id="login-submit"
            >
              {loading ? 'Processing…' : btnLabels[mode]}
            </button>
          </form>

          <div className="login-form-footer">

            <p>
              {mode === 'login' ? (
                <>
                  First time?{' '}
                  <button
                    type="button"
                    className="toggle-auth-btn"
                    onClick={() => { setMode('reset'); setError(''); setSuccessMsg(''); }}
                  >
                    Change temporary password
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    className="toggle-auth-btn"
                    onClick={() => { setMode('login'); setError(''); setSuccessMsg(''); }}
                  >
                    ← Back to sign in
                  </button>
                </>
              )}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
