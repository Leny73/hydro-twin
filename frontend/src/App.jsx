/**
 * App.jsx — HydroTwin router root
 * ===================================
 *
 * v3 dashboard chrome:
 *   <BrowserRouter>
 *     <Layout>          ← sidebar + topbar + bottom data bar
 *       <Routes>
 *         /         → <Overview>  (operational map + AlertPanel + history replay)
 *         /reports  → <Reports>   (citizen incident form + list)
 *       </Routes>
 *     </Layout>
 *   </BrowserRouter>
 *
 * Shared snapshot data (regionStatuses, last-updated, demo flag) lives in
 * Layout and reaches pages via useOutletContext(). Pages may set their own
 * topbar title/subtitle via setPageMeta().
 *
 * Environment variables required (.env.local):
 *   VITE_MAPBOX_TOKEN  – Mapbox public access token
 *   VITE_API_ENDPOINT  – API Gateway endpoint URL (the /assess route;
 *                        /status and /reports are derived from it)
 */

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout    from './components/Layout';
import Overview  from './pages/Overview';
import Reports   from './pages/Reports';
import Sources   from './pages/Sources';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/"        element={<Overview />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/sources" element={<Sources />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
