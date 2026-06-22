import { useState, type FormEvent, type ReactNode } from "react";
import { IconLogo } from "./icons";
import { Button, Input } from "./ui";

/*
  Local single-user access gate. A 6-character PIN is hashed (SHA-256 + static
  salt) and stored in localStorage; the unlocked state lives in sessionStorage
  so a refresh won't re-prompt but closing the tab will.

  Note: this gates the UI for a local, on-box, single-operator deployment — it
  is not a substitute for network auth. The API is expected to be bound to
  localhost per the local-only compliance model.
*/

const PIN_HASH_KEY = "lens-pin-hash";
const UNLOCKED_KEY = "lens-unlocked";
const SALT = "lens-thfe::v1";
const PIN_LEN = 6;

async function hashPin(pin: string): Promise<string> {
  const data = new TextEncoder().encode(`${SALT}:${pin}`);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function lockApp() {
  sessionStorage.removeItem(UNLOCKED_KEY);
  window.location.reload();
}

export function PinGate({ children }: { children: ReactNode }) {
  const [unlocked, setUnlocked] = useState(
    () => sessionStorage.getItem(UNLOCKED_KEY) === "1",
  );
  const [hasPin, setHasPin] = useState(() => !!localStorage.getItem(PIN_HASH_KEY));

  const [pin, setPin] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (unlocked) return <>{children}</>;

  const unlock = () => {
    sessionStorage.setItem(UNLOCKED_KEY, "1");
    setUnlocked(true);
  };

  const onSetup = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (pin.length !== PIN_LEN) return setError(`PIN must be exactly ${PIN_LEN} characters.`);
    if (pin !== confirm) return setError("The two PINs do not match.");
    setBusy(true);
    try {
      localStorage.setItem(PIN_HASH_KEY, await hashPin(pin));
      unlock();
    } finally {
      setBusy(false);
    }
  };

  const onEnter = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const ok = (await hashPin(pin)) === localStorage.getItem(PIN_HASH_KEY);
      if (ok) unlock();
      else {
        setError("Incorrect PIN.");
        setPin("");
      }
    } finally {
      setBusy(false);
    }
  };

  const resetPin = () => {
    if (!window.confirm("Reset the PIN? You'll set a new one on the next screen.")) return;
    localStorage.removeItem(PIN_HASH_KEY);
    setHasPin(false);
    setPin("");
    setConfirm("");
    setError(null);
  };

  return (
    <div className="flex h-full items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900/60 p-7 shadow-xl">
        <div className="mb-5 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/15 text-indigo-300 ring-1 ring-inset ring-indigo-500/30">
            <IconLogo width={20} height={20} />
          </div>
          <div className="leading-tight">
            <div className="font-mono text-sm font-bold tracking-[0.25em] text-slate-100">LENS</div>
            <div className="text-[10px] uppercase tracking-wide text-slate-500">
              {hasPin ? "Enter your PIN" : "Set an access PIN"}
            </div>
          </div>
        </div>

        <form onSubmit={hasPin ? onEnter : onSetup} className="space-y-3">
          <Input
            autoFocus
            type="password"
            inputMode="text"
            maxLength={PIN_LEN}
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            placeholder={`${PIN_LEN}-character PIN`}
            className="text-center font-mono text-lg tracking-[0.5em]"
          />
          {!hasPin && (
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
            {hasPin ? "Unlock" : "Set PIN & Enter"}
          </Button>
        </form>

        {hasPin && (
          <button
            onClick={resetPin}
            className="mt-4 w-full text-center text-xs text-slate-600 hover:text-slate-400"
          >
            Forgot PIN? Reset
          </button>
        )}
        <p className="mt-4 text-center text-[11px] leading-relaxed text-slate-600">
          Local access gate for this on-box deployment.
        </p>
      </div>
    </div>
  );
}
