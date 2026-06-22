import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api, ApiError, clearToken, getToken, setToken } from "../lib/api";
import { BrandLogo } from "./BrandLogo";
import { Button, Input } from "./ui";

/*
  Local single-operator access gate, enforced end to end:
  the PIN is verified by the backend, which returns a token sent as a bearer
  credential on every API call (see lib/api). The token is held in localStorage;
  Lock clears it. This protects the on-box deployment for a single operator.
*/

const PIN_LEN = 6;

export function lockApp() {
  clearToken();
  window.location.reload();
}

export function PinGate({ children }: { children: ReactNode }) {
  const [unlocked, setUnlocked] = useState(() => !!getToken());
  const [configured, setConfigured] = useState<boolean | null>(null);

  const [pin, setPin] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (unlocked) return;
    api
      .authStatus()
      .then((s) => setConfigured(s.configured))
      .catch(() => setConfigured(false));
  }, [unlocked]);

  if (unlocked) return <>{children}</>;

  const finish = (token: string) => {
    setToken(token);
    setUnlocked(true);
  };

  const onSetup = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (pin.length !== PIN_LEN) return setError(`PIN must be exactly ${PIN_LEN} characters.`);
    if (pin !== confirm) return setError("The two PINs do not match.");
    setBusy(true);
    try {
      finish((await api.authSetup(pin)).token);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not set the PIN.");
    } finally {
      setBusy(false);
    }
  };

  const onEnter = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      finish((await api.authLogin(pin)).token);
    } catch (e) {
      setError(e instanceof ApiError && e.status === 401 ? "Incorrect PIN." : "Login failed.");
      setPin("");
    } finally {
      setBusy(false);
    }
  };

  const isSetup = configured === false;

  return (
    <div className="flex h-full items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900/60 p-7 shadow-xl">
        <div className="mb-5 flex items-center gap-3">
          <BrandLogo className="h-10 w-10 rounded-lg" />
          <div className="leading-tight">
            <div className="font-mono text-sm font-bold tracking-[0.25em] text-slate-100">LENS</div>
            <div className="text-[10px] uppercase tracking-wide text-slate-500">
              {configured === null ? "…" : isSetup ? "Set an access PIN" : "Enter your PIN"}
            </div>
          </div>
        </div>

        {configured === null ? (
          <p className="py-6 text-center text-sm text-slate-500">Connecting…</p>
        ) : (
          <form onSubmit={isSetup ? onSetup : onEnter} className="space-y-3">
            <Input
              autoFocus
              type="password"
              maxLength={PIN_LEN}
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder={`${PIN_LEN}-character PIN`}
              className="text-center font-mono text-lg tracking-[0.5em]"
            />
            {isSetup && (
              <Input
                type="password"
                maxLength={PIN_LEN}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="Confirm PIN"
                className="text-center font-mono text-lg tracking-[0.5em]"
              />
            )}
            {error && <p className="text-sm text-red-400">{error}</p>}
            <Button type="submit" variant="primary" disabled={busy} className="w-full justify-center">
              {isSetup ? "Set PIN & Enter" : "Unlock"}
            </Button>
          </form>
        )}

        <p className="mt-4 text-center text-[11px] leading-relaxed text-slate-600">
          Local access gate for this on-box deployment.
        </p>
      </div>
    </div>
  );
}
