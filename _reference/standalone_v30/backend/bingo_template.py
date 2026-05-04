BINGO_UI_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>BIG Hat Music Bingo - Live Engine</title>
    <style>
        body { background: #000e2a; color: white; font-family: 'Segoe UI', sans-serif; margin: 0; padding: 40px; text-align: center; overflow: hidden; }
        .game-board { background: rgba(255,255,255,0.03); border: 2px solid #5973F7; border-radius: 30px; padding: 40px; max-width: 900px; margin: 0 auto; box-shadow: 0 0 50px rgba(89, 115, 247, 0.2); position: relative; z-index: 10; }
        h1 { color: #5973F7; font-size: 38px; margin-top: 0; font-weight: 900; }
        .current-call { font-size: 48px; font-weight: 800; margin: 30px 0; min-height: 80px; color: #fbdd68; text-shadow: 0 0 20px rgba(251, 221, 104, 0.4); }
        .grid { display: grid; grid-template-columns: repeat(15, 1fr); gap: 4px; margin-top: 20px; }
        .num { aspect-ratio: 1; display: flex; align-items: center; justify-content: center; background: rgba(255,255,255,0.05); border-radius: 6px; font-size: 11px; color: #8892b0; border: 1px solid rgba(255,255,255,0.05); }
        .num.called { background: #5973F7; color: white; font-weight: bold; box-shadow: 0 0 15px #5973F7; border-color: #5973F7; transform: scale(1.1); transition: all 0.3s; }
        .controls { margin-top: 40px; display: flex; justify-content: center; gap: 15px; }
        .btn { background: #5973F7; color: white; border: none; padding: 12px 30px; border-radius: 12px; font-weight: 800; cursor: pointer; font-size: 16px; transition: all 0.2s; }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(89, 115, 247, 0.4); }
        .btn-bingo { background: #ef4444; }
        .btn-secondary { background: rgba(255,255,255,0.1); color: #8892b0; }
        
        /* BINGO WINNER OVERLAY (Ported from MaxEmus) */
        #winner-overlay { display: none; position: fixed; inset: 0; background: black; z-index: 100; flex-direction: column; align-items: center; justify-content: center; }
        #winner-video { width: 100%; height: 100%; object-fit: cover; position: absolute; }
        .winner-content { position: relative; z-index: 110; text-align: center; background: rgba(0,0,0,0.6); backdrop-filter: blur(10px); padding: 40px 80px; border-radius: 30px; border: 2px solid #fbdd68; }
        .winner-title { font-size: 80px; font-weight: 900; color: #fbdd68; margin: 0; text-shadow: 0 0 30px #fbdd68; }
        .winner-name { font-size: 40px; font-weight: 700; color: white; margin-top: 10px; }
        #name-input-panel { margin-top: 20px; display: flex; flex-direction: column; gap: 10px; }
        input { padding: 12px; border-radius: 8px; border: none; width: 300px; font-size: 18px; text-align: center; }
    </style>
</head>
<body>
    <div class="game-board">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <h1>BIGHat MUSIC BINGO</h1>
            <div id="round-info" style="font-weight:bold; color:#8892b0">1980s HITS - ROUND 1</div>
        </div>
        
        <div class="current-call" id="call">READY TO ROCK?</div>
        
        <div class="grid" id="grid"></div>

        <div class="controls">
            <button class="btn btn-secondary" onclick="window.location.href='/'">Exit</button>
            <button class="btn btn-bingo" onclick="triggerBingo()">BINGO!</button>
            <button class="btn" onclick="callNext()">NEXT SONG</button>
        </div>
    </div>

    <!-- Ported Winner Logic -->
    <div id="winner-overlay">
        <video id="winner-video" loop>
            <source src="/static/resources/bingo-winner-80s.mp4" type="video/mp4">
        </video>
        <div class="winner-content">
            <p class="winner-title">BINGO!</p>
            <div id="winner-name-display" class="winner-name"></div>
            
            <div id="name-input-panel">
                <input type="text" id="winner-name-input" placeholder="ENTER WINNER NAME">
                <button class="btn" onclick="submitWinner()">SUBMIT NAME</button>
            </div>
            
            <button class="btn btn-secondary" id="continue-btn" style="display:none; margin-top:20px;" onclick="closeWinner()">CONTINUE ROUND</button>
        </div>
    </div>

    <script>
        // Init Grid
        const grid = document.getElementById('grid');
        for(let i=1; i<=75; i++) {
            const div = document.createElement('div');
            div.className = 'num';
            div.id = 'n'+i;
            div.innerText = i;
            grid.appendChild(div);
        }

        const songs = ["Billie Jean - Michael Jackson", "Purple Rain - Prince", "Take On Me - a-ha"];
        let index = 0;

        function callNext() {
            if(index >= songs.length) return alert('No more songs in this round!');
            document.getElementById('call').innerText = songs[index];
            const num = Math.floor(Math.random() * 75) + 1;
            document.getElementById('n'+num).classList.add('called');
            index++;
        }

        function triggerBingo() {
            const overlay = document.getElementById('winner-overlay');
            const video = document.getElementById('winner-video');
            overlay.style.display = 'flex';
            video.play();
        }

        function submitWinner() {
            const name = document.getElementById('winner-name-input').value;
            if(!name) return alert('Enter a name!');
            document.getElementById('winner-name-display').innerText = name;
            document.getElementById('name-input-panel').style.display = 'none';
            document.getElementById('continue-btn').style.display = 'block';
        }

        function closeWinner() {
            document.getElementById('winner-overlay').style.display = 'none';
            document.getElementById('winner-video').pause();
            document.getElementById('name-input-panel').style.display = 'flex';
            document.getElementById('continue-btn').style.display = 'none';
            document.getElementById('winner-name-input').value = '';
        }
    </script>
</body>
</html>
"""
