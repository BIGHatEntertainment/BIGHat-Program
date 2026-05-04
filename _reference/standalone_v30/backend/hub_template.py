HUB_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>BIG Hat Entertainment Hub</title>
    <link href="https://cdn.jsdelivr.net/npm/lucide-static@0.344.0/font/lucide.min.css" rel="stylesheet">
    <style>
        :root { --brand-yellow: #fbdd68; --bg-dark: #000e2a; --card-glass: rgba(255, 255, 255, 0.03); }
        body { background: var(--bg-dark); color: white; font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; padding: 0; overflow-x: hidden; }
        
        .header { padding: 20px 40px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(251, 221, 104, 0.15); background: rgba(0, 14, 42, 0.8); backdrop-filter: blur(10px); position: sticky; top: 0; z-index: 100; }
        .logo-group { display: flex; align-items: center; gap: 12px; cursor: pointer; }
        .logo-img { width: 40px; }
        .logo-text { font-size: 22px; font-weight: 800; color: var(--brand-yellow); letter-spacing: -0.5px; }
        
        .nav-links { display: flex; gap: 5px; }
        .nav-link { padding: 8px 16px; border-radius: 8px; color: #8892b0; text-decoration: none; font-size: 14px; font-weight: 500; transition: all 0.2s; }
        .nav-link.active { color: var(--brand-yellow); background: rgba(251, 221, 104, 0.1); }
        
        .profile-area { display: flex; align-items: center; gap: 15px; }
        .role-badge { font-size: 10px; font-weight: 800; text-transform: uppercase; background: rgba(20, 27, 80, 0.6); border: 1px solid rgba(251, 221, 104, 0.1); padding: 4px 10px; border-radius: 20px; color: var(--brand-yellow); }
        .user-avatar { width: 32px; height: 32px; border-radius: 50%; background: var(--brand-yellow); color: var(--bg-dark); display: flex; align-items: center; justify-content: center; font-weight: 900; }

        .container { padding: 40px; max-width: 1200px; margin: 0 auto; }
        .welcome { margin-bottom: 35px; }
        .welcome h1 { font-size: 28px; margin: 0; }
        .welcome p { color: #8892b0; margin-top: 5px; font-size: 15px; }
        
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 20px; }
        .card { background: var(--card-glass); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 24px; padding: 25px; position: relative; overflow: hidden; transition: all 0.3s; cursor: pointer; }
        .card:hover { transform: translateY(-5px); background: rgba(255, 255, 255, 0.05); border-color: rgba(251, 221, 104, 0.3); }
        .card-glow { position: absolute; top: 0; right: 0; width: 150px; height: 150px; border-radius: 50%; opacity: 0.1; transform: translate(30%, -30%); }
        
        .icon-box { width: 50px; height: 50px; border-radius: 14px; display: flex; align-items: center; justify-content: center; margin-bottom: 18px; }
        .card h3 { font-size: 20px; margin: 0 0 8px 0; }
        .card p { color: #8892b0; font-size: 13.5px; line-height: 1.5; margin-bottom: 20px; }
        
        .btn { width: 100%; padding: 12px; border-radius: 10px; font-weight: 700; border: none; cursor: pointer; font-size: 14px; transition: 0.2s; }
        
        .section-title { font-size: 18px; font-weight: 700; margin: 40px 0 20px 0; display: flex; align-items: center; gap: 10px; }
        .line { height: 1px; flex: 1; background: rgba(255,255,255,0.05); }

        .resource-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 15px; }
        .res-card { background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 15px; border-radius: 15px; display: flex; align-items: center; gap: 15px; cursor: pointer; transition: 0.2s; }
        .res-card:hover { background: rgba(255,255,255,0.05); border-color: var(--brand-yellow); }
        .res-card i { color: var(--brand-yellow); }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo-group">
            <img src="/static/logo.png" class="logo-img">
            <span class="logo-text">BIG Hat Entertainment</span>
        </div>
        <div class="nav-links">
            <a href="#" class="nav-link active">Dashboard</a>
            <a href="/schedule" class="nav-link">Schedule</a>
            <a href="/admin/settings" class="nav-link">Settings</a>
            <a href="/tools" class="nav-link">Tools</a>
            <a href="/api/docs/view" class="nav-link" target="_blank">Documentation</a>
        </div>
        <div class="profile-area">
            <div id="role-display" class="role-badge">...</div>
            <div id="avatar-initial" class="user-avatar">?</div>
        </div>
    </div>

    <div class="container">
        <div class="welcome">
            <h1>Welcome back, <span id="user-name" style="color:var(--brand-yellow)">...</span></h1>
            <p id="location-display">Your All-in-1 Entertainment Hub</p>
        </div>

        <div class="grid">
            <div class="card" onclick="window.location.href='/trivia/present/demo'">
                <div class="card-glow" style="background: radial-gradient(circle, #fbdd68 0%, transparent 70%);"></div>
                <div class="icon-box" style="background: rgba(251, 221, 104, 0.1); border: 1px solid rgba(251, 221, 104, 0.2);"><i class="lucide-help-circle" style="color:#fbdd68; font-size:22px"></i></div>
                <h3>Trivia Presenter</h3>
                <button class="btn" style="background:var(--brand-yellow); color:var(--bg-dark)">Launch Presenter</button>
            </div>

            <div class="card" onclick="window.location.href='/bingo/host/demo'">
                <div class="card-glow" style="background: radial-gradient(circle, #5973F7 0%, transparent 70%);"></div>
                <div class="icon-box" style="background: rgba(89, 115, 247, 0.1); border: 1px solid rgba(89, 115, 247, 0.2);"><i class="lucide-music" style="color:#5973F7; font-size:22px"></i></div>
                <h3>Music Bingo</h3>
                <button class="btn" style="background:#5973F7; color:white;">Start Game Engine</button>
            </div>

            <div class="card" onclick="window.location.href='/tools'">
                <div class="card-glow" style="background: radial-gradient(circle, #22c55e 0%, transparent 70%);"></div>
                <div class="icon-box" style="background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.2);"><i class="lucide-zap" style="color:#22c55e; font-size:22px"></i></div>
                <h3>Proprietary Tools</h3>
                <button class="btn" style="background:#22c55e; color:white;">Open Story & Score Tool</button>
            </div>
        </div>

        <div class="section-title">
            <i class="lucide-file-text" style="color:var(--brand-yellow)"></i>
            <span>Trivia Resources</span>
            <div class="line"></div>
        </div>

        <div class="resource-grid">
            <div class="res-card" onclick="window.open('/static/resources/trivia-answer-sheet.pdf')">
                <i class="lucide-download"></i>
                <div>
                    <div style="font-weight:bold; font-size:14px">Trivia Answer Sheet</div>
                    <div style="font-size:11px; color:#8892b0">Printable 10-Question Grid</div>
                </div>
            </div>
            <div class="res-card" onclick="window.open('/static/resources/trivia-multiple-choice.pdf')">
                <i class="lucide-download"></i>
                <div>
                    <div style="font-weight:bold; font-size:14px">Multiple Choice Sheet</div>
                    <div style="font-size:11px; color:#8892b0">Standard MC Format</div>
                </div>
            </div>
            <div class="res-card" onclick="window.open('/static/resources/trivia-tie-breaker.pdf')">
                <i class="lucide-download"></i>
                <div>
                    <div style="font-weight:bold; font-size:14px">Tie Breaker Sheet</div>
                    <div style="font-size:11px; color:#8892b0">Closest Number Format</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        fetch('/api/setup/status').then(r => r.json()).then(data => {
            const config = data.config;
            if(config) {
                const master = config.users[0];
                document.getElementById('user-name').innerText = master.display_name || master.first_name;
                document.getElementById('avatar-initial').innerText = master.first_name.charAt(0);
                document.getElementById('role-display').innerText = master.role.replace('_', ' ');
                document.getElementById('location-display').innerText = config.settings.location_name + ' \u2014 ' + config.settings.city;
            }
        });
    </script>
</body>
</html>
"""
