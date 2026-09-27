import React, { useState, useEffect, useRef } from 'react';
import { ChevronDown, Check } from 'lucide-react';
import './CustomSelect.css';

const CustomSelect = ({ 
  children, 
  value, 
  onChange, 
  disabled = false, 
  className = '', 
  name 
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const wrapperRef = useRef(null);

  // Extract options from children (standard <option> tags)
  const options = React.Children.toArray(children).filter(
    (child) => child.type === 'option'
  ).map(child => ({
    value: child.props.value,
    label: child.props.children
  }));

  // Find the label for the currently selected value
  const selectedOption = options.find(opt => opt.value === value) || options[0];

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      // Close on scroll for mobile if it's not a bottom sheet
      window.addEventListener('scroll', handleClickOutside, { passive: true });
    }
    
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      window.removeEventListener('scroll', handleClickOutside);
    };
  }, [isOpen]);

  const handleSelect = (optionValue) => {
    if (onChange) {
      // Simulate standard event object for drop-in compatibility
      onChange({ target: { value: optionValue, name } });
    }
    setIsOpen(false);
  };

  const toggleOpen = () => {
    if (!disabled) setIsOpen(!isOpen);
  };

  return (
    <div 
      className={`custom-select-wrapper ${isOpen ? 'open' : ''}`} 
      ref={wrapperRef}
      style={{ zIndex: isOpen ? 99999 : 1 }}
    >
      <div 
        className={`custom-select-trigger ${className} ${isOpen ? 'open' : ''}`}
        onClick={toggleOpen}
        disabled={disabled}
        role="combobox"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
      >
        <span className="selected-text">{selectedOption ? selectedOption.label : '-'}</span>
        <ChevronDown className="chevron" />
      </div>

      <div className={`custom-select-menu ${isOpen ? 'open' : ''}`} role="listbox">
        {options.map((opt, idx) => (
          <div
            key={idx}
            className={`custom-select-option ${opt.value === value ? 'selected' : ''}`}
            onClick={() => handleSelect(opt.value)}
            role="option"
            aria-selected={opt.value === value}
          >
            <span>{opt.label}</span>
            {opt.value === value && <Check className="check-icon" />}
          </div>
        ))}
      </div>
    </div>
  );
};

export default CustomSelect;
