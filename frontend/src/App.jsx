/**
 * App.jsx — HydroTwin router root
 * ===================================
 *
 * Two surfaces, one bundle:
 *
 *   <BrowserRouter>
 *     <Routes>
 *       <Layout>                 ← municipality dashboard chrome
 *         /             → <Overview>
 *         /incidents    → <Incidents>   (read-only triage list)
 *         /sources      → <Sources>
 *       </Layout>
 *       /submit         → <Submit>      ← public citizen surface, no chrome
 *     </Routes>
 *   </BrowserRouter>
 *
 * The dashboard is for municipalities; citizens go to /submit, and what
 * they send appears on /incidents inside the dashboard.
 *
 * Environment variables required (.env.local):
 *   VITE_MAPBOX_TOKEN  – Mapbox public access token
 *   VITE_API_ENDPOINT  – API Gateway endpoint URL (the /assess route;
 *                        /status and /reports are derived from it)
 */

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout    from './components/Layout';
import Overview  from './pages/Overview';
import Incidents from './pages/Incidents';
import Sources   from './pages/Sources';
import Dams      from './pages/Dams';
import Submit    from './pages/Submit';
import NotFound  from './pages/NotFound';
import Unsubscribe from './pages/Unsubscribe';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/"          element={<Overview />}  />
          <Route path="/incidents" element={<Incidents />} />
          <Route path="/sources"   element={<Sources />}   />
          <Route path="/dams"      element={<Dams />}      />
        </Route>
        <Route path="/submit"      element={<Submit />}      />
        <Route path="/unsubscribe" element={<Unsubscribe />} />
        <Route path="*"            element={<NotFound />}    />
      </Routes>
    </BrowserRouter>
  );
}
