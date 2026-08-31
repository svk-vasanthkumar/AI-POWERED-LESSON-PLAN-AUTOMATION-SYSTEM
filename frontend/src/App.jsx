import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import Layout from './components/Layout/Layout';
import Dashboard from './pages/Dashboard/Dashboard';
import Documents from './pages/Documents/Documents';
import DocumentPreview from './pages/Documents/DocumentPreview';
import Courses from './pages/Courses/Courses';
import Faculty from './pages/Faculty/Faculty';
import LessonPlanCreator from './pages/LessonPlanCreator/LessonPlanCreator';
import LessonPlansList from './pages/LessonPlans/LessonPlansList';
import LessonPlanEditor from './pages/LessonPlans/LessonPlanEditor';
import Login from './pages/Auth/Login';
import ResetPassword from './pages/Auth/ResetPassword';
import Settings from './pages/Settings/Settings';
import Reports from './pages/Reports/Reports';

const App = () => {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/login" element={<Login />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          
          <Route element={<Layout />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/courses" element={<Courses />} />
            <Route path="/faculty" element={<Faculty />} />
            <Route path="/lesson-plans" element={<LessonPlansList />} />
            <Route path="/lesson-plans/create" element={<LessonPlanCreator />} />
            <Route path="/lesson-plans/:id" element={<LessonPlanEditor />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
          
          <Route path="/preview/:type/:id" element={<DocumentPreview />} />
        </Routes>
      </Router>
    </AuthProvider>
  );
};

export default App;
