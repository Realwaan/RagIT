import { ClerkProvider, SignIn, UserButton, useAuth } from '@clerk/react';
import { BookOpen, ScanEye, ShieldCheck, Sparkles } from 'lucide-react';
import { useEffect, useState } from 'react';
import { App } from './App';
import { setTokenProvider } from './types';

function AuthBrand() {
  return (
    <div className="auth-brand">
      <span className="logo"><Sparkles size={20} /></span>
      <div>
        <span className="auth-brand-name">RagIT</span>
        <span className="auth-brand-tag">Enterprise Document Intelligence</span>
      </div>
    </div>
  );
}

function AccountWorkspace() {
  const { isLoaded, isSignedIn, userId, getToken } = useAuth();
  const [readyUser, setReadyUser] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (isSignedIn && userId) {
      setTokenProvider((opts) => getToken(opts));
      // Warm up token retrieval before mounting App to eliminate cold-start race conditions
      getToken()
        .then(() => {
          if (!cancelled) {
            setReadyUser(userId);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setReadyUser(userId);
          }
        });
    } else {
      setTokenProvider(undefined);
      setReadyUser(null);
    }
    return () => {
      cancelled = true;
      setTokenProvider(undefined);
    };
  }, [getToken, isSignedIn, userId]);

  if (!isLoaded) {
    return (
      <main className="auth-screen">
        <div className="auth-card auth-loading-card">
          <AuthBrand />
          <p role="status" className="auth-status">Loading your account...</p>
        </div>
      </main>
    );
  }
  if (!isSignedIn) {
    return (
      <main className="auth-screen">
        <div className="auth-card">
          <AuthBrand />
          <div className="auth-header">
            <h1>Welcome to RagIT</h1>
            <p>Sign in or create an account to work with your documents.</p>
          </div>
          <div className="auth-badges" aria-label="Platform capabilities">
            <span className="auth-badge"><BookOpen size={13} /> Grounded Citations</span>
            <span className="auth-badge"><ShieldCheck size={13} /> Compliance Audit</span>
            <span className="auth-badge"><ScanEye size={13} /> Visual Evidence</span>
          </div>
          <div className="auth-signin-wrap">
            <SignIn routing="hash" />
          </div>
        </div>
      </main>
    );
  }
  if (readyUser !== userId) {
    return (
      <main className="auth-screen">
        <div className="auth-card auth-loading-card">
          <AuthBrand />
          <p role="status" className="auth-status">Opening your workspace...</p>
        </div>
      </main>
    );
  }
  return (
    <App
      key={userId}
      ownerId={userId}
      accountControl={
        <div className="account-control" aria-label="Your account">
          <UserButton />
        </div>
      }
    />
  );
}

export function AuthRoot() {
  const key = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
  if (!key) {
    return (
      <main className="auth-screen">
        <div className="auth-card auth-loading-card">
          <AuthBrand />
          <div className="auth-header">
            <h1>Authentication setup required</h1>
            <p>Configure the Clerk publishable key and rebuild the frontend.</p>
          </div>
        </div>
      </main>
    );
  }
  return <ClerkProvider publishableKey={key}><AccountWorkspace /></ClerkProvider>;
}
