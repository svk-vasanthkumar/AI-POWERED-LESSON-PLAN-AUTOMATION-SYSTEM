import React from 'react';
import { Check, X } from 'lucide-react';
import './PasswordStrength.css';

export const checkPasswordStrength = (password = '') => {
  const checks = {
    length: password.length >= 8,
    uppercase: /[A-Z]/.test(password),
    lowercase: /[a-z]/.test(password),
    number: /\d/.test(password),
    special: /[!@#$%^&*()\-_=+\[\]{}|;:,.<>?/]/.test(password),
  };

  const passedCount = Object.values(checks).filter(Boolean).length;
  const isStrong = passedCount === 5;

  let label = 'Weak';
  let colorClass = 'strength-weak';

  if (passedCount >= 5) {
    label = 'Strong';
    colorClass = 'strength-strong';
  } else if (passedCount >= 3) {
    label = 'Medium';
    colorClass = 'strength-medium';
  }

  return { checks, passedCount, isStrong, label, colorClass };
};

const PasswordStrength = ({ password = '' }) => {
  if (!password) return null;

  const { checks, passedCount, label, colorClass } = checkPasswordStrength(password);
  const percentage = (passedCount / 5) * 100;

  const rules = [
    { key: 'length', text: 'At least 8 characters' },
    { key: 'uppercase', text: 'One uppercase letter (A-Z)' },
    { key: 'lowercase', text: 'One lowercase letter (a-z)' },
    { key: 'number', text: 'One number (0-9)' },
    { key: 'special', text: 'One special character (!@#$%^&*)' },
  ];

  return (
    <div className="password-strength-container">
      <div className="strength-bar-header">
        <span className="strength-label">Strength: <strong className={colorClass}>{label}</strong></span>
      </div>
      
      <div className="strength-progress-bg">
        <div 
          className={`strength-progress-fill ${colorClass}`}
          style={{ width: `${percentage}%` }}
        ></div>
      </div>

      <ul className="strength-rules-list">
        {rules.map((rule) => {
          const satisfied = checks[rule.key];
          return (
            <li key={rule.key} className={satisfied ? 'rule-met' : 'rule-unmet'}>
              {satisfied ? <Check size={13} className="rule-icon met" /> : <span className="rule-dot" />}
              <span>{rule.text}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default PasswordStrength;
