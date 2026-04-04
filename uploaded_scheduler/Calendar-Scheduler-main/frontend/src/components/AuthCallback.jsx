import { useEffect, useRef, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const AuthCallback = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const hasProcessed = useRef(false);
  const [status, setStatus] = useState('processing');
  const [error, setError] = useState(null);

  useEffect(() => {
    // Prevent double processing (React StrictMode)
    if (hasProcessed.current) {
      console.log('AuthCallback: Already processed, skipping');
      return;
    }
    hasProcessed.current = true;

    const processSession = async () => {
      try {
        console.log('AuthCallback: Starting OAuth processing');
        console.log('AuthCallback: Current URL:', window.location.href);
        console.log('AuthCallback: Hash:', location.hash);
        
        // Extract session_id from URL fragment
        const hash = location.hash.substring(1);
        const params = new URLSearchParams(hash);
        const sessionId = params.get('session_id');

        console.log('AuthCallback: Extracted session_id:', sessionId ? `${sessionId.substring(0, 10)}...` : 'MISSING');

        if (!sessionId) {
          console.error('AuthCallback: No session_id found in URL');
          setError('No session ID found. Please try logging in again.');
          setStatus('error');
          // Wait a moment before redirecting
          setTimeout(() => navigate('/', { replace: true }), 2000);
          return;
        }

        setStatus('authenticating');
        console.log('AuthCallback: Making API request to', `${BACKEND_URL}/api/auth/session`);
        
        // Exchange session_id for session_token
        // Remove withCredentials as it can cause CORS issues
        const response = await axios.post(
          `${BACKEND_URL}/api/auth/session`,
          {},
          {
            headers: {
              'X-Session-ID': sessionId,
              'Content-Type': 'application/json'
            },
            timeout: 30000 // 30 second timeout
          }
        );

        console.log('AuthCallback: API response received');
        console.log('AuthCallback: Response status:', response.status);
        console.log('AuthCallback: Response data keys:', Object.keys(response.data || {}));

        const userData = response.data;

        // Validate response data - check for various possible field names
        const employeeId = userData?.employee_id || userData?.employeeId || userData?.id;
        const userName = userData?.name || userData?.email?.split('@')[0] || 'User';
        const userEmail = userData?.email || '';
        const isAdmin = userData?.is_admin || userData?.isAdmin || false;

        if (!employeeId) {
          console.error('AuthCallback: Invalid user data received:', userData);
          setError('Invalid response from server. Please try again.');
          setStatus('error');
          setTimeout(() => navigate('/', { replace: true }), 2000);
          return;
        }

        console.log('AuthCallback: User validated:', { employeeId, userName, userEmail });
        setStatus('success');

        // Store user data in sessionStorage (consistent with HostLogin.jsx)
        const hostData = {
          id: employeeId,
          name: userName,
          email: userEmail,
          is_admin: isAdmin
        };
        
        console.log('AuthCallback: Storing in sessionStorage');
        
        // Clear any old data first
        sessionStorage.removeItem('loggedInHost');
        
        // Store new data
        sessionStorage.setItem('loggedInHost', JSON.stringify(hostData));

        // Verify storage was successful
        const stored = sessionStorage.getItem('loggedInHost');
        if (!stored) {
          console.error('AuthCallback: Failed to store in sessionStorage');
          setError('Failed to save login data. Please try again.');
          setStatus('error');
          setTimeout(() => navigate('/', { replace: true }), 2000);
          return;
        }
        
        console.log('AuthCallback: Storage verified');

        // Clear the URL hash to prevent re-processing
        window.history.replaceState(null, '', window.location.pathname);
        
        // Small delay to ensure state is set before navigation
        console.log('AuthCallback: Navigating to home page');
        setTimeout(() => {
          navigate('/', { replace: true });
        }, 100);

      } catch (error) {
        console.error('AuthCallback: Error occurred');
        console.error('AuthCallback: Error name:', error.name);
        console.error('AuthCallback: Error message:', error.message);
        console.error('AuthCallback: Error response:', error.response?.data);
        console.error('AuthCallback: Error status:', error.response?.status);
        
        let errorMessage = 'Authentication failed. Please try again.';
        
        if (error.response?.status === 403) {
          errorMessage = 'Your email is not authorized. Please contact an administrator to add your account.';
        } else if (error.response?.status === 401) {
          errorMessage = 'Session expired or invalid. Please try logging in again.';
        } else if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
          errorMessage = 'Request timed out. Please check your connection and try again.';
        } else if (error.code === 'ERR_NETWORK' || error.message === 'Network Error') {
          errorMessage = 'Network error. Please check your connection and try again.';
        } else if (error.response?.data?.detail) {
          errorMessage = error.response.data.detail;
        }
        
        setError(errorMessage);
        setStatus('error');
        
        // Clear any partial session data
        sessionStorage.removeItem('loggedInHost');
        
        // Wait before redirecting so user can see the error
        setTimeout(() => {
          navigate('/', { replace: true });
        }, 3000);
      }
    };

    // Small delay to ensure component is fully mounted
    setTimeout(processSession, 100);
  }, [navigate, location]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="text-center p-8 bg-white rounded-lg shadow-lg max-w-md">
        {status === 'processing' && (
          <>
            <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-blue-500 mx-auto mb-4"></div>
            <p className="text-lg font-semibold text-gray-700">Processing login...</p>
          </>
        )}
        
        {status === 'authenticating' && (
          <>
            <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-green-500 mx-auto mb-4"></div>
            <p className="text-lg font-semibold text-gray-700">Authenticating...</p>
          </>
        )}
        
        {status === 'success' && (
          <>
            <div className="text-green-500 mb-4">
              <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"></path>
              </svg>
            </div>
            <p className="text-lg font-semibold text-green-700">Login successful!</p>
            <p className="text-sm text-gray-500 mt-2">Redirecting...</p>
          </>
        )}
        
        {status === 'error' && (
          <>
            <div className="text-red-500 mb-4">
              <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path>
              </svg>
            </div>
            <p className="text-lg font-semibold text-red-700">Login Failed</p>
            <p className="text-sm text-gray-600 mt-2">{error}</p>
            <p className="text-xs text-gray-400 mt-4">Redirecting to login page...</p>
          </>
        )}
      </div>
    </div>
  );
};

export default AuthCallback;
