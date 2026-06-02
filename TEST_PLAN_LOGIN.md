# Test Plan for Login Functionality Recovery

## Objective
Verify that the login system works correctly after reverting commit 2503cee which broke the authentication flow.

## Test Environment
- Flask development server running locally
- Database connection configured (MySQL/SQLite)
- Clerk API credentials configured in environment variables

## Test Cases

### 1. Traditional Login (Email/Password)
**Prerequisites:**
- At least one user exists in the database with known credentials

**Steps:**
1. Navigate to `/login` (or root path `/`)
2. Enter valid email and password
3. Submit form
4. Verify redirect to dashboard (`/dashboard/index`)
5. Verify session contains user_id and username

**Expected Result:** Successful login and redirection to dashboard

### 2. Traditional Login Failure
**Prerequisites:**
- Non-existent user or incorrect password

**Steps:**
1. Navigate to login page
2. Enter invalid credentials
3. Submit form
4. Verify error message "Email o contraseña incorrectos" appears
5. Verify user remains on login page

**Expected Result:** Login failure with appropriate error message

### 3. Clerk Authentication - New User Flow
**Prerequisites:**
- Clerk application configured with valid keys
- No existing user in database with test email

**Steps:**
1. Navigate to login page
2. Click "Sign in with Clerk" (or navigate to `/register` which redirects to Clerk)
3. Complete Clerk sign up flow with test email
4. After Clerk redirect back to `/auth/clerk-callback`
5. Verify system creates user in database (check User table)
6. Verify redirect to `/auth/setup-account` (since no restaurant exists)
7. Complete restaurant setup form
8. Verify redirect to dashboard

**Expected Result:** New user created, restaurant configured, successful login

### 4. Clerk Authentication - Existing User Flow
**Prerequisites:**
- User exists in database with clerk_id populated
- User has associated restaurant

**Steps:**
1. Navigate to login page
2. Click "Sign in with Clerk"
3. Complete Clerk sign in with existing account
4. Verify redirect to dashboard (since user has restaurant)
5. Verify session contains correct user data

**Expected Result:** Existing user authenticated, redirected to dashboard

### 5. Clerk Authentication - Existing User Without Restaurant
**Prerequisites:**
- User exists in database with clerk_id populated
- User does NOT have associated restaurant

**Steps:**
1. Navigate to login page
2. Click "Sign in with Clerk"
3. Complete Clerk sign in
4. Verify redirect to `/auth/setup-account`
5. Complete restaurant setup
6. Verify redirect to dashboard

**Expected Result:** User guided to setup restaurant, then to dashboard

### 6. Session Persistence
**Prerequisites:**
- Successfully logged in user

**Steps:**
1. After login, access protected route (e.g., `/dashboard/index`)
2. Verify access granted without re-authentication
3. Close browser, reopen, navigate to dashboard
4. Verify session persists (if configured as permanent) or redirects to login

**Expected Result:** Session maintained appropriately

### 7. Logout Functionality
**Prerequisites:**
- Authenticated user session

**Steps:**
1. Navigate to `/auth/logout`
2. Verify session cleared
3. Verify redirect to logout template
4. Attempt to access protected route
5. Verify redirect to login

**Expected Result:** Session terminated, user logged out

## Database Verification
For each test case involving user creation/modification:
1. Check `User` table for correct email, username, clerk_id
2. Check `AITokenWallet` table for token initialization
3. Check `Restaurant` table when applicable
4. Verify proper relationships established

## Performance Considerations
- Verify login completes within reasonable time (<2 seconds)
- Check for any database errors in logs
- Verify no duplicate user creation on repeated Clerk callbacks

## Rollback Verification
Confirm that the problematic commit 2503cee has been reverted:
1. `git log --oneline -3` should show revert commit as HEAD
2. The `sync_clerk()` function should contain user creation logic, not rejection

## Success Criteria
All test cases pass with expected results, demonstrating:
- Authentication system restored to working state
- Both traditional and Clerk flows functional
- Proper user creation and session management
- No regression in existing functionality (password reset, etc.)