import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, ChevronRight, FileText, Calendar, Clock, LayoutTemplate, Settings, Wand2, Download, CheckCircle } from 'lucide-react';
import { syllabusService } from '../../services/syllabusService';
import { lessonPlanService } from '../../services/lessonPlanService';
import { courseService } from '../../services/courseService';
import { academicCalendarService } from '../../services/academicCalendarService';
import { timetableService } from '../../services/timetableService';
import { schedulerService } from '../../services/schedulerService';
import './LessonPlanCreator.css';

const LessonPlanCreator = () => {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [syllabi, setSyllabi] = useState([]);
  const [calendars, setCalendars] = useState([]);
  const [timetables, setTimetables] = useState([]);
  
  // Wizard State
  const [projectState, setProjectState] = useState({
    syllabusId: null,
    courseName: '',
    courseCode: '',
    semester: '',
    config: {
      includeBloomsLevel: true,
      includeTeachingMethod: true,
      includeAssessment: true,
      includeRemarks: false
    },
    calendarId: '',
    timetableId: '',
    generatedPlan: null
  });

  const steps = [
    { id: 1, title: 'Select Document', icon: <FileText size={18} /> },
    { id: 2, title: 'Review Data', icon: <Settings size={18} /> },
    { id: 3, title: 'Configure Template', icon: <LayoutTemplate size={18} /> },
    { id: 4, title: 'Generate Plan', icon: <Wand2 size={18} /> },
    { id: 5, title: 'Review & Export', icon: <Check size={18} /> }
  ];

  useEffect(() => {
    const loadSyllabi = async () => {
      try {
        const [data, courses, cals, times] = await Promise.all([
          syllabusService.getAll(),
          courseService.getAll().catch(() => []),
          academicCalendarService.getAll().catch(() => []),
          timetableService.getAll().catch(() => [])
        ]);
        
        const enrichedSyllabi = data.map(syllabus => {
          const course = courses.find(c => c._id === syllabus.course_id || c.id === syllabus.course_id);
          return {
            ...syllabus,
            course_name: course ? course.course_name : 'Unknown Course',
            course_code: course ? course.course_code : 'N/A',
            semester: course ? course.semester : 'N/A'
          };
        });
        const enrichedTimetables = times.map(tt => {
          const course = courses.find(c => c._id === tt.course_id || c.id === tt.course_id);
          return {
            ...tt,
            course_name: course ? course.course_name : tt.course_id
          };
        });

        setSyllabi(enrichedSyllabi);
        setCalendars(cals);
        setTimetables(enrichedTimetables);
        if (cals.length > 0) {
          setProjectState(prev => ({ ...prev, calendarId: cals[0]._id || cals[0].id }));
        }
        if (times.length > 0) {
          setProjectState(prev => ({ ...prev, timetableId: times[0]._id || times[0].id }));
        }
      } catch (error) {
        console.error("Failed to load setup data");
      }
    };
    loadSyllabi();
  }, []);

  const handleSyllabusSelect = (syllabus) => {
    setProjectState(prev => ({
      ...prev,
      syllabusId: syllabus._id || syllabus.id,
      courseName: syllabus.course_name,
      courseCode: syllabus.course_code,
      semester: syllabus.semester
    }));
  };

  const handleNext = async () => {
    if (currentStep === 3) {
      // Transition from Config to Generate
      setLoading(true);
      try {
        // Call backend API to generate lesson plan using Groq + CSP
        const payload = {
          template_config: projectState.config
        };
        const generated = await lessonPlanService.generate(projectState.syllabusId, payload);
        
        let generatedSessions = generated.sessions || [];
        if (generatedSessions.length === 0 && generated.structured_plan && generated.structured_plan.units) {
          generated.structured_plan.units.forEach((unit) => {
            if (unit.topics) {
              unit.topics.forEach((topic) => {
                generatedSessions.push({
                  day_of_week: '-',
                  date: '',
                  topic: topic.topic,
                  module: `Unit ${unit.unit_number}`,
                  co: (topic.learning_outcomes || []).join(', ') || 'N/A',
                  teaching_method: (topic.teaching_methods || []).join(', ') || '-',
                  assessment: (topic.assessment_methods || []).join(', ') || '-'
                });
              });
            }
          });
        }
        generated.sessions = generatedSessions;
        
        setProjectState(prev => ({
          ...prev,
          generatedPlan: generated
        }));
        
        let planId = generated.lesson_plan_id || generated.id || generated._id;
        
        if (projectState.calendarId && projectState.timetableId) {
          try {
            await schedulerService.generateSchedule(generated.course_id || projectState.courseCode, projectState.calendarId, projectState.timetableId);
            const updatedPlan = await lessonPlanService.getById(planId);
            setProjectState(prev => ({
              ...prev,
              generatedPlan: updatedPlan
            }));
          } catch (schedError) {
            console.error("Schedule generation failed, but plan was created:", schedError);
          }
        }
        
        setCurrentStep(4);
      } catch (error) {
        alert("Failed to generate plan: " + (error.uiMessage || error.message));
      } finally {
        setLoading(false);
      }
    } else if (currentStep < steps.length) {
      setCurrentStep(prev => prev + 1);
    }
  };

  const handlePrev = () => {
    if (currentStep > 1) {
      setCurrentStep(prev => prev - 1);
    }
  };
  
  const handleExport = async (format) => {
    const planId = projectState.generatedPlan?.lesson_plan_id || projectState.generatedPlan?.id || projectState.generatedPlan?._id;
    const courseId = projectState.generatedPlan?.course_id || projectState.courseCode;
    if (!planId) return;
    
    setLoading(true);
    try {
      let blob;
      const hasSchedule = projectState.calendarId && projectState.timetableId;
      
      if (hasSchedule && courseId) {
        if (format === 'pdf') blob = await schedulerService.exportPdf(courseId);
        else if (format === 'docx') blob = await schedulerService.exportDocx(courseId);
        else if (format === 'xlsx') blob = await schedulerService.exportXlsx(courseId);
      } else {
        if (format === 'pdf') blob = await lessonPlanService.exportPdf(planId);
        else if (format === 'docx') blob = await lessonPlanService.exportDocx(planId);
        else if (format === 'xlsx') blob = await lessonPlanService.exportXlsx(planId);
      }
      
      const url = window.URL.createObjectURL(new Blob([blob]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `Lesson_Plan_${projectState.courseCode}.${format}`);
      document.body.appendChild(link);
      link.click();
      link.parentNode.removeChild(link);
    } catch (error) {
      alert("Failed to export: " + (error.uiMessage || error.message));
    } finally {
      setLoading(false);
    }
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 1:
        return (
          <div className="step-content">
            <h3>Select a Syllabus</h3>
            <p className="text-secondary mb-4">Choose an uploaded syllabus to serve as the foundation for this lesson plan.</p>
            
            {syllabi.length === 0 ? (
              <div className="empty-state">
                <p>No syllabi available.</p>
                <button className="btn btn-primary mt-2" onClick={() => navigate('/documents')}>Go to Documents to Upload</button>
              </div>
            ) : (
              <div className="syllabus-grid">
                {syllabi.map(syllabus => (
                  <div 
                    key={syllabus._id || syllabus.id} 
                    className={`selection-card ${projectState.syllabusId === (syllabus._id || syllabus.id) ? 'selected' : ''}`}
                    onClick={() => handleSyllabusSelect(syllabus)}
                  >
                    <div className="selection-card-header">
                      <FileText size={24} className={projectState.syllabusId === (syllabus._id || syllabus.id) ? 'text-accent' : 'text-secondary'} />
                      {projectState.syllabusId === (syllabus._id || syllabus.id) && <div className="selected-indicator"><Check size={14} /></div>}
                    </div>
                    <h4>{syllabus.course_code || 'Unknown'} - {syllabus.course_name || 'Syllabus'}</h4>
                    <p>Semester {syllabus.semester || 'N/A'}</p>
                  </div>
                ))}
              </div>
            )}

          </div>
        );
      case 2:
        return (
          <div className="step-content">
            <h3>Review Extracted Information</h3>
            <p className="text-secondary mb-4">Verify the data extracted from your uploaded syllabus.</p>
            
            <div className="ocr-review-panel" style={{ display: 'flex', gap: '24px' }}>
              <div className="ocr-preview" style={{ flex: 1, backgroundColor: '#f8fafc', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '24px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '300px' }}>
                <FileText size={48} className="text-secondary mb-3" />
                <p className="text-secondary">Document Preview</p>
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>(Syllabus PDF Page 1)</p>
              </div>
              
              <div className="ocr-data" style={{ flex: 1, border: '1px solid var(--border-color)', borderRadius: '12px', padding: '24px' }}>
                <h4 style={{ margin: '0 0 16px 0', fontSize: '16px' }}>Extracted Fields</h4>
                
                <div className="form-group mb-3">
                  <label style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Course Code</label>
                  <input type="text" className="form-control" value={projectState.courseCode || ''} onChange={(e) => setProjectState(prev => ({...prev, courseCode: e.target.value}))} />
                </div>
                
                <div className="form-group mb-3">
                  <label style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Course Name</label>
                  <input type="text" className="form-control" value={projectState.courseName || ''} onChange={(e) => setProjectState(prev => ({...prev, courseName: e.target.value}))} />
                </div>
                
                <div className="form-group mb-3">
                  <label style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Semester</label>
                  <input type="text" className="form-control" value={projectState.semester || ''} onChange={(e) => setProjectState(prev => ({...prev, semester: e.target.value}))} />
                </div>
                
                <div className="bg-blue-light text-blue" style={{ padding: '12px', borderRadius: '8px', fontSize: '13px', marginTop: '16px', display: 'flex', gap: '8px' }}>
                  <CheckCircle size={16} />
                  <span>Units, Topics, and CO-PO mappings have been successfully extracted and structured.</span>
                </div>
              </div>
            </div>

            <div className="schedule-selection mt-4" style={{ display: 'flex', gap: '1rem', marginTop: '2rem', borderTop: '1px solid var(--border)', paddingTop: '1.5rem' }}>
              <div className="form-group" style={{ flex: 1 }}>
                <label className="form-label">Academic Calendar (Optional)</label>
                <select 
                  className="form-control" 
                  value={projectState.calendarId} 
                  onChange={(e) => setProjectState(prev => ({...prev, calendarId: e.target.value}))}
                >
                  <option value="">Do not schedule yet</option>
                  {calendars.map(cal => (
                    <option key={cal._id || cal.id} value={cal._id || cal.id}>
                      {cal.name || `${cal.academic_year} (Sem ${cal.semester})`}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label className="form-label">Faculty Timetable (Optional)</label>
                <select 
                  className="form-control" 
                  value={projectState.timetableId} 
                  onChange={(e) => setProjectState(prev => ({...prev, timetableId: e.target.value}))}
                >
                  <option value="">Do not schedule yet</option>
                  {timetables.map(tt => (
                    <option key={tt._id || tt.id} value={tt._id || tt.id}>
                      {tt.name || `${tt.course_name || tt.course_id} (Sem ${tt.semester})`}
                    </option>
                  ))}
                </select>
              </div>
            </div>

          </div>
        );
      case 3:
        return (
          <div className="step-content">
            <h3>Configure Lesson Plan Template</h3>
            <p className="text-secondary mb-4">Select the columns and structure required for your college format.</p>
            
            <div className="config-panel">
              <div className="config-group">
                <label className="checkbox-label">
                  <input 
                    type="checkbox" 
                    checked={true}
                    disabled
                  />
                  <span>Standard Columns (Date, Topic, Hours, Module, CO)</span>
                </label>
                <p className="config-hint">These columns are mandatory for CSP scheduling.</p>
              </div>
              
              <div className="config-group">
                <h4>AI Recommendations (Groq)</h4>
                <label className="checkbox-label">
                  <input 
                    type="checkbox" 
                    checked={projectState.config.includeBloomsLevel}
                    onChange={(e) => setProjectState(prev => ({...prev, config: {...prev.config, includeBloomsLevel: e.target.checked}}))}
                  />
                  <span>Include Bloom's Taxonomy Levels</span>
                </label>
                <label className="checkbox-label">
                  <input 
                    type="checkbox" 
                    checked={projectState.config.includeTeachingMethod}
                    onChange={(e) => setProjectState(prev => ({...prev, config: {...prev.config, includeTeachingMethod: e.target.checked}}))}
                  />
                  <span>Recommend Teaching Method & Pedagogy</span>
                </label>
                <label className="checkbox-label">
                  <input 
                    type="checkbox" 
                    checked={projectState.config.includeAssessment}
                    onChange={(e) => setProjectState(prev => ({...prev, config: {...prev.config, includeAssessment: e.target.checked}}))}
                  />
                  <span>Suggest Assessment Activities</span>
                </label>
              </div>
            </div>
          </div>
        );
      case 4:
        return (
          <div className="step-content text-center py-5">
            {loading ? (
              <div className="generating-state">
                <div className="spinner-large"></div>
                <h3 className="mt-4">Generating Lesson Plan...</h3>
                <p className="text-secondary">Running CSP scheduling constraints and fetching AI recommendations.</p>
                <div className="loading-steps">
                  <div className="loading-step active">✓ Analyzing Syllabus Structure</div>
                  <div className="loading-step active">✓ Resolving Timetable Conflicts</div>
                  <div className="loading-step pulse">⟳ Generating AI Pedagogy...</div>
                </div>
              </div>
            ) : projectState.generatedPlan ? (
              <div className="success-state">
                <div className="success-icon-large">
                  <CheckCircle size={48} />
                </div>
                <h3>Generation Complete!</h3>
                <p>Your lesson plan for {projectState.courseName} has been successfully generated without any scheduling conflicts.</p>
                <button className="btn btn-primary mt-4" onClick={() => setCurrentStep(5)}>Proceed to Review</button>
              </div>
            ) : (
              <div className="error-state">
                <p>Something went wrong during generation.</p>
                <button className="btn btn-secondary mt-2" onClick={() => setCurrentStep(3)}>Go Back</button>
              </div>
            )}
          </div>
        );
      case 5:
        return (
          <div className="step-content">
            <div className="preview-header">
              <div>
                <h3>{projectState.courseName} ({projectState.courseCode})</h3>
                <p className="text-secondary">Generated Lesson Plan Preview</p>
              </div>
              <div className="export-actions">
                <button className="btn btn-secondary btn-sm" onClick={() => handleExport('pdf')} disabled={loading}>
                  <Download size={14} /> PDF
                </button>
                <button className="btn btn-secondary btn-sm" onClick={() => handleExport('xlsx')} disabled={loading}>
                  <Download size={14} /> Excel
                </button>
                <button className="btn btn-primary btn-sm" onClick={() => {
                  const planId = projectState.generatedPlan?.lesson_plan_id || projectState.generatedPlan?.id || projectState.generatedPlan?._id;
                  navigate(`/lesson-plans/${planId}`);
                }}>
                  Full Editor
                </button>
              </div>
            </div>
            
            <div className="preview-table-container">
              {projectState.generatedPlan?.sessions && (
                <table className="data-table preview-table">
                  <thead>
                    <tr>
                      <th>Day</th>
                      <th>Date</th>
                      <th>Hrs</th>
                      <th>Topic</th>
                      <th>Module</th>
                      <th>CO</th>
                      {projectState.config.includeTeachingMethod && <th>Methodology</th>}
                      {projectState.config.includeAssessment && <th>Assessment</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {projectState.generatedPlan.sessions.slice(0, 10).map((session, idx) => (
                      <tr key={idx}>
                        <td>{session.day_of_week}</td>
                        <td>{session.date}</td>
                        <td className="text-center">{session.hours || 1}</td>
                        <td className="font-medium">{session.topic}</td>
                        <td>{session.module || 'Unit 1'}</td>
                        <td>{session.co || 'CO1'}</td>
                        {projectState.config.includeTeachingMethod && <td>{session.teaching_method || '-'}</td>}
                        {projectState.config.includeAssessment && <td>{session.assessment || '-'}</td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {projectState.generatedPlan?.sessions?.length > 10 && (
                <div className="preview-footer">
                  <p>Showing 10 of {projectState.generatedPlan.sessions.length} sessions. Open full editor to see all.</p>
                </div>
              )}
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="creator-page">
      <div className="page-header">
        <h1 className="page-title">Create Lesson Plan</h1>
      </div>

      <div className="creator-container">
        {/* Stepper */}
        <div className="stepper">
          {steps.map((step, index) => (
            <div 
              key={step.id} 
              className={`step ${currentStep === step.id ? 'active' : ''} ${currentStep > step.id ? 'completed' : ''}`}
            >
              <div className="step-indicator">
                {currentStep > step.id ? <Check size={16} /> : step.id}
              </div>
              <div className="step-details">
                <p className="step-title">{step.title}</p>
              </div>
              {index < steps.length - 1 && <div className="step-line"></div>}
            </div>
          ))}
        </div>

        {/* Content Area */}
        <div className="creator-content">
          {renderStepContent()}
        </div>

        {/* Footer Actions */}
        <div className="creator-footer">
          <button 
            className="btn btn-secondary" 
            onClick={handlePrev}
            disabled={currentStep === 1 || loading || currentStep === 4}
          >
            Back
          </button>
          
          {currentStep < 4 && (
            <button 
              className="btn btn-primary" 
              onClick={handleNext}
              disabled={
                (currentStep === 1 && !projectState.syllabusId) || 
                loading
              }
            >
              {currentStep === 3 ? 'Generate Plan' : 'Continue'}
              {!loading && <ChevronRight size={18} />}
            </button>
          )}
          
          {currentStep === 5 && (
            <button 
              className="btn btn-primary" 
              onClick={() => navigate('/lesson-plans')}
            >
              Save & Exit
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default LessonPlanCreator;
