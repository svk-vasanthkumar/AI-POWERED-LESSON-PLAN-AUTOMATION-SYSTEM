import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarChart3, TrendingUp, Users, BookOpen, Layers, FileText, CheckCircle, Clock } from 'lucide-react';
import { lessonPlanService } from '../../services/lessonPlanService';
import { facultyService } from '../../services/facultyService';
import { courseService } from '../../services/courseService';
import { syllabusService } from '../../services/syllabusService';
import { reportsService } from '../../services/reportsService';
import { useAuth } from '../../context/AuthContext';
import './Reports.css';

const Reports = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isFaculty = user?.role === 'faculty';
  const isAdminOrHod = user?.role === 'admin' || user?.role === 'hod';

  const StatCard = ({ title, value, icon, colorClass }) => (
    <div className="stat-card">
      <div className="stat-content">
        <h3 className="stat-title">{title}</h3>
        <p className="stat-value">{value}</p>
      </div>
      <div className={`stat-icon-wrapper ${colorClass}`}>
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
    facultyWorkload: [],
    myPlans: []
  });
  
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        setLoading(true);
        
        const [plans, courses, syllabi] = await Promise.all([
          lessonPlanService.getAll().catch(() => []),
          courseService.getAll().catch(() => []),
          syllabusService.getAll().catch(() => [])
        ]);

        // Build a course lookup map by _id for O(1) enrichment
        const courseMap = {};
        courses.forEach(c => {
          const id = c._id || c.id;
          if (id) courseMap[id] = c;
        });

        // Enrich each plan with course_name + course_code
        const enrichedPlans = plans.map(plan => {
          const courseId = plan.course_id;
          const course = courseMap[courseId];
          return {
            ...plan,
            course_name: course?.course_name
              || plan.structured_plan?.course_title
              || plan.course_title
              || 'Unnamed Plan',
            course_code: course?.course_code || plan.course_code || '',
            display_status: plan.status || 'Draft',
          };
        });

        let facultyCount = 0;
        if (isAdminOrHod) {
          const faculty = await facultyService.getAll().catch(() => []);
          facultyCount = faculty.length;
        }

        setMetrics({
          totalPlans: enrichedPlans.length || 0,
          activeFaculty: facultyCount,
          totalCourses: courses.length || 0,
          totalSyllabi: syllabi.length || 0
        });

        const [coData, progressData, workloadData] = await Promise.all([
          reportsService.getCoCoverage().catch(() => null),
          reportsService.getCourseProgress().catch(() => []),
          isAdminOrHod ? reportsService.getFacultyWorkload().catch(() => []) : Promise.resolve([])
        ]);
        
        setDetailedReports({
          coCoverage: coData,
          courseProgress: progressData,
          facultyWorkload: workloadData,
          myPlans: isFaculty ? enrichedPlans : []
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
      ...(isAdminOrHod ? [["Active Faculty", metrics.activeFaculty]] : []),
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

  const getStatusBadgeClass = (status) => {
    if (!status) return 'status-badge status-draft';
    const s = status.toLowerCase();
    if (s === 'approved') return 'status-badge status-approved';
    if (s === 'needs_review' || s === 'needs-review') return 'status-badge status-needs-review';
    if (s === 'processing') return 'status-badge status-processing';
    return 'status-badge status-draft';
  };

  return (
    <div className="reports-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Reports & Analytics</h1>
          <p className="page-subtitle">
            {isFaculty
              ? 'View your lesson plans, course progress, and completion metrics.'
              : 'View department-wide lesson plan metrics and completion rates.'}
          </p>
        </div>
        <button className="btn btn-secondary" onClick={handleDownloadCSV} disabled={loading}>
          Download CSV
        </button>
      </div>

      {/* Stat Cards */}
      <div className="stats-grid mb-4">
        <StatCard
          title="Total Plans"
          value={loading ? "..." : metrics.totalPlans}
          icon={<BookOpen size={22} />}
          colorClass="bg-blue-light text-blue"
        />
        <StatCard
          title="Total Courses"
          value={loading ? "..." : metrics.totalCourses}
          icon={<Layers size={22} />}
          colorClass="bg-green-light text-green"
        />
        {isAdminOrHod && (
          <StatCard
            title="Active Faculty"
            value={loading ? "..." : metrics.activeFaculty}
            icon={<Users size={22} />}
            colorClass="bg-amber-light text-amber"
          />
        )}
        <StatCard
          title="Total Syllabi"
          value={loading ? "..." : metrics.totalSyllabi}
          icon={<FileText size={22} />}
          colorClass="bg-navy-light text-navy"
        />
      </div>

      <div className="reports-content">
        {loading ? (
          <div className="report-placeholder-card">
            <div className="spinner-large"></div>
            <p className="mt-4">Loading reports...</p>
          </div>
        ) : (
          <div className="detailed-reports-grid">

            {/* ── Faculty: My Lesson Plans ─────────────────────── */}
            {isFaculty && (
              <div className="report-card">
                <div className="report-card-header">
                  <h3>My Lesson Plans</h3>
                  <BookOpen size={18} className="text-secondary" />
                </div>
                <div className="report-card-body">
                  {detailedReports.myPlans.length > 0 ? (
                    <div className="workload-list">
                      {detailedReports.myPlans.slice(0, 8).map((plan, idx) => (
                        <div 
                          key={idx} 
                          className="workload-item" 
                          style={{ cursor: 'pointer' }}
                          onClick={() => navigate(`/lesson-plans/${plan._id}`)}
                        >
                          <div className="faculty-info">
                            <div className="faculty-avatar">
                              {plan.course_name.charAt(0).toUpperCase()}
                            </div>
                            <div>
                              <p className="faculty-name">{plan.course_name}</p>
                              <p className="faculty-dept">
                                {plan.course_code ? `${plan.course_code} • ` : ''}
                                {plan.created_at ? new Date(plan.created_at).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' }) : ''}
                              </p>
                            </div>
                          </div>
                          <span className={getStatusBadgeClass(plan.display_status)}>
                            {plan.display_status}
                          </span>
                        </div>
                      ))}
                      {detailedReports.myPlans.length > 8 && (
                        <p className="text-secondary text-center" style={{ paddingTop: 12, fontSize: 13 }}>
                          +{detailedReports.myPlans.length - 8} more plans
                        </p>
                      )}
                    </div>
                  ) : (
                    <p className="text-secondary">No lesson plans found.</p>
                  )}
                </div>
              </div>
            )}

            {/* ── CO Coverage Analysis ─────────────────────────── */}
            <div className="report-card">
              <div className="report-card-header">
                <h3>CO Coverage Analysis</h3>
                <TrendingUp size={18} className="text-secondary" />
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
                    <h4 className="section-subtitle mt-4 mb-1">Course Breakdown</h4>
                    <p className="text-secondary mb-3" style={{ fontSize: '12px' }}>
                      Coverage is calculated by matching defined Course Outcomes against the outcomes actually mapped in your lesson plan topics.
                    </p>
                    <div className="coverage-list">
                      {detailedReports.coCoverage.course_breakdown.map((course, idx) => (
                        <div key={idx} className="coverage-item">
                          <div className="coverage-item-header">
                            <span className="course-name">{course.course_name}</span>
                            <span className="course-stats">{course.covered_cos} / {course.total_cos} COs</span>
                          </div>
                          <div className="progress-bar-container mb-2">
                            <div
                              className={`progress-bar ${course.coverage_percentage < 50 ? 'bg-danger' : course.coverage_percentage < 80 ? 'bg-warning' : 'bg-success'}`}
                              style={{ width: `${course.coverage_percentage}%` }}
                            ></div>
                          </div>
                          
                          {/* Detailed CO Breakdown */}
                          {(course.covered_co_list?.length > 0 || course.missing_co_list?.length > 0) && (
                            <div className="co-details" style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', fontSize: '12px', marginTop: '8px' }}>
                              {course.covered_co_list?.map(co => (
                                <span key={`cov-${co}`} style={{ padding: '2px 8px', background: 'var(--success-light)', color: 'var(--success-text)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--success)' }}>
                                  {co} ✓
                                </span>
                              ))}
                              {course.missing_co_list?.map(co => (
                                <span key={`mis-${co}`} style={{ padding: '2px 8px', background: 'var(--error-light)', color: 'var(--error-text)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--error)' }}>
                                  {co} ✗
                                </span>
                              ))}
                            </div>
                          )}
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

            {/* ── Course Progress ───────────────────────────────── */}
            <div className="report-card">
              <div className="report-card-header">
                <h3>Course Progress</h3>
                <BookOpen size={18} className="text-secondary" />
              </div>
              <div className="report-card-body">
                {detailedReports.courseProgress && detailedReports.courseProgress.length > 0 ? (
                  <div className="workload-list">
                    {detailedReports.courseProgress.map((course, idx) => (
                      <div 
                        key={idx} 
                        className="workload-item"
                        style={{ cursor: 'pointer' }}
                        onClick={() => navigate(`/progress/${course.course_id}`)}
                      >
                        <div className="faculty-info">
                          <div>
                            <p className="faculty-name">{course.course_name}</p>
                            <p className="faculty-dept">{course.course_code} • {course.status}</p>
                          </div>
                        </div>
                        <div className="workload-stats flex-column" style={{ width: '90px' }}>
                          <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
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

            {/* ── Faculty Workload (Admin/HOD only) ─────────────── */}
            {isAdminOrHod && (
              <div className="report-card">
                <div className="report-card-header">
                  <h3>Faculty Workload</h3>
                  <Users size={18} className="text-secondary" />
                </div>
                <div className="report-card-body">
                  {detailedReports.facultyWorkload && detailedReports.facultyWorkload.length > 0 ? (
                    <div className="workload-list">
                      {detailedReports.facultyWorkload.map((faculty, idx) => (
                        <div key={idx} className="workload-item">
                          <div className="faculty-info">
                            <div className="faculty-avatar">
                              {(faculty.faculty_name || '?').charAt(0).toUpperCase()}
                            </div>
                            <div>
                              <p className="faculty-name">{faculty.faculty_name}</p>
                              <p className="faculty-dept">{faculty.designation} • {faculty.department}</p>
                            </div>
                          </div>
                          <div className="stat-badge">
                            <BookOpen size={13} />
                            <span>{faculty.course_count} Courses</span>
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
      </div>
    </div>
  );
};

export default Reports;
