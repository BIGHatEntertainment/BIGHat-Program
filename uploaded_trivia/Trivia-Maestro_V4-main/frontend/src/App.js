import "./App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./pages/Home";
import Editor from "./pages/Editor";
import Admin from "./pages/Admin";
import { Toaster } from "./components/ui/toaster";
import { StoryGeneratorDashboard, StoryGeneratorPage } from "./addons/story-generator";

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/editor" element={<Editor />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="/story-generator" element={<StoryGeneratorDashboard />} />
          <Route path="/story-generator/create" element={<StoryGeneratorPage />} />
          <Route path="/story-generator/create/:id" element={<StoryGeneratorPage />} />
        </Routes>
      </BrowserRouter>
      <Toaster />
    </div>
  );
}

export default App;