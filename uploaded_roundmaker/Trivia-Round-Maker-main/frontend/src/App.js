import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import Dashboard from "@/pages/Dashboard";
import RoundCreator from "@/pages/RoundCreator";

function App() {
  return (
    <div className="min-h-screen bg-[#0f1629]">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/create/:roundType" element={<RoundCreator />} />
        </Routes>
      </BrowserRouter>
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: '#1e293b',
            border: '1px solid #334155',
            color: '#f8fafc',
          },
        }}
      />
    </div>
  );
}

export default App;
