# DToxOut Web Frontend

React 19 + TypeScript + Vite web application for cosmetic ingredient safety analysis.

## Setup & Running

1. Install dependencies:
   ```bash
   npm install
   ```

2. Copy `.env.example` to `.env` and set `VITE_API_URL`:
   ```env
   VITE_API_URL=http://localhost:8000/api/v1
   ```

3. Start development server:
   ```bash
   npm run dev
   ```
   The dev server will run on `http://localhost:5173`.

4. Run unit and integration tests:
   ```bash
   npm test
   ```

5. Build production bundle:
   ```bash
   npm run build
   ```

## Production Docker Deployment

Build and run Nginx-served static SPA container:
```bash
docker build -t dtoxout-frontend .
docker run -p 3000:80 dtoxout-frontend
```
