import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import FilmsPage from './pages/FilmsPage';
import FilmDetailPage from './pages/FilmDetailPage';
import TasksPage from './pages/TasksPage';
import SettingsPage from './pages/SettingsPage';
import LibrariesPage from './pages/LibrariesPage';
import TaskLivePage from './pages/TaskLivePage';

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<FilmsPage />} />
          <Route path="/films/:id" element={<FilmDetailPage />} />
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/libraries" element={<LibrariesPage />} />
          <Route path="/tasks/:taskId/live" element={<TaskLivePage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}