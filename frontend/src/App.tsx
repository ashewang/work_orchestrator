import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import ProjectsPage from './components/ProjectsPage';
import DashboardPage from './components/DashboardPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="projects" element={<ProjectsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
