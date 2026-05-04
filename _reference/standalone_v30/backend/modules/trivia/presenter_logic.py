TRIVIA_UI = """
<!DOCTYPE html>
<html>
<head>
    <title>BIG Hat Trivia Presenter</title>
    <link href="https://cdn.jsdelivr.net/npm/lucide-static@0.344.0/font/lucide.min.css" rel="stylesheet">
    <style>
        :root { --brand-yellow: #fbdd68; --bg-dark: #000e2a; }
        body { background: #111; color: white; font-family: 'Segoe UI', sans-serif; margin: 0; overflow: hidden; display: flex; height: 100vh; }
        
        /* Sidebar Controls */
        .sidebar { width: 300px; background: var(--bg-dark); border-right: 1px solid rgba(255,255,255,0.1); display: flex; flex-direction: column; padding: 20px; z-index: 10; }
        .sidebar h2 { color: var(--brand-yellow); font-size: 18px; margin-bottom: 20px; }
        .thumbnail-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
        .thumb { aspect-ratio: 16/9; background: #222; border: 2px solid transparent; border-radius: 8px; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 10px; color: #555; }
        .thumb.active { border-color: var(--brand-yellow); box-shadow: 0 0 15px rgba(251, 221, 104, 0.3); }
        
        /* Main Presenter Stage */
        .main-stage { flex: 1; position: relative; background: #000; display: flex; align-items: center; justify-content: center; padding: 20px; }
        .slide-container { width: 100%; aspect-ratio: 16/9; background: white; position: relative; box-shadow: 0 0 100px rgba(0,0,0,0.5); overflow: hidden; }
        .slide-element { position: absolute; display: flex; align-items: center; pointer-events: none; }
        
        /* Controls */
        .bottom-bar { position: fixed; bottom: 0; left: 300px; right: 0; height: 60px; background: rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: space-between; padding: 0 30px; border-top: 1px solid rgba(255,255,255,0.1); }
        .btn { background: var(--brand-yellow); color: var(--bg-dark); border: none; padding: 8px 20px; border-radius: 6px; font-weight: 700; cursor: pointer; }
        .btn-ghost { background: transparent; color: #8892b0; border: 1px solid rgba(255,255,255,0.1); }
    </style>
</head>
<body>
    <div class="sidebar">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:20px;">
            <img src="/static/logo.png" style="width:30px">
            <h2 style="margin:0">Host Console</h2>
        </div>
        <div class="thumbnail-list" id="thumb-list"></div>
        <div style="margin-top:20px; display:flex; flex-direction:column; gap:10px;">
            <button class="btn" style="background:#5973F7; color:white;" onclick="openAudience()">Open TV View</button>
            <button class="btn btn-ghost" onclick="window.location.href='/'">Exit Presenter</button>
        </div>
    </div>

    <div class="main-stage">
        <div class="slide-container" id="stage"></div>
        <div class="bottom-bar">
            <div style="color:#8892b0; font-size:12px;">Slide <span id="slide-num">1</span> of <span id="total-slides">?</span></div>
            <div style="display:flex; gap:10px;">
                <button class="btn btn-ghost" onclick="prev()">PREV</button>
                <button class="btn" onclick="next()">NEXT (SPACE)</button>
            </div>
            <div id="timer" style="color:var(--brand-yellow); font-weight:bold; font-family:monospace; font-size:20px;"></div>
        </div>
    </div>

    <script>
        let slides = [];
        let currentIndex = 0;
        let audienceWindow = null;

        // Fetch demo presentation
        async function load() {
            // Simulated Ported Slides from MaxEmus
            slides = [
                { background: '#000e2a', elements: [{ type: 'text', x: 200, y: 300, width: 1520, height: 400, content: 'WELCOME TO TRIVIA', fontSize: 120, color: '#fbdd68', textAlign: 'center', fontWeight: 'bold' }] },
                { background: '#000e2a', elements: [{ type: 'text', x: 100, y: 100, width: 1720, height: 200, content: 'ROUND 1', fontSize: 80, color: '#fbdd68', textAlign: 'center' }, { type: 'text', x: 200, y: 400, width: 1520, height: 300, content: 'Question 1: In what city does BIG Hat Entertainment operate?', fontSize: 60, color: 'white', textAlign: 'center' }] },
                { background: '#000e2a', elements: [{ type: 'text', x: 100, y: 100, width: 1720, height: 200, content: 'ROUND 1', fontSize: 80, color: '#fbdd68', textAlign: 'center' }, { type: 'text', x: 200, y: 400, width: 1520, height: 300, content: 'Answer: Phoenix, AZ', fontSize: 100, color: '#22c55e', textAlign: 'center', fontWeight: 'bold' }] }
            ];
            render();
            renderThumbs();
        }

        function render() {
            const stage = document.getElementById('stage');
            const slide = slides[currentIndex];
            stage.style.background = slide.background;
            stage.innerHTML = '';
            
            slide.elements.forEach(el => {
                const div = document.createElement('div');
                div.className = 'slide-element';
                div.style.left = (el.x / 1920 * 100) + '%';
                div.style.top = (el.y / 1080 * 100) + '%';
                div.style.width = (el.width / 1920 * 100) + '%';
                div.style.height = (el.height / 1080 * 100) + '%';
                div.style.fontSize = (el.fontSize / 1080 * 100) + 'vh';
                div.style.color = el.color;
                div.style.textAlign = el.textAlign;
                div.style.fontWeight = el.fontWeight || 'normal';
                div.style.justifyContent = el.textAlign === 'center' ? 'center' : 'flex-start';
                div.innerText = el.content || '';
                stage.appendChild(div);
            });

            document.getElementById('slide-num').innerText = currentIndex + 1;
            document.getElementById('total-slides').innerText = slides.length;
            
            if(audienceWindow && !audienceWindow.closed) {
                audienceWindow.postMessage({ type: 'UPDATE', slide: slide }, '*');
            }
        }

        function renderThumbs() {
            const list = document.getElementById('thumb-list');
            list.innerHTML = '';
            slides.forEach((s, i) => {
                const div = document.createElement('div');
                div.className = 'thumb' + (i === currentIndex ? ' active' : '');
                div.innerText = 'SLIDE ' + (i+1);
                div.onclick = () => { currentIndex = i; render(); renderThumbs(); };
                list.appendChild(div);
            });
        }

        function next() { if(currentIndex < slides.length - 1) { currentIndex++; render(); renderThumbs(); } }
        function prev() { if(currentIndex > 0) { currentIndex--; render(); renderThumbs(); } }

        window.onkeydown = (e) => {
            if(e.code === 'Space' || e.code === 'ArrowRight') next();
            if(e.code === 'ArrowLeft') prev();
        };

        function openAudience() {
            const left = window.screen.width;
            audienceWindow = window.open('about:blank', 'AudienceView', `width=1280,height=720,left=${left},top=0`);
            audienceWindow.document.write(`
                <html><body style="margin:0; background:black; overflow:hidden; display:flex; align-items:center; justify-content:center;">
                <div id="stage" style="width:100vw; aspect-ratio:16/9; position:relative;"></div>
                <script>
                    window.onmessage = (e) => {
                        if(e.data.type === 'UPDATE') {
                            const stage = document.getElementById('stage');
                            const slide = e.data.slide;
                            stage.style.background = slide.background;
                            stage.innerHTML = '';
                            slide.elements.forEach(el => {
                                const div = document.createElement('div');
                                div.style.position = 'absolute';
                                div.style.left = (el.x / 1920 * 100) + '%';
                                div.style.top = (el.y / 1080 * 100) + '%';
                                div.style.width = (el.width / 1920 * 100) + '%';
                                div.style.height = (el.height / 1080 * 100) + '%';
                                div.style.fontSize = (el.fontSize / 1080 * 100) + 'vh';
                                div.style.color = el.color;
                                div.style.textAlign = el.textAlign;
                                div.style.fontWeight = el.fontWeight || 'normal';
                                div.style.display = 'flex';
                                div.style.alignItems = 'center';
                                div.style.justifyContent = el.textAlign === 'center' ? 'center' : 'flex-start';
                                div.innerText = el.content || '';
                                stage.appendChild(div);
                            });
                        }
                    }
                <\/script></body></html>
            `);
            setTimeout(() => render(), 500);
        }

        load();
    </script>
</body>
</html>
"""
