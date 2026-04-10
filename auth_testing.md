# Auth Testing Playbook for BIG Hat Hub

## Google OAuth Flow
1. User clicks "Sign in with Google" on login page
2. Redirects to https://auth.emergentagent.com/?redirect={origin}/
3. Google authenticates user
4. Returns to {origin}/#session_id={session_id}
5. AuthCallback processes session_id, calls backend /api/auth/google-callback
6. Backend exchanges session_id for user data via Emergent Auth API
7. Creates/updates user, creates session, sets cookie
8. Redirects to dashboard

## Test Credentials
- Master Admin: Sellards@bighat.live / BigHat2024!
- Default host password: B1GHat
