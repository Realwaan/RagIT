import { ClerkProvider, SignIn, UserButton, useAuth } from '@clerk/react';
import { useEffect, useState } from 'react';
import { App } from './App';
import { setTokenProvider } from './types';

function AccountWorkspace() {
  const { isLoaded, isSignedIn, userId, getToken } = useAuth();
  const [readyUser, setReadyUser] = useState<string | null>(null);
  useEffect(() => {
    setTokenProvider(() => getToken());
    setReadyUser(userId || null);
    return () => setTokenProvider(undefined);
  }, [getToken, userId]);
  if (!isLoaded) return <p role="status">Loading your account...</p>;
  if (!isSignedIn) return <main className="auth-screen"><h1>Welcome to RagIT</h1><p>Sign in or create an account to work with your documents.</p><SignIn routing="hash" /></main>;
  if (readyUser !== userId) return <p role="status">Opening your workspace...</p>;
  return <><div className="account-control" aria-label="Your account"><UserButton /></div><App key={userId} ownerId={userId} /></>;
}

export function AuthRoot() {
  const key = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
  if (!key) return <main className="auth-screen"><h1>Authentication setup required</h1><p>Configure the Clerk publishable key and rebuild the frontend.</p></main>;
  return <ClerkProvider publishableKey={key}><AccountWorkspace /></ClerkProvider>;
}
