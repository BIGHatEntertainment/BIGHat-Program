SETTINGS_UI_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>BIG Hat - Admin Settings</title>
    <link href="https://cdn.jsdelivr.net/npm/lucide-static@0.344.0/font/lucide.min.css" rel="stylesheet">
    <style>
        :root { --brand-yellow: #fbdd68; --bg-dark: #000e2a; --card-glass: rgba(255, 255, 255, 0.03); }
        body { background: var(--bg-dark); color: white; font-family: 'Segoe UI', sans-serif; margin: 0; padding: 40px; }
        .container { max-width: 800px; margin: 0 auto; }
        .card { background: var(--card-glass); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 24px; padding: 40px; }
        h1 { color: var(--brand-yellow); margin-top: 0; }
        .setting-group { margin-bottom: 30px; padding-bottom: 20px; border-bottom: 1px solid rgba(255,255,255,0.05); }
        h3 { font-size: 18px; margin-bottom: 10px; }
        p { color: #8892b0; font-size: 14px; margin-bottom: 20px; }
        
        .source-toggle { display: flex; gap: 10px; }
        .toggle-btn { flex: 1; padding: 15px; border-radius: 12px; border: 2px solid rgba(255,255,255,0.1); background: rgba(0,0,0,0.2); color: #8892b0; cursor: pointer; font-weight: bold; transition: 0.2s; }
        .toggle-btn.active { border-color: var(--brand-yellow); color: var(--brand-yellow); background: rgba(251, 221, 104, 0.05); }
        .toggle-btn.disabled { opacity: 0.5; cursor: not-allowed; }
        
        .path-input { width: 100%; padding: 12px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); color: white; border-radius: 10px; margin-top: 10px; }
        .save-btn { background: var(--brand-yellow); color: var(--bg-dark); border: none; padding: 15px 40px; border-radius: 12px; font-weight: 800; cursor: pointer; width: 100%; margin-top: 20px; }
        .back-link { color: #8892b0; text-decoration: none; font-size: 14px; display: inline-flex; align-items: center; gap: 8px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/" class="back-link"><i class="lucide-arrow-left"></i> Back to Hub</a>
        <div class="card">
            <h1>Master Admin Settings</h1>
            <p>Configure proprietary file paths and data sources for your standalone instance.</p>

            <div class="setting-group">
                <h3>Trivia Round Source</h3>
                <p>Choose where to pull your event slides and data from.</p>
                <div class="source-toggle">
                    <button id="btn-local" class="toggle-btn" onclick="setSource('local')">
                        <i class="lucide-folder" style="display:block; margin-bottom:5px;"></i>
                        Local Storage
                    </button>
                    <button id="btn-cloud" class="toggle-btn" onclick="setSource('cloud')">
                        <i class="lucide-cloud" style="display:block; margin-bottom:5px;"></i>
                        BIG Hat Cloud
                        <div id="sub-tag" style="font-size:10px; font-weight:normal;">Subscription Required</div>
                    </button>
                </div>
            </div>

            <div class="setting-group" id="path-section">
                <h3>Local Trivia Path</h3>
                <p>Specify the folder inside C:\BIG Hat where your round PPTX files are stored.</p>
                <input type="text" id="trivia-path" class="path-input" placeholder="C:\BIG Hat\data\trivia">
            </div>

            <button class="save-btn" onclick="saveSettings()">Save Configuration</button>
        </div>
    </div>

    <script>
        let currentSource = 'local';
        let subActive = false;

        async function load() {
            const r = await fetch('/api/setup/status');
            const data = await r.json();
            const config = data.config;
            
            currentSource = config.settings.trivia_source || 'local';
            subActive = config.settings.cloud_subscription_active || false;
            
            document.getElementById('trivia-path').value = config.paths.local_trivia || 'C:\\BIG Hat\\data\\trivia';
            
            if(!subActive) {
                document.getElementById('btn-cloud').classList.add('disabled');
                document.getElementById('sub-tag').innerText = 'LOCKED - Upgrade to Sync';
                currentSource = 'local'; // Force local if no sub
            }
            
            updateUI();
        }

        function setSource(s) {
            if(s === 'cloud' && !subActive) return alert('Cloud access requires an active monthly subscription.');
            currentSource = s;
            updateUI();
        }

        function updateUI() {
            document.getElementById('btn-local').classList.toggle('active', currentSource === 'local');
            document.getElementById('btn-cloud').classList.toggle('active', currentSource === 'cloud');
            document.getElementById('path-section').style.opacity = currentSource === 'local' ? '1' : '0.5';
        }

        async function saveSettings() {
            const path = document.getElementById('trivia-path').value;
            const data = {
                settings: { trivia_source: currentSource, cloud_subscription_active: subActive },
                paths: { local_trivia: path }
            };
            await fetch('/api/admin/settings/save', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            alert('Settings Saved Successfully');
        }

        load();
    </script>
</body>
</html>
"""
