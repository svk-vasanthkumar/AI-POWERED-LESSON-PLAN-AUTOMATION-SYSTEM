import React, { useState, useEffect } from 'react';
import { BarChart3, TrendingUp, Users, BookOpen, Layers, FileText } from 'lucide-react';
import { lessonPlanService } from '../../services/lessonPlanService';
import { facultyService } from '../../services/facultyService';
import { courseService } from '../../services/courseService';
import { syllabusService } from '../../services/syllabusService';
import { reportsService } from '../../services/reportsService';
import { useAuth } from '../../context/AuthContext';
import './Reports.css';

const Reports = () => {
  const StatCard = ({ title, value, icon, color }) => (
    <div className="stat-card">
      <div className="stat-content">
        <h3 className="stat-title">{title}</h3>
        <p className="stat-value">{value}</p>
      </div>
      <div className={`stat-icon-wrapper bg-${color}-light text-${color}`}>
        {icon}
      </div>
    </div>
  );

  const [metrics, setMetrics] = useState({
    totalPlans: 0,
    activeFaculty: 0,
    totalCourses: 0,
    totalSyllabi: 0
  });
  
  const [detailedReports, setDetailedReports] = useState({
    coCoverage: null,
    courseProgress: [],
    facultyWorkload: []
  });
  
  const [loading, setLoading] = useState(true);
  const { user } = useAuth();

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        setLoading(true);
        const [plans, faculty, courses, syllabi, coData, progressData, workloadData] = await Promise.all([
          lessonPlanService.getAll().catch(() => []),
          facultyService.getAll().catch(() => []),
          courseService.getAll().catch(() => []),
          syllabusService.getAll().catch(() => []),
          reportsService.getCoCoverage().catch(() => null),
          reportsService.getCourseProgress().catch(() => []),
          reportsService.getFacultyWorkload().catch(() => [])
        ]);

        setMetrics({
          totalPlans: plans.length || 0,
          activeFaculty: faculty.length || 0,
          totalCourses: courses.length || 0,
          totalSyllabi: syllabi.length || 0
        });
        
        setDetailedReports({
          coCoverage: coData,
          courseProgress: progressData,
          facultyWorkload: workloadData
        });
      } catch (error) {
        console.error("Failed to fetch reports data:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchMetrics();
  }, []);

  const handleDownloadCSV = () => {
    const csvContent = [
      ["Metric", "Count"],
      ["Total Plans", metrics.totalPlans],
      ["Total Courses", metrics.totalCourses],
      ["Active Faculty", metrics.activeFaculty],
      ["Total Syllabi", metrics.totalSyllabi]
    ]
      .map(e => e.join(","))
      .join("\n");

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", "system_metrics_summary.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="reports-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Reports & Analytics</h1>
          <p className="page-subtitle">View department-wide lesson plan metrics and completion rates.</p>
        </div>
      </div>

      <div className="stats-grid mb-4">
        <StatCard title="Total Plans" value={loading ? "..." : metrics.totalPlans} icon={<BookOpen size={24} />} color="blue" />
        <StatCard title="Total Courses" value={loading ? "..." : metrics.totalCourses} icon={<Layers size={24} />} color="green" />
        <StatCard title="Active Faculty" value={loading ? "..." : metrics.activeFaculty} icon={<Users size={24} />} color="amber" />
        <StatCard title="Total Syllabi" value={loading ? "..." : metrics.totalSyllabi} icon={<FileText size={24} />} color="navy" />
      </div>

      <div className="reports-content">
        {loading ? (
          <div className="report-placeholder-card">
             <div className="spinner-large"></div>
             <p className="mt-4">Loading Detailed Reports...</p>
          </div>
        ) : (
          <div className="detailed-reports-grid">
            
            <div className="report-card">
              <div className="report-card-header">
                <h3>CO Coverage Analysis</h3>
                <TrendingUp size={20} className="text-secondary" />
              </div>
              <div className="report-card-body">
                {detailedReports.coCoverage ? (
                  <>
                    <div className="coverage-summary">
                      <div className="coverage-circle">
                        <span className="coverage-value">{detailedReports.coCoverage.department_average}%</span>
                        <span className="coverage-label">Dept Avg</span>
                      </div>
                    </div>
                    
                    <h4 className="section-subtitle mt-4 mb-3">Course Breakdown</h4>
                    <div className="coverage-list">
                      {detailedReports.coCoverage.course_breakdown.map((course, idx) => (
                        <div key={idx} className="coverage-item">
                          <div className="coverage-item-header">
                            <span className="course-name">{course.course_name}</span>
                            <span className="course-stats">{course.covered_cos} / {course.total_cos} COs</span>
                          </div>
                          <div className="progress-bar-container">
                            <div 
                              className={`progress-bar ${course.coverage_percentage < 50 ? 'bg-danger' : course.coverage_percentage < 80 ? 'bg-warning' : 'bg-success'}`}
                              style={{ width: `${course.coverage_percentage}%` }}
                            ></div>
                          </div>
                        </div>
                      ))}
                      {detailedReports.coCoverage.course_breakdown.length === 0 && (
                        <p className="text-secondary">No lesson plans generated yet.</p>
                      )}
                    </div>
                  </>
                ) : (
                  <p className="text-secondary">CO Coverage data unavailable.</p>
                )}
              </div>
            </div>

            <div className="report-card">
              <div className="report-card-header">
                <h3>Course Progress</h3>
                <BookOpen size={20} className="text-secondary" />
              </div>
              <div className="report-card-body">
                {detailedReports.courseProgress && detailedReports.courseProgress.length > 0 ? (
                  <div className="workload-list">
                    {detailedReports.courseProgress.map((course, idx) => (
                      <div key={idx} className="workload-item">
                        <div className="faculty-info">
                          <div>
                            <p className="faculty-name">{course.course_name}</p>
                            <p className="faculty-dept">{course.course_code} • {course.status}</p>
                          </div>
                        </div>
                        <div className="workload-stats flex-column align-items-end" style={{ width: '120px' }}>
                          <span className="text-secondary" style={{ fontSize: '12px', marginBottom: '4px' }}>
                            {course.progress_percentage}%
                          </span>
                          <div className="progress-bar-container w-100">
                            <div 
                              className={`progress-bar ${course.progress_percentage < 50 ? 'bg-danger' : course.progress_percentage < 100 ? 'bg-warning' : 'bg-success'}`}
                              style={{ width: `${course.progress_percentage}%` }}
                            ></div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-secondary">No course progress data available.</p>
                )}
              </div>
            </div>

            {(user?.role === 'admin' || user?.role === 'hod') && (
              <div className="report-card">
                <div className="report-card-header">
                  <h3>Faculty Workload</h3>
                  <Users size={20} className="text-secondary" />
                </div>
                <div className="report-card-body">
                  {detailedReports.facultyWorkload && detailedReports.facultyWorkload.length > 0 ? (
                    <div className="workload-list">
                      {detailedReports.facultyWorkload.map((faculty, idx) => (
                        <div key={idx} className="workload-item">
                          <div className="faculty-info">
                            <div>
                              <p className="faculty-name">{faculty.faculty_name}</p>
                              <p className="faculty-dept">{faculty.designation} • {faculty.department}</p>
                            </div>
                          </div>
                          <div className="workload-stats">
                            <div className="stat-badge">
                              <BookOpen size={14} />
                              <span>{faculty.course_count} Courses</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-secondary">No faculty workload data available.</p>
                  )}
                </div>
              </div>
            )}

          </div>
        )}
        
        <div className="text-center mt-4">
          <button className="btn btn-secondary" onClick={handleDownloadCSV} disabled={loading}>
            Download Summary CSV
          </button>
        </div>
      </div>
    </div>
  );
};

export default Reports;
