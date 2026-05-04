SCHEDULER_UI_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>BIG Hat Scheduler - Enterprise</title>
    <link href="https://cdn.jsdelivr.net/npm/lucide-static@0.344.0/font/lucide.min.css" rel="stylesheet">
    <style>
        :root { --brand-pink: #ec4899; --bg-dark: #000e2a; --card-glass: rgba(255, 255, 255, 0.03); }
        body { background: var(--bg-dark); color: white; font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; padding: 0; }
        .header { padding: 20px 40px; border-bottom: 1px solid rgba(236, 72, 153, 0.15); display: flex; justify-content: space-between; align-items: center; }
        .logo { font-size: 20px; font-weight: 800; color: var(--brand-pink); display: flex; align-items: center; gap: 10px; }
        .container { padding: 40px; max-width: 1200px; margin: 0 auto; }
        
        .tabs { display: flex; gap: 20px; margin-bottom: 30px; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .tab { padding: 10px 20px; cursor: pointer; color: #8892b0; font-weight: 600; border-bottom: 2px solid transparent; }
        .tab.active { color: var(--brand-pink); border-bottom-color: var(--brand-pink); }
        
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
        .event-card { background: var(--card-glass); border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 20px; position: relative; }
        .event-type { font-size: 10px; font-weight: 800; text-transform: uppercase; background: rgba(236, 72, 153, 0.1); color: var(--brand-pink); padding: 3px 8px; border-radius: 4px; display: inline-block; margin-bottom: 10px; }
        .event-title { font-size: 18px; font-weight: 700; margin: 0 0 5px 0; }
        .event-meta { font-size: 13px; color: #8892b0; display: flex; align-items: center; gap: 5px; margin-bottom: 3px; }
        
        .btn { padding: 10px 20px; border-radius: 8px; border: none; font-weight: 700; cursor: pointer; transition: 0.2s; }
        .btn-pink { background: var(--brand-pink); color: white; }
        .btn-ghost { background: transparent; color: #8892b0; border: 1px solid rgba(255,255,255,0.1); }
        
        .sidebar-form { position: fixed; right: 0; top: 0; bottom: 0; width: 400px; background: #0a1128; border-left: 1px solid rgba(251, 221, 104, 0.1); padding: 40px; transform: translateX(100%); transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1); z-index: 1000; box-shadow: -20px 0 50px rgba(0,0,0,0.5); }
        .sidebar-form.open { transform: translateX(0); }
        input, select { width: 100%; padding: 12px; margin: 8px 0; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); color: white; border-radius: 8px; box-sizing: border-box; }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo"><img src="/static/logo.png" style="width:30px"> Event Scheduler</div>
        <button class="btn btn-ghost" onclick="window.location.href='/'">Back to Hub</button>
    </div>

    <div class="container">
        <div class="tabs">
            <div class="tab active">Upcoming Events</div>
            <div class="tab" onclick="alert('Venues and Hosts coming in next module update!')">Venues & Hosts</div>
            <div class="tab" onclick="alert('Reports coming in next module update!')">Payment Reports</div>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:30px;">
            <div>
                <h1 style="margin:0;">Event Lineup</h1>
                <p style="color:#8892b0; margin-top:5px;">Track your live shows and host assignments.</p>
            </div>
            <button class="btn btn-pink" onclick="toggleForm()">+ Create New Event</button>
        </div>

        <div class="grid" id="event-grid">
            <!-- Loading -->
        </div>
    </div>

    <!-- Create Event Sidebar -->
    <div class="sidebar-form" id="event-form">
        <h2 style="color:var(--brand-pink)">Create Event</h2>
        <p style="color:#8892b0; font-size:14px; margin-bottom:20px;">Add a new show to the proprietary local database.</p>
        
        <input type="text" id="title" placeholder="Event Title (e.g. Trivia Night)">
        <select id="type">
            <option value="Trivia">Trivia</option>
            <option value="Music Bingo">Music Bingo</option>
            <option value="Karaoke">Karaoke</option>
        </select>
        <select id="venue">
            <option value="" disabled selected>Select Venue</option>
            <option value="v1">Monkey Pants</option>
            <option value="v2">The Tap House</option>
        </select>
        <input type="datetime-local" id="date">
        
        <button class="btn btn-pink" style="width:100%; margin-top:20px;" onclick="saveEvent()">Save to Local DB</button>
        <button class="btn btn-ghost" style="width:100%; margin-top:10px;" onclick="toggleForm()">Cancel</button>
    </div>

    <script>
        function toggleForm() { document.getElementById('event-form').classList.toggle('open'); }

        async function loadEvents() {
            const r = await fetch('/api/scheduler/events');
            const events = await r.json();
            const grid = document.getElementById('event-grid');
            grid.innerHTML = '';
            
            events.forEach(e => {
                const card = document.createElement('div');
                card.className = 'event-card';
                card.innerHTML = `
                    <div class="event-type">${e.event_type}</div>
                    <h3 class="event-title">${e.title}</h3>
                    <div class="event-meta"><i class="lucide-map-pin" style="font-size:12px"></i> ${e.venue_name || 'Venue ' + e.venue_id}</div>
                    <div class="event-meta"><i class="lucide-calendar" style="font-size:12px"></i> ${new Date(e.date).toLocaleString()}</div>
                    <div style="margin-top:15px; display:flex; gap:10px;">
                        <button class="btn btn-ghost" style="flex:1; font-size:12px; padding:6px" onclick="alert('Host assignment locked to Master Admin in demo.')">Assign Host</button>
                    </div>
                `;
                grid.appendChild(card);
            });
        }

        async function saveEvent() {
            const data = {
                title: document.getElementById('title').value,
                event_type: document.getElementById('type').value,
                venue_id: document.getElementById('venue').value,
                date: document.getElementById('date').value
            };
            await fetch('/api/scheduler/events/create', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            toggleForm();
            loadEvents();
        }

        loadEvents();
    </script>
</body>
</html>
"""
