TOOLS_UI_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>BIG Hat Proprietary Tools</title>
    <link href="https://cdn.jsdelivr.net/npm/lucide-static@0.344.0/font/lucide.min.css" rel="stylesheet">
    <style>
        body { background: #000e2a; color: white; font-family: 'Segoe UI', sans-serif; margin: 0; padding: 40px; }
        .container { max-width: 1000px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 40px; }
        .tool-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 30px; }
        .tool-card { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 24px; padding: 40px; text-align: center; }
        h1 { color: #22c55e; }
        h3 { font-size: 24px; margin-bottom: 15px; }
        p { color: #8892b0; margin-bottom: 30px; }
        .btn { background: #22c55e; color: white; border: none; padding: 15px 40px; border-radius: 12px; font-weight: 800; cursor: pointer; width: 100%; }
        .back-btn { background: transparent; color: #8892b0; border: 1px solid rgba(255,255,255,0.1); padding: 10px 20px; border-radius: 8px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Proprietary Tools</h1>
            <button class="back-btn" onclick="window.location.href='/'">Back to Hub</button>
        </div>

        <div class="tool-grid">
            <!-- Story Generator -->
            <div class="tool-card">
                <i class="lucide-instagram" style="font-size:48px; color:#22c55e; margin-bottom:20px;"></i>
                <h3>Story Generator</h3>
                <p>Generate high-quality Instagram Story videos for your events with custom overlays and branding.</p>
                <button class="btn" onclick="alert('Starting FFmpeg Video Engine...')">Create Story Video</button>
            </div>

            <!-- Scoreboard -->
            <div class="tool-card">
                <i class="lucide-trophy" style="font-size:48px; color:#22c55e; margin-bottom:20px;"></i>
                <h3>Scoreboard Tool</h3>
                <p>Display live leaderboard and tournament brackets with synthwave animations.</p>
                <button class="btn" onclick="alert('Launching Live Scoreboard...')">Open Scoreboard</button>
            </div>
        </div>
    </div>
</body>
</html>
"""
