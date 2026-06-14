# Healthcare Copilot

Healthcare Copilot is a domain-specific, artificial intelligence-assisted application designed to translate natural language inquiries into executable SQL queries against a healthcare database. The system incorporates a multi-agent architecture, retrieval-augmented generation (RAG), and a knowledge graph to assist analysts and clinicians in extracting and understanding data securely.

## System Architecture

The application is structured into a React-based frontend and a FastAPI backend, orchestrated via Docker.

### Core Components
- **Frontend**: A React application that provides a chat interface, dynamic chart rendering, and a visual knowledge graph interface.
- **Backend**: A FastAPI server that handles query processing, routing, and system integrations.
- **Database Layer**: PostgreSQL for structured clinical data, ChromaDB for vector-based schema retrieval, Neo4j for the knowledge graph, and Redis for caching and conversation history management.
- **Observability**: Prometheus and Grafana for metrics and trace aggregation.

## Features

### Natural Language to SQL Processing
The system accepts natural language questions and converts them into PostgreSQL queries using a Large Language Model. The generation process utilizes Retrieval-Augmented Generation (RAG) against ChromaDB to supply the model with accurate schema definitions and contextual metadata.

### Agentic Workflow Execution
For complex queries, the system employs a LangGraph-based multi-agent pipeline. This pipeline executes a sequential workflow: schema extraction, execution plan generation, SQL drafting, SQL validation, and query optimization. 

### Data Insights and Visualization
Upon successful execution of a generated SQL query, the system analyzes the result set to generate automated insights and context-aware summaries. It also recommends and configures appropriate chart types based on the data structure.

### Knowledge Graph Integration
The system synchronizes clinical entities into a Neo4j knowledge graph. This enables relationship-based reasoning, allowing the system to traverse patient histories and provider networks for complex queries that extend beyond standard relational joins.

### Security and Compliance Layer
The application includes a strict security layer designed for healthcare environments and HIPAA compliance:
- **Prompt Injection Prevention**: User inputs are scanned using heuristic rules to detect and reject prompt injections and jailbreak attempts prior to model execution.
- **SQL Execution Safeguards**: An Abstract Syntax Tree (AST) parser validates all generated SQL to guarantee that only `SELECT` operations are permitted. It actively blocks Data Manipulation Language (DML), Data Definition Language (DDL), system catalog access, and common SQL injection patterns.
- **Data Leakage Prevention and PHI Redaction**: Result sets are filtered before egress. If a user is assigned an analyst role, Protected Health Information (PHI) such as Social Security Numbers, Medical Record Numbers, and contact details are automatically masked using regular expressions and column-level heuristics.
- **Audit Logging**: All queries, validation failures, and security events are logged with structured metadata to maintain an audit trail.

## Deployment Instructions

Ensure Docker and Docker Compose are installed on the host machine.

1. Navigate to the project root directory.
2. Build and start the services using Docker Compose:
   `docker compose up --build -d`
3. Access the application components:
   - Frontend: `http://localhost:5173`
   - Backend API Docs: `http://localhost:8001/docs`
   - Neo4j Browser: `http://localhost:7474`
   - Grafana Dashboard: `http://localhost:3000`
