"""
Email notification module for BIG Hat Entertainment scheduling app.
- Friday: Email primaries with their venue's upcoming week report.
- Monday: Email secondaries with available hosting spots for the week.
"""
import asyncio
import os
import logging
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path
from dotenv import load_dotenv
import resend

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logger = logging.getLogger("notifications")

resend.api_key = os.environ.get('RESEND_API_KEY', '')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'Notifications@bighat.live')

mongo_url = os.environ['MONGO_URL']
_client = AsyncIOMotorClient(mongo_url)
_db = _client[os.environ['DB_NAME']]


def _get_following_week_range():
    """Get Monday-Sunday of the following week."""
    today = datetime.now(timezone.utc).date()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)
    next_sunday = next_monday + timedelta(days=6)
    return next_monday, next_sunday


def _get_current_week_range():
    """Get Monday-Sunday of the current week."""
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _map_event_type_to_category(event_type: str) -> str:
    if event_type == 'Trivia':
        return 'trivia'
    if event_type in ('Music Bingo', 'Karaoke'):
        return 'bingo_karaoke'
    return ''


def _send_email(to: str, subject: str, html: str):
    """Send email via Resend (sync call, use in thread)."""
    params = {
        "from": SENDER_EMAIL,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    return resend.Emails.send(params)


# ===================== PRIMARY FRIDAY REPORT =====================

async def send_primary_friday_reports():
    """
    Send each primary host a report of their venue's events for the following week.
    Shows: event date/time, type, status (claimed by you / unclaimed / blackout).
    """
    logger.info("=== Sending Friday Primary Reports ===")
    next_mon, next_sun = _get_following_week_range()
    next_mon_iso = datetime(next_mon.year, next_mon.month, next_mon.day, tzinfo=timezone.utc).isoformat()
    next_sun_end = datetime(next_sun.year, next_sun.month, next_sun.day, 23, 59, 59, tzinfo=timezone.utc).isoformat()

    # Load all data
    primary_roles = await _db.venue_roles.find({"role_type": "primary"}, {"_id": 0}).to_list(500)
    if not primary_roles:
        logger.info("No primary roles found, skipping.")
        return {"sent": 0, "errors": []}

    all_employees = {e['id']: e for e in await _db.employees.find({}, {"_id": 0}).to_list(500)}
    all_venues = {v['id']: v for v in await _db.venues.find({}, {"_id": 0}).to_list(200)}
    all_events = await _db.events.find({
        "date": {"$gte": next_mon_iso, "$lte": next_sun_end}
    }, {"_id": 0}).to_list(2000)
    all_blackouts = await _db.blackout_dates.find({}, {"_id": 0}).to_list(1000)

    # Group roles by employee
    from collections import defaultdict
    emp_roles = defaultdict(list)
    for role in primary_roles:
        emp_roles[role['employee_id']].append(role)

    sent_count = 0
    errors = []

    for emp_id, roles in emp_roles.items():
        emp = all_employees.get(emp_id)
        if not emp or not emp.get('email'):
            continue

        # Build report for this primary
        venue_sections = []
        for role in roles:
            venue = all_venues.get(role['venue_id'])
            if not venue:
                continue
            venue_name = venue['name']
            category = role['role_category']
            cat_label = 'Trivia' if category == 'trivia' else 'Bingo/Karaoke'

            # Filter events for this venue + category
            venue_events = []
            for ev in all_events:
                if ev['venue_id'] != role['venue_id']:
                    continue
                ev_cat = _map_event_type_to_category(ev.get('event_type', ''))
                if ev_cat != category:
                    continue
                venue_events.append(ev)

            if not venue_events:
                venue_sections.append({
                    "venue_name": venue_name,
                    "cat_label": cat_label,
                    "events": [],
                })
                continue

            event_rows = []
            for ev in sorted(venue_events, key=lambda x: x['date']):
                ev_date = datetime.fromisoformat(ev['date']) if isinstance(ev['date'], str) else ev['date']
                ev_date_str = ev_date.strftime('%Y-%m-%d')
                day_str = ev_date.strftime('%A, %b %d')
                time_str = ev_date.strftime('%I:%M %p')

                # Determine status
                if ev.get('claimed_by') == emp_id:
                    status = '<span style="color:#16a34a;font-weight:bold;">Claimed by you</span>'
                elif ev.get('claimed_by'):
                    claimer = all_employees.get(ev['claimed_by'], {}).get('name', 'Someone')
                    status = f'<span style="color:#6b7280;">Claimed by {claimer}</span>'
                else:
                    # Check blackout
                    has_blackout = any(
                        b['employee_id'] == emp_id
                        and b['start_date'] <= ev_date_str <= b['end_date']
                        for b in all_blackouts
                    )
                    if has_blackout:
                        status = '<span style="color:#dc2626;font-weight:bold;">You have a blackout</span>'
                    else:
                        status = '<span style="color:#d97706;font-weight:bold;">Unclaimed — needs your attention</span>'

                event_rows.append({
                    "day": day_str,
                    "time": time_str,
                    "type": ev['event_type'],
                    "status": status,
                })

            venue_sections.append({
                "venue_name": venue_name,
                "cat_label": cat_label,
                "events": event_rows,
            })

        if not venue_sections:
            continue

        # Build HTML
        html = _build_primary_email_html(emp['name'], next_mon, next_sun, venue_sections)
        subject = f"BIG Hat — Your Venue Report for {next_mon.strftime('%b %d')}–{next_sun.strftime('%b %d')}"

        try:
            await asyncio.to_thread(_send_email, emp['email'], subject, html)
            sent_count += 1
            logger.info(f"Primary report sent to {emp['name']} ({emp['email']})")
            await asyncio.sleep(0.6)  # Rate limit: max 2 req/sec
        except Exception as e:
            logger.error(f"Failed to send to {emp['email']}: {e}")
            errors.append({"email": emp['email'], "error": str(e)})

    logger.info(f"Friday primary reports: {sent_count} sent, {len(errors)} errors")
    return {"sent": sent_count, "errors": errors}


def _build_primary_email_html(name, week_start, week_end, venue_sections):
    venue_html = ""
    for vs in venue_sections:
        if not vs['events']:
            venue_html += f"""
            <div style="margin-bottom:24px;padding:16px;background:#f9fafb;border-radius:8px;border:1px solid #e5e7eb;">
              <h3 style="margin:0 0 8px 0;color:#1f2937;">{vs['venue_name']} — {vs['cat_label']}</h3>
              <p style="color:#9ca3af;margin:0;">No events scheduled this week.</p>
            </div>"""
        else:
            rows = ""
            for ev in vs['events']:
                rows += f"""<tr>
                  <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;">{ev['day']}</td>
                  <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;">{ev['time']}</td>
                  <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;">{ev['type']}</td>
                  <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;">{ev['status']}</td>
                </tr>"""
            venue_html += f"""
            <div style="margin-bottom:24px;padding:16px;background:#f9fafb;border-radius:8px;border:1px solid #e5e7eb;">
              <h3 style="margin:0 0 12px 0;color:#1f2937;">{vs['venue_name']} — {vs['cat_label']}</h3>
              <table style="width:100%;border-collapse:collapse;font-size:14px;">
                <thead><tr style="background:#e5e7eb;">
                  <th style="padding:8px 12px;text-align:left;">Day</th>
                  <th style="padding:8px 12px;text-align:left;">Time</th>
                  <th style="padding:8px 12px;text-align:left;">Type</th>
                  <th style="padding:8px 12px;text-align:left;">Status</th>
                </tr></thead>
                <tbody>{rows}</tbody>
              </table>
            </div>"""

    return f"""<!DOCTYPE html><html><body style="margin:0;padding:0;font-family:Arial,sans-serif;background:#f3f4f6;">
    <div style="max-width:640px;margin:0 auto;padding:24px;">
      <div style="background:#1f2937;color:white;padding:20px 24px;border-radius:8px 8px 0 0;text-align:center;">
        <h1 style="margin:0;font-size:22px;">BIG Hat Entertainment</h1>
        <p style="margin:4px 0 0;opacity:0.8;font-size:14px;">Primary Host — Weekly Venue Report</p>
      </div>
      <div style="background:white;padding:24px;border-radius:0 0 8px 8px;">
        <p style="font-size:16px;color:#1f2937;">Hi {name},</p>
        <p style="color:#4b5563;">Here's your venue report for <strong>{week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}</strong>:</p>
        {venue_html}
        <p style="color:#6b7280;font-size:13px;margin-top:24px;">Remember to claim your events before Sunday so they stay reserved for you. After Sunday, unclaimed events open to all hosts.</p>
        <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
        <p style="color:#9ca3af;font-size:12px;text-align:center;">BIG Hat Entertainment Scheduling System</p>
      </div>
    </div>
    </body></html>"""


# ===================== SECONDARY MONDAY AVAILABILITY =====================

async def send_secondary_monday_availability():
    """
    Send each secondary host a list of available (unclaimed) events at their
    secondary venues for the current week.
    """
    logger.info("=== Sending Monday Secondary Availability ===")
    mon, sun = _get_current_week_range()
    mon_iso = datetime(mon.year, mon.month, mon.day, tzinfo=timezone.utc).isoformat()
    sun_end = datetime(sun.year, sun.month, sun.day, 23, 59, 59, tzinfo=timezone.utc).isoformat()

    secondary_roles = await _db.venue_roles.find({"role_type": "secondary"}, {"_id": 0}).to_list(1000)
    if not secondary_roles:
        logger.info("No secondary roles found, skipping.")
        return {"sent": 0, "errors": []}

    all_employees = {e['id']: e for e in await _db.employees.find({}, {"_id": 0}).to_list(500)}
    all_venues = {v['id']: v for v in await _db.venues.find({}, {"_id": 0}).to_list(200)}
    all_events = await _db.events.find({
        "date": {"$gte": mon_iso, "$lte": sun_end},
        "claimed_by": None,
    }, {"_id": 0}).to_list(2000)

    # Group roles by employee
    from collections import defaultdict
    emp_roles = defaultdict(list)
    for role in secondary_roles:
        emp_roles[role['employee_id']].append(role)

    sent_count = 0
    errors = []

    for emp_id, roles in emp_roles.items():
        emp = all_employees.get(emp_id)
        if not emp or not emp.get('email'):
            continue

        available_events = []
        for role in roles:
            venue = all_venues.get(role['venue_id'])
            if not venue:
                continue
            category = role['role_category']

            for ev in all_events:
                if ev['venue_id'] != role['venue_id']:
                    continue
                ev_cat = _map_event_type_to_category(ev.get('event_type', ''))
                if ev_cat != category:
                    continue
                ev_date = datetime.fromisoformat(ev['date']) if isinstance(ev['date'], str) else ev['date']
                available_events.append({
                    "venue_name": venue['name'],
                    "day": ev_date.strftime('%A, %b %d'),
                    "time": ev_date.strftime('%I:%M %p'),
                    "type": ev['event_type'],
                })

        if not available_events:
            continue

        # De-duplicate (an event could match multiple secondary roles at same venue)
        seen = set()
        unique_events = []
        for ae in available_events:
            key = f"{ae['venue_name']}|{ae['day']}|{ae['time']}|{ae['type']}"
            if key not in seen:
                seen.add(key)
                unique_events.append(ae)

        unique_events.sort(key=lambda x: x['day'])

        html = _build_secondary_email_html(emp['name'], mon, sun, unique_events)
        subject = f"BIG Hat — {len(unique_events)} Open Hosting Spot{'s' if len(unique_events) != 1 else ''} This Week"

        try:
            await asyncio.to_thread(_send_email, emp['email'], subject, html)
            sent_count += 1
            logger.info(f"Secondary availability sent to {emp['name']} ({emp['email']})")
            await asyncio.sleep(0.6)  # Rate limit: max 2 req/sec
        except Exception as e:
            logger.error(f"Failed to send to {emp['email']}: {e}")
            errors.append({"email": emp['email'], "error": str(e)})

    logger.info(f"Monday secondary reports: {sent_count} sent, {len(errors)} errors")
    return {"sent": sent_count, "errors": errors}


def _build_secondary_email_html(name, week_start, week_end, events):
    rows = ""
    for ev in events:
        rows += f"""<tr>
          <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;">{ev['venue_name']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;">{ev['day']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;">{ev['time']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;">{ev['type']}</td>
        </tr>"""

    return f"""<!DOCTYPE html><html><body style="margin:0;padding:0;font-family:Arial,sans-serif;background:#f3f4f6;">
    <div style="max-width:640px;margin:0 auto;padding:24px;">
      <div style="background:#7c3aed;color:white;padding:20px 24px;border-radius:8px 8px 0 0;text-align:center;">
        <h1 style="margin:0;font-size:22px;">BIG Hat Entertainment</h1>
        <p style="margin:4px 0 0;opacity:0.8;font-size:14px;">Open Hosting Spots This Week</p>
      </div>
      <div style="background:white;padding:24px;border-radius:0 0 8px 8px;">
        <p style="font-size:16px;color:#1f2937;">Hi {name},</p>
        <p style="color:#4b5563;">There are <strong>{len(events)}</strong> open hosting spot{'s' if len(events) != 1 else ''} at your secondary venues for <strong>{week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}</strong>:</p>
        <table style="width:100%;border-collapse:collapse;font-size:14px;margin-top:16px;">
          <thead><tr style="background:#ede9fe;">
            <th style="padding:8px 12px;text-align:left;">Venue</th>
            <th style="padding:8px 12px;text-align:left;">Day</th>
            <th style="padding:8px 12px;text-align:left;">Time</th>
            <th style="padding:8px 12px;text-align:left;">Type</th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>
        <p style="color:#6b7280;font-size:13px;margin-top:24px;">Log in to the scheduler to claim any of these events.</p>
        <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
        <p style="color:#9ca3af;font-size:12px;text-align:center;">BIG Hat Entertainment Scheduling System</p>
      </div>
    </div>
    </body></html>"""
