/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" in the static demo build (`npm run build:demo`), which plays a recorded town. */
  readonly VITE_DEMO?: string;
}
