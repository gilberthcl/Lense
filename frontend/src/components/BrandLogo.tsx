import { useState } from "react";
import { api } from "../lib/api";
import { IconLogo } from "./icons";

/**
 * Platform logo. Renders the uploaded LENS logo if present, otherwise falls
 * back to the built-in mark. The platform-logo endpoint is auth-exempt so it
 * also works on the lock screen. Pass `version` to bust the cache after upload.
 */
export function BrandLogo({
  className = "",
  iconSize = 20,
  version,
}: {
  className?: string;
  iconSize?: number;
  version?: number | string;
}) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div
        className={`flex items-center justify-center bg-indigo-500/15 text-indigo-300 ring-1 ring-inset ring-indigo-500/30 ${className}`}
      >
        <IconLogo width={iconSize} height={iconSize} />
      </div>
    );
  }

  const src = version != null
    ? `${api.platformLogoUrl()}?v=${version}`
    : api.platformLogoUrl();

  return (
    <img
      src={src}
      alt="LENS"
      onError={() => setFailed(true)}
      className={`object-cover ${className}`}
    />
  );
}
