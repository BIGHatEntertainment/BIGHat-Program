TRIVIA_PRESENT_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>BIG Hat Trivia - Presentation Mode</title>
    <style>
        body { background: #000e2a; color: white; font-family: 'Segoe UI', sans-serif; margin: 0; display: flex; flex-direction: column; height: 100vh; }
        .stage { flex: 1; display: flex; align-items: center; justify-content: center; font-size: 48px; font-weight: 800; text-align: center; padding: 50px; border: 10px solid #fbdd68; margin: 20px; border-radius: 30px; background: rgba(255,255,255,0.02); }
        .controls { height: 80px; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; gap: 20px; border-top: 1px solid rgba(251, 221, 104, 0.2); }
        .btn { background: #fbdd68; color: #000e2a; border: none; padding: 10px 30px; border-radius: 8px; font-weight: 800; cursor: pointer; }
        .score-panel { position: fixed; right: 40px; top: 100px; width: 200px; background: rgba(255,255,255,0.05); padding: 20px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.1); }
    </style>
</head>
<body>
    <div class="stage" id="slide-content">
        READY TO PLAY?
    </div>
    <div class="score-panel">
        <h4 style="margin-top:0; color:#fbdd68">Leaderboard</h4>
        <div id="scores" style="font-size:14px; color:#8892b0">No teams registered.</div>
    </div>
    <div class="controls">
        <button class="btn" onclick="prev()">PREV</button>
        <button class="btn" onclick="next()">NEXT SLIDE</button>
    </div>
    <script>
        const slides = ["ROUND 1: GENERAL KNOWLEDGE", "Question 1: Who founded BIG Hat?", "Question 2: What city are we in?", "ANSWERS COMING UP..."];
        let current = -1;
        function next() {
            current = (current + 1) % slides.length;
            document.getElementById('slide-content').innerText = slides[current];
        }
    </script>
</body>
</html>
"""
