import React, { useRef, useState } from 'react';
import { UploadCloud, File, X, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import './UploadCard.css';

const UploadCard = ({ title, acceptedFormats, onUpload, isUploading, progress, status, statusMessage }) => {
  const fileInputRef = useRef(null);
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelection(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      handleFileSelection(e.target.files[0]);
    }
  };

  const handleFileSelection = (file) => {
    setSelectedFile(file);
    if (onUpload) {
      onUpload(file);
    }
  };

  const triggerUpload = () => {
    fileInputRef.current.click();
  };

  const renderStatus = () => {
    if (isUploading) {
      return (
        <div className="upload-status uploading">
          <Loader2 className="spinner" size={20} />
          <div className="status-text">
            <span>{statusMessage || 'Uploading...'}</span>
            <div className="progress-bar-container">
              <div className="progress-bar" style={{ width: `${progress || 0}%` }}></div>
            </div>
          </div>
        </div>
      );
    }
    
    if (status === 'success') {
      return (
        <div className="upload-status success">
          <CheckCircle size={20} />
          <div className="status-text">
            <span>{statusMessage || 'Upload complete'}</span>
          </div>
        </div>
      );
    }
    
    if (status === 'error') {
      return (
        <div className="upload-status error">
          <AlertCircle size={20} />
          <div className="status-text">
            <span>{statusMessage || 'Upload failed'}</span>
          </div>
          <button className="btn btn-sm btn-secondary" onClick={() => setSelectedFile(null)}>Try Again</button>
        </div>
      );
    }
    
    return null;
  };

  return (
    <div className="upload-card">
      <div className="upload-header">
        <h3 className="upload-title">{title}</h3>
        <p className="upload-subtitle">Accepted formats: {acceptedFormats}</p>
      </div>

      {!selectedFile || status === 'error' ? (
        <div 
          className={`upload-zone ${dragActive ? 'drag-active' : ''}`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={triggerUpload}
        >
          <input 
            ref={fileInputRef}
            type="file" 
            className="hidden-input" 
            accept={acceptedFormats}
            onChange={handleChange}
          />
          <UploadCloud size={40} className="upload-icon" />
          <p className="upload-prompt">
            <span className="upload-link">Click to upload</span> or drag and drop
          </p>
        </div>
      ) : (
        <div className="file-preview-card">
          <div className="file-info">
            <div className="file-icon bg-blue-light text-blue">
              <File size={24} />
            </div>
            <div className="file-details">
              <p className="file-name">{selectedFile.name}</p>
              <p className="file-size">{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</p>
            </div>
          </div>
          
          {!isUploading && status !== 'success' && (
            <button className="remove-file-btn" onClick={() => setSelectedFile(null)}>
              <X size={20} />
            </button>
          )}
        </div>
      )}

      {renderStatus()}
    </div>
  );
};

export default UploadCard;
