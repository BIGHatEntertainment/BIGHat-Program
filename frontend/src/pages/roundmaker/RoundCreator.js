import { useState, useRef, useEffect, useCallback } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import { ArrowLeft, Upload, Plus, Minus, Save, Download, Image as ImageIcon, Loader2, Lock, ExternalLink } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Checkbox } from "../../components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ROUND_CONFIG = {
  MC: { name: "Multiple Choice", questions: 10, hasOptions: true, color: "#22c55e", badgeClass: "badge-mc", coverMode: "fixed" },
  REG: { name: "General Round", questions: 10, hasOptions: false, color: "#ef4444", badgeClass: "badge-reg", coverMode: "sharepoint" },
  MISC: { name: "Specific / Misc", questions: 10, hasOptions: false, color: "#3b82f6", badgeClass: "badge-misc", coverMode: "upload" },
  MYS: { name: "Mystery Round", questions: 10, hasOptions: false, color: "#a855f7", badgeClass: "badge-mys", lockedQ10: true, coverMode: "fixed" },
  BIG: { name: "The BIG Question", questions: 1, hasOptions: false, color: "#facc15", badgeClass: "badge-big", isBig: true, coverMode: "fixed" },
};

function initQuestions(roundType) {
  const config = ROUND_CONFIG[roundType];
  if (!config) return [];

  if (roundType === "BIG") {
    return [{ number: 1, question: "", answer: "" }];
  }

  return Array.from({ length: config.questions }, (_, i) => ({
    number: i + 1,
    question: roundType === "MYS" && i === 9 ? "Theme?" : "",
    answer: "",
    options: config.hasOptions ? ["", "", "", ""] : undefined,
    correctOption: config.hasOptions ? -1 : undefined,
  }));
}

function initAnswers() {
  return Array.from({ length: 10 }, (_, i) => ({ number: i + 1, answer: "" }));
}

export default function RoundCreator() {
  const { roundType } = useParams();
  const [searchParams] = useSearchParams();
  const editId = searchParams.get("edit");
  const navigate = useNavigate();
  const config = ROUND_CONFIG[roundType];
  const fileInputRef = useRef(null);

  const [roundName, setRoundName] = useState("");
  const [questions, setQuestions] = useState(() => initQuestions(roundType));
  const [bigAnswers, setBigAnswers] = useState(() => initAnswers());
  const [tiebreaker, setTiebreaker] = useState({ question: "", answer: "" });
  const [coverImage, setCoverImage] = useState(null);
  const [coverPreview, setCoverPreview] = useState(null);
  const [coverFileId, setCoverFileId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [loadingEdit, setLoadingEdit] = useState(!!editId);

  // REG-specific: title images dropdown
  const [regImages, setRegImages] = useState([]);
  const [regImagesLoading, setRegImagesLoading] = useState(roundType === "REG");
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [nextNumber, setNextNumber] = useState(1);

  // Fetch REG title images or MC next name on mount
  useEffect(() => {
    if (roundType === "REG") {
      (async () => {
        try {
          const res = await axios.get(`${API}/roundmaker/reg-title-images`);
          setRegImages(res.data.images || []);
        } catch (e) {
          console.error("Failed to load REG title images", e);
          toast.error("Failed to load categories from SharePoint");
        } finally {
          setRegImagesLoading(false);
        }
      })();
    }
    if (roundType === "MC" && !editId) {
      (async () => {
        try {
          const res = await axios.get(`${API}/roundmaker/mc-next-name`);
          setRoundName(res.data.round_name);
        } catch (e) {
          console.error("Failed to get MC next name", e);
        }
      })();
    }
  }, [roundType, editId]);

  // When a REG category is selected, fetch the next number and download the image
  const handleSelectCategory = async (categoryName) => {
    const img = regImages.find((i) => i.name_no_ext === categoryName);
    if (!img) return;
    setSelectedCategory(img);
    try {
      // Get next available number (checks SharePoint for existing files)
      const numRes = await axios.get(`${API}/roundmaker/reg-next-number/${encodeURIComponent(img.name_no_ext)}`);
      const num = numRes.data.next_number;
      const autoName = numRes.data.round_name || `${img.name_no_ext}_${num}`;
      setNextNumber(num);
      setRoundName(autoName);

      // Download the image from SharePoint for PPTX generation
      const dlRes = await axios.post(`${API}/roundmaker/reg-download-title-image`, null, {
        params: { item_id: img.item_id, drive_id: img.drive_id, filename: img.name },
      });
      setCoverFileId(dlRes.data.file_id);
      // Use the backend serve endpoint for preview
      setCoverPreview(`${API}/roundmaker/uploads/${encodeURIComponent(img.name)}`);
      toast.success(`Selected: ${autoName}`);
    } catch (e) {
      console.error("Failed to setup REG category", e);
      setRoundName(`${img.name_no_ext}_1`);
    }
  };

  const loadRoundData = useCallback(async (id) => {
    try {
      const res = await axios.get(`${API}/roundmaker/rounds/${id}`);
      const data = res.data;
      setRoundName(data.name);
      if (data.tiebreaker) setTiebreaker(data.tiebreaker);
      if (data.cover_image_id) setCoverFileId(data.cover_image_id);
      if (roundType === "BIG" && data.questions?.length) {
        const answers = data.questions.map((q, i) => ({ number: i + 1, answer: q.answer || "" }));
        setBigAnswers(answers);
        if (data.questions[0]) {
          setQuestions([{ number: 1, question: data.questions[0].question, answer: "" }]);
        }
      } else if (data.questions?.length) {
        setQuestions(data.questions.map((q) => ({
          ...q,
          correctOption: q.correctOption ?? -1,
          options: q.options || (config?.hasOptions ? ["", "", "", ""] : undefined),
        })));
      }
    } catch (e) {
      toast.error("Failed to load round data");
    } finally {
      setLoadingEdit(false);
    }
  }, [roundType, config]);

  useEffect(() => {
    if (editId) loadRoundData(editId);
  }, [editId, loadRoundData]);

  if (!config) {
    return (
      <div className="min-h-screen bg-[#0f1629] flex items-center justify-center">
        <p className="text-red-400">Invalid round type</p>
      </div>
    );
  }

  const isBig = config.isBig;

  const updateQuestion = (index, field, value) => {
    setQuestions((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], [field]: value };
      return copy;
    });
  };

  const updateOption = (qIndex, optIndex, value) => {
    setQuestions((prev) => {
      const copy = [...prev];
      const opts = [...(copy[qIndex].options || [])];
      opts[optIndex] = value;
      copy[qIndex] = { ...copy[qIndex], options: opts };
      return copy;
    });
  };

  const setCorrectOption = (qIndex, optIndex) => {
    setQuestions((prev) => {
      const copy = [...prev];
      const labels = ["A", "B", "C", "D"];
      copy[qIndex] = {
        ...copy[qIndex],
        correctOption: optIndex,
        answer: `${labels[optIndex]}) ${copy[qIndex].options?.[optIndex] || ""}`,
      };
      return copy;
    });
  };

  const updateBigAnswer = (index, value) => {
    setBigAnswers((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], answer: value };
      return copy;
    });
  };

  const addBigAnswerLine = () => {
    if (bigAnswers.length >= 15) {
      toast.info("Maximum 15 answers");
      return;
    }
    setBigAnswers((prev) => [...prev, { number: prev.length + 1, answer: "" }]);
  };

  const removeBigAnswerLine = () => {
    if (bigAnswers.length <= 8) {
      toast.info("Minimum 8 answers");
      return;
    }
    setBigAnswers((prev) => prev.slice(0, -1));
  };

  const handleCoverUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setCoverImage(file);
    setCoverPreview(URL.createObjectURL(file));

    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await axios.post(`${API}/roundmaker/upload-cover`, formData);
      setCoverFileId(res.data.file_id);
      toast.success("Cover image uploaded");
    } catch (err) {
      toast.error("Failed to upload cover image");
    }
  };

  const buildPayload = () => {
    let payload;
    if (isBig) {
      const filledAnswers = bigAnswers.filter((a) => a.answer.trim());
      const questionsPayload = filledAnswers.map((a, i) => ({
        number: i + 1,
        question: questions[0]?.question || "",
        answer: a.answer,
      }));
      payload = {
        round_type: roundType,
        name: roundName,
        questions: questionsPayload,
        tiebreaker: tiebreaker.question ? tiebreaker : null,
        cover_image_id: coverFileId,
      };
    } else {
      payload = {
        round_type: roundType,
        name: roundName,
        questions: questions.map((q) => ({
          number: q.number,
          question: q.question,
          answer: q.answer,
          options: q.options || null,
          correctOption: q.correctOption ?? -1,
        })),
        cover_image_id: coverFileId,
      };
    }
    return payload;
  };

  const handleSave = async () => {
    if (!roundName.trim()) {
      toast.error("Please enter a round name");
      return;
    }
    setSaving(true);
    try {
      const payload = buildPayload();
      await axios.post(`${API}/roundmaker/rounds`, payload);
      toast.success("Round saved!");
      navigate("/roundmaker");
    } catch (err) {
      toast.error("Failed to save round");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAndGenerate = async () => {
    if (!roundName.trim()) {
      toast.error("Please enter a round name");
      return;
    }
    setGenerating(true);
    try {
      const payload = buildPayload();
      const saveRes = await axios.post(`${API}/roundmaker/rounds`, payload);
      const roundId = saveRes.data.id;
      const genRes = await axios.post(`${API}/roundmaker/rounds/${roundId}/generate`, null, {
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([genRes.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = `${roundName}.pptx`;
      link.click();
      window.URL.revokeObjectURL(url);
      toast.success("PowerPoint generated and downloaded!");
      navigate("/roundmaker");
    } catch (err) {
      toast.error("Failed to generate PowerPoint");
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveAndUpload = async () => {
    if (!roundName.trim()) {
      toast.error("Please enter a round name");
      return;
    }
    setUploading(true);
    try {
      const payload = buildPayload();
      const saveRes = await axios.post(`${API}/roundmaker/rounds`, payload);
      const roundId = saveRes.data.id;
      const uploadRes = await axios.post(`${API}/roundmaker/rounds/${roundId}/upload-sharepoint`);
      toast.success(uploadRes.data.message || "Uploaded to SharePoint!");
      navigate("/roundmaker");
    } catch (err) {
      const msg = err.response?.data?.detail || "SharePoint upload failed";
      toast.error(msg);
    } finally {
      setUploading(false);
    }
  };

  const getPlaceholder = () => {
    switch (roundType) {
      case "MC": return "e.g. MC_1-20_A";
      case "REG": return "e.g. Sports Trivia 1";
      case "MISC": return "e.g. 90s Music 2";
      case "MYS": return "e.g. MYS_Animals";
      case "BIG": return "e.g. BIG_Geography";
      default: return "Round name";
    }
  };

  return (
    <div className="min-h-screen bg-[#0f1629]">
      {/* Header */}
      <header className="backdrop-blur-md bg-slate-900/70 border-b border-white/5 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              data-testid="back-button"
              variant="ghost"
              size="sm"
              onClick={() => navigate("/roundmaker")}
              className="text-slate-400 hover:text-white hover:bg-slate-800/50"
            >
              <ArrowLeft size={18} className="mr-1" />
              Back
            </Button>
            <div className="h-6 w-px bg-slate-700" />
            <div className="flex items-center gap-3">
              <span
                className="text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full"
                style={{ backgroundColor: `${config.color}20`, color: config.color }}
              >
                {roundType}
              </span>
              <h1
                data-testid="round-type-title"
                className="text-xl font-semibold text-white"
                style={{ fontFamily: "'Space Grotesk', sans-serif" }}
              >
                {config.name}
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button
              data-testid="save-btn"
              onClick={handleSave}
              disabled={saving}
              className="bg-slate-800 text-white border border-slate-700 hover:border-teal-400 hover:text-teal-400 transition-colors duration-200"
            >
              <Save size={16} className="mr-2" />
              {saving ? "Saving..." : "Save Draft"}
            </Button>
            <Button
              data-testid="generate-btn"
              onClick={handleSaveAndGenerate}
              disabled={generating}
              className="bg-slate-800 text-teal-400 border border-slate-700 hover:border-teal-400 
                transition-colors duration-200"
            >
              <Download size={16} className="mr-2" />
              {generating ? "Generating..." : "Download PPTX"}
            </Button>
            <Button
              data-testid="upload-sharepoint-btn"
              onClick={handleSaveAndUpload}
              disabled={uploading}
              className="bg-yellow-400 text-slate-900 hover:bg-yellow-300 font-bold uppercase tracking-wide
                shadow-lg shadow-yellow-400/20 active:scale-95 transition-transform transition-shadow duration-200"
            >
              {uploading ? (
                <Loader2 size={16} className="mr-2 animate-spin" />
              ) : (
                <Upload size={16} className="mr-2" />
              )}
              {uploading ? "Uploading..." : "Save to SharePoint"}
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {loadingEdit ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 size={32} className="animate-spin text-teal-400" />
            <span className="ml-3 text-slate-400">Loading round data...</span>
          </div>
        ) : (
        <>
        {/* Round Name & Cover Image */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 mb-10 animate-fade-in">
          {/* Name */}
          <div className={roundType === "REG" ? "lg:col-span-7" : "lg:col-span-7"}>
            {roundType === "REG" ? (
              <>
                <Label className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-2 block">
                  Round Category
                </Label>
                <Select
                  value={selectedCategory?.name_no_ext || ""}
                  onValueChange={handleSelectCategory}
                  disabled={regImagesLoading}
                >
                  <SelectTrigger
                    data-testid="reg-category-dropdown"
                    className="w-full bg-slate-900/50 border-slate-700 text-white h-12 text-lg
                      hover:border-red-400 focus:border-red-400 focus:ring-1 focus:ring-red-400 transition-colors duration-200"
                  >
                    <SelectValue placeholder={regImagesLoading ? "Loading categories..." : "Select a category..."} />
                  </SelectTrigger>
                  <SelectContent
                    data-testid="reg-category-list"
                    className="bg-slate-800 border-slate-700 max-h-64"
                  >
                    {regImages.map((img) => (
                      <SelectItem
                        key={img.item_id}
                        value={img.name_no_ext}
                        data-testid={`reg-category-option-${img.name_no_ext}`}
                        className="text-slate-300 focus:bg-slate-700/50 focus:text-red-400 cursor-pointer"
                      >
                        {img.name_no_ext}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <div className="mt-3 flex items-center gap-3">
                  <Label className="text-sm font-semibold uppercase tracking-wider text-slate-400">
                    Round Name
                  </Label>
                  <div
                    data-testid="reg-round-name-display"
                    className="bg-slate-800/60 border border-slate-700/50 rounded-lg px-4 py-2 text-white text-lg flex-1"
                  >
                    {roundName || <span className="text-slate-500">Select a category above</span>}
                  </div>
                </div>
              </>
            ) : roundType === "MC" ? (
              <>
                <Label className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-2 block">
                  Round Name
                </Label>
                <div
                  data-testid="mc-round-name-display"
                  className="bg-slate-900/50 border border-slate-700 rounded-md px-4 h-12 flex items-center text-white text-lg"
                >
                  {roundName || <span className="text-slate-500">Loading from SharePoint...</span>}
                </div>
                <p className="text-slate-600 text-xs mt-2">
                  Auto-assigned: MC_[01-20]_[Letter]. Every 20 rounds starts a new letter.
                </p>
              </>
            ) : (
              <>
                <Label className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-2 block">
                  Round Name
                </Label>
                <Input
                  data-testid="round-name-input"
                  value={roundName}
                  onChange={(e) => setRoundName(e.target.value)}
                  placeholder={getPlaceholder()}
                  className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500
                    focus:border-yellow-400 focus:ring-1 focus:ring-yellow-400 transition-colors duration-200 text-lg h-12"
                />
                <p className="text-slate-600 text-xs mt-2">
                  {roundType === "MISC" && "Format: [Name] [Number if sequel] (e.g. 90s Music 2)"}
                  {roundType === "MYS" && "Format: MYS_[Name] (e.g. MYS_Animals)"}
                  {roundType === "BIG" && "Format: BIG_[Name] (e.g. BIG_Geography)"}
                </p>
              </>
            )}
          </div>

          {/* Cover Image */}
          <div className="lg:col-span-5">
            {roundType === "REG" ? (
              <div>
                <Label className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-2 block">
                  Title Image
                </Label>
                {coverPreview ? (
                  <div
                    data-testid="reg-title-preview"
                    className="w-full max-h-48 rounded-xl overflow-hidden border border-slate-700"
                  >
                    <img src={coverPreview} alt="Title" className="w-full h-48 object-cover rounded-xl" />
                  </div>
                ) : (
                  <div
                    data-testid="reg-title-placeholder"
                    className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-6 flex flex-col items-center justify-center h-48"
                  >
                    <ImageIcon size={32} className="text-slate-600 mb-2" />
                    <p className="text-slate-500 text-sm text-center">Select a category to preview title image</p>
                  </div>
                )}
              </div>
            ) : config.coverMode === "upload" ? (
              <>
                <Label className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-2 block">
                  Cover Image (9:16)
                </Label>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleCoverUpload}
                  className="hidden"
                />
                {coverPreview ? (
                  <div
                    data-testid="cover-preview"
                    className="relative w-full aspect-[9/16] max-h-48 rounded-xl overflow-hidden border border-slate-700 cursor-pointer"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <img src={coverPreview} alt="Cover" className="w-full h-full object-cover" />
                    <div className="absolute inset-0 bg-black/40 flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity duration-200">
                      <Upload size={24} className="text-white" />
                    </div>
                  </div>
                ) : (
                  <div
                    data-testid="cover-upload-zone"
                    className="cover-upload-zone rounded-xl p-8 flex flex-col items-center justify-center cursor-pointer aspect-[9/16] max-h-48"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <ImageIcon size={32} className="text-slate-600 mb-2" />
                    <p className="text-slate-500 text-sm">Click to upload cover image</p>
                    <p className="text-slate-600 text-xs mt-1">9:16 portrait recommended</p>
                  </div>
                )}
              </>
            ) : config.coverMode === "fixed" ? (
              <div>
                <Label className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-2 block">
                  Title Image
                </Label>
                <div
                  data-testid="cover-fixed-preview"
                  className="w-full rounded-xl overflow-hidden border border-slate-700"
                >
                  <img 
                    src={`${API}/roundmaker/title-cards/${roundType}`} 
                    alt={`${roundType} Title Card`} 
                    className="w-full h-48 object-cover rounded-xl"
                    onError={(e) => { e.target.style.display = 'none'; }}
                  />
                </div>
              </div>
            ) : null}
          </div>
        </div>

        {/* Questions Section */}
        {isBig ? (
          <BigQuestionForm
            question={questions[0]}
            onQuestionChange={(val) => updateQuestion(0, "question", val)}
            answers={bigAnswers}
            onAnswerChange={updateBigAnswer}
            onAddAnswer={addBigAnswerLine}
            onRemoveAnswer={removeBigAnswerLine}
            tiebreaker={tiebreaker}
            onTiebreakerChange={setTiebreaker}
            config={config}
          />
        ) : roundType === "MC" ? (
          <MCForm
            questions={questions}
            onQuestionChange={updateQuestion}
            onOptionChange={updateOption}
            onSetCorrectOption={setCorrectOption}
            config={config}
          />
        ) : (
          <StandardForm
            questions={questions}
            onQuestionChange={updateQuestion}
            roundType={roundType}
            config={config}
          />
        )}
        </>
        )}
      </main>
    </div>
  );
}

/* ── MC Form ── */
function MCForm({ questions, onQuestionChange, onOptionChange, onSetCorrectOption, config }) {
  return (
    <div className="space-y-4 animate-slide-up">
      <h2 className="text-2xl font-medium text-teal-400 mb-6" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
        Questions & Options
      </h2>
      {questions.map((q, idx) => (
        <div
          key={idx}
          data-testid={`question-row-${idx + 1}`}
          className="question-row bg-slate-800/40 border border-slate-700/50 rounded-xl p-5"
        >
          <div className="flex items-center gap-3 mb-3">
            <span
              className="text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded-full"
              style={{ backgroundColor: `${config.color}20`, color: config.color }}
            >
              Q{q.number}
            </span>
            {q.correctOption >= 0 && (
              <span className="text-xs text-green-400 bg-green-400/10 px-2 py-0.5 rounded-full">
                Answer: {["A", "B", "C", "D"][q.correctOption]})
              </span>
            )}
          </div>
          <Input
            data-testid={`question-input-${idx + 1}`}
            value={q.question}
            onChange={(e) => onQuestionChange(idx, "question", e.target.value)}
            placeholder={`Question ${q.number}...`}
            className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500
              focus:border-yellow-400 focus:ring-1 focus:ring-yellow-400 transition-colors duration-200 mb-3"
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {["A", "B", "C", "D"].map((label, oIdx) => {
              const isCorrect = q.correctOption === oIdx;
              return (
                <div
                  key={label}
                  className={`flex items-center gap-2 rounded-lg px-2 py-1.5 transition-colors duration-200 ${
                    isCorrect ? "bg-green-500/10 border border-green-500/30" : ""
                  }`}
                >
                  <Checkbox
                    data-testid={`correct-${idx + 1}-${label.toLowerCase()}`}
                    checked={isCorrect}
                    onCheckedChange={() => onSetCorrectOption(idx, oIdx)}
                    className="border-slate-600 data-[state=checked]:bg-green-500 data-[state=checked]:border-green-500"
                  />
                  <span className={`text-sm font-bold w-6 ${isCorrect ? "text-green-400" : "text-teal-400"}`}>
                    {label})
                  </span>
                  <Input
                    data-testid={`option-${idx + 1}-${label.toLowerCase()}`}
                    value={q.options?.[oIdx] || ""}
                    onChange={(e) => onOptionChange(idx, oIdx, e.target.value)}
                    placeholder={`Option ${label}`}
                    className={`bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500
                      focus:border-teal-400 focus:ring-1 focus:ring-teal-400 transition-colors duration-200 text-sm ${
                      isCorrect ? "border-green-500/50" : ""
                    }`}
                  />
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── Standard Form (REG, MISC, MYS) ── */
function StandardForm({ questions, onQuestionChange, roundType, config }) {
  return (
    <div className="space-y-3 animate-slide-up">
      <h2 className="text-2xl font-medium text-teal-400 mb-6" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
        Questions & Answers
      </h2>
      {questions.map((q, idx) => {
        const isLockedTheme = roundType === "MYS" && idx === 9;
        return (
          <div
            key={idx}
            data-testid={`question-row-${idx + 1}`}
            className="question-row bg-slate-800/40 border border-slate-700/50 rounded-xl p-5"
          >
            <div className="flex items-center gap-3 mb-3">
              <span
                className="text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded-full"
                style={{ backgroundColor: `${config.color}20`, color: config.color }}
              >
                Q{q.number}
              </span>
              {isLockedTheme && (
                <span className="text-xs text-purple-400 bg-purple-400/10 px-2 py-0.5 rounded-full">
                  Locked
                </span>
              )}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Label className="text-slate-500 text-xs mb-1 block">Question</Label>
                <Input
                  data-testid={`question-input-${idx + 1}`}
                  value={q.question}
                  onChange={(e) => onQuestionChange(idx, "question", e.target.value)}
                  placeholder={isLockedTheme ? "Theme?" : `Question ${q.number}...`}
                  disabled={isLockedTheme}
                  className={`bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500
                    focus:border-yellow-400 focus:ring-1 focus:ring-yellow-400 transition-colors duration-200
                    ${isLockedTheme ? "opacity-60 cursor-not-allowed" : ""}`}
                />
              </div>
              <div>
                <Label className="text-slate-500 text-xs mb-1 block">Answer</Label>
                <Input
                  data-testid={`answer-input-${idx + 1}`}
                  value={q.answer}
                  onChange={(e) => onQuestionChange(idx, "answer", e.target.value)}
                  placeholder={isLockedTheme ? "The theme is..." : `Answer ${q.number}...`}
                  className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500
                    focus:border-yellow-400 focus:ring-1 focus:ring-yellow-400 transition-colors duration-200"
                />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ── BIG Question Form ── */
function BigQuestionForm({ question, onQuestionChange, answers, onAnswerChange, onAddAnswer, onRemoveAnswer, tiebreaker, onTiebreakerChange, config }) {
  return (
    <div className="space-y-8 animate-slide-up">
      {/* The Big Question */}
      <div>
        <h2 className="text-2xl font-medium text-teal-400 mb-4" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
          The BIG Question
        </h2>
        <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-6">
          <Label className="text-slate-400 text-xs uppercase tracking-wider mb-2 block">Your Question</Label>
          <Input
            data-testid="big-question-input"
            value={question?.question || ""}
            onChange={(e) => onQuestionChange(e.target.value)}
            placeholder="Enter the BIG question..."
            className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500
              focus:border-yellow-400 focus:ring-1 focus:ring-yellow-400 transition-colors duration-200 text-lg h-12"
          />
        </div>
      </div>

      {/* Answers */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-medium text-teal-400" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            Answers ({answers.filter((a) => a.answer.trim()).length}/{answers.length})
          </h2>
          <div className="flex items-center gap-2">
            <Button
              data-testid="remove-answer-btn"
              variant="ghost"
              size="sm"
              onClick={onRemoveAnswer}
              disabled={answers.length <= 8}
              className="text-slate-400 hover:text-red-400 hover:bg-red-400/10 disabled:opacity-30"
            >
              <Minus size={16} className="mr-1" />
              Remove
            </Button>
            <Button
              data-testid="add-answer-btn"
              variant="ghost"
              size="sm"
              onClick={onAddAnswer}
              disabled={answers.length >= 15}
              className="text-teal-400 hover:text-teal-300 hover:bg-teal-400/10 disabled:opacity-30"
            >
              <Plus size={16} className="mr-1" />
              Add Answer
            </Button>
          </div>
        </div>
        <div className="space-y-2">
          {answers.map((a, idx) => (
            <div
              key={idx}
              data-testid={`big-answer-row-${idx + 1}`}
              className="question-row flex items-center gap-3 bg-slate-800/40 border border-slate-700/50 rounded-lg px-4 py-3"
            >
              <span
                className="text-xs font-bold w-6 text-center rounded-full py-0.5"
                style={{ color: config.color }}
              >
                {idx + 1}
              </span>
              <Input
                data-testid={`big-answer-input-${idx + 1}`}
                value={a.answer}
                onChange={(e) => onAnswerChange(idx, e.target.value)}
                placeholder={`Answer ${idx + 1}...`}
                className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500
                  focus:border-yellow-400 focus:ring-1 focus:ring-yellow-400 transition-colors duration-200 flex-1"
              />
            </div>
          ))}
        </div>
      </div>

      {/* Tiebreaker */}
      <div>
        <h2 className="text-2xl font-medium text-teal-400 mb-4" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
          Tiebreaker
        </h2>
        <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-6 space-y-4">
          <div>
            <Label className="text-slate-400 text-xs uppercase tracking-wider mb-2 block">Tiebreaker Question</Label>
            <Input
              data-testid="tiebreaker-question-input"
              value={tiebreaker.question}
              onChange={(e) => onTiebreakerChange({ ...tiebreaker, question: e.target.value })}
              placeholder="Enter tiebreaker question..."
              className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500
                focus:border-yellow-400 focus:ring-1 focus:ring-yellow-400 transition-colors duration-200"
            />
          </div>
          <div>
            <Label className="text-slate-400 text-xs uppercase tracking-wider mb-2 block">Tiebreaker Answer</Label>
            <Input
              data-testid="tiebreaker-answer-input"
              value={tiebreaker.answer}
              onChange={(e) => onTiebreakerChange({ ...tiebreaker, answer: e.target.value })}
              placeholder="Enter tiebreaker answer..."
              className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500
                focus:border-yellow-400 focus:ring-1 focus:ring-yellow-400 transition-colors duration-200"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
