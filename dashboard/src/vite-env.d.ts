/// <reference types="vite/client" />

// CSS imports — Vite handles these at build time
declare module '*.css' {
  const content: string
  export default content
}
