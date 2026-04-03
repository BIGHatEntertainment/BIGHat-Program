# Auth Testing Playbook

## Step 1: MongoDB Verification
```
mongosh
use test_database
db.users.find({role: "master_admin"}).pretty()
db.users.findOne({role: "master_admin"}, {password_hash: 1})
```
Verify: bcrypt hash starts with `$2b$`, indexes exist on users.email (unique), login_attempts.identifier.

## Step 2: API Testing
```
API_URL=https://show-command.preview.emergentagent.com
curl -c cookies.txt -X POST $API_URL/api/auth/login -H "Content-Type: application/json" -d '{"email":"Sellards@bighat.live","password":"BigHat2024!"}'
curl -b cookies.txt $API_URL/api/auth/me
```

Login should return the user object with token. The `/me` call should return the same user.
