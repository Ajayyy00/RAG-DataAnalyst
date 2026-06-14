# Healthcare Copilot Frontend

This directory contains the user interface for the Healthcare Copilot application. The frontend is built as a single-page application (SPA) using React and Vite, designed to provide analysts and clinicians with an intuitive interface for querying and visualizing healthcare data.

## Architecture and Technologies

- **Framework**: React with Vite for fast build times and hot module replacement.
- **Routing**: React Router DOM for client-side navigation.
- **Styling**: Tailwind CSS for utility-first styling and responsive design.
- **State Management**: Context API and local component state.
- **Data Fetching**: Axios for asynchronous HTTP requests to the FastAPI backend.
- **Visualization**:
  - Recharts for rendering dynamic analytical charts (e.g., line, bar, pie, and scatter charts).
  - React Force Graph for rendering the interactive Neo4j knowledge graph.

## Core Features

### Interactive Chat Interface
The primary interface allows users to submit natural language queries. It displays the reasoning process, the generated SQL syntax, execution performance metrics (row count and latency), and AI-generated insights summarizing the results.

### Dynamic Chart Rendering
Upon receiving analytical data from the backend, the frontend automatically selects and renders the most appropriate chart type. The chart configurations support dynamic axes, tooltips, and responsive container scaling.

### Knowledge Graph Explorer
A dedicated visualization pane maps clinical entities (such as Patients, Encounters, and Providers) as nodes and relationships as edges. The explorer provides a force-directed graph layout, enabling users to visually traverse complex interconnected medical histories.

### Authentication and Session Management
The application manages JWT access and refresh tokens, securely storing session states and handling token expiration events transparently.

## Local Development

Ensure Node.js is installed on your local environment.

1. Navigate to the frontend directory.
2. Install dependencies:
   `npm install`
3. Start the development server:
   `npm run dev`

The local development server will typically bind to `http://localhost:5173`. Ensure the backend API is running concurrently for full functionality.
