import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "./components/ui/sonner";
import Lobby from "./pages/Lobby";
import HostDashboard from "./pages/HostDashboard";
import AudienceView from "./pages/AudienceView";
import "@/App.css";

function App() {
  return (
    <div className="App min-h-screen bg-background">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Lobby />} />
          <Route path="/host" element={<HostDashboard />} />
          <Route path="/audience" element={<AudienceView />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-center" richColors />
    </div>
  );
}

export default App;
