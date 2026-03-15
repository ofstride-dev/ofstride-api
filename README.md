# Ofstride Redesign (Vite + Tailwind)

Modern, modular redesign for Ofstride Services LLP using React + TypeScript + Tailwind.

## Structure
- src/components: shared UI (Header, Footer, ChatWidget, Layout)
- src/sections: homepage sections
- src/pages: route-level pages
- src/data: central content config

## Run
1. Install dependencies:
   npm install
2. Start dev server:
   npm run dev

### Full-stack (UI + FastAPI + agent)
To test chat + analytics end-to-end, run:
   npm run dev:full

## Notes
- Offstride content, logo, and colors are preserved.
- Chat widget uses the FastAPI proxy by default (API on :5175). The agent service is expected on :8001.
- Tailwind is configured for @apply via src/index.css.
