# StudyMate – Personalised AI study companion

StudyMate is a minimal, UK-friendly web application that wraps GPT guidance around the way *you* learn. Upload notes, lecture slides, or revision sheets, capture your learning habits, and receive tailored plans, deep-dive notes, quizzes, and mock papers drawn strictly from trusted material.

## Features

- **Secure learner accounts** – register once and StudyMate remembers your tone, learning style, trusted materials, and assessment history.
- **Interactive learner profile** – record learning style, goals, timetable, and preferred tone to steer every response.
- **Document vault** – upload classroom notes or handouts; preview them inline and StudyMate revisits each excerpt twice before replying.
- **AI coaching hub** – request planners, revision notes, weakness analysis, confidence check-ins, teacher-style mocks, or application ideas in warm British English.
- **Assessment tracker & analytics** – log past papers so the assistant mirrors your teacher’s style, highlights weak topics, and tracks average scores.
- **Auto-generated planner** – local scheduling engine builds a GitHub-inspired board of daily focus blocks using your topics and availability.
- **Offline-friendly** – without an OpenAI key the app still produces structured placeholders so you can preview prompts.

## Getting started

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

2. **Provide an OpenAI API key** (optional but recommended):

   ```bash
   export OPENAI_API_KEY="sk-your-key"
   ```

3. **Run the development server**

   ```bash
   uvicorn study_app.server:app --reload
   ```

4. Visit [http://localhost:8000](http://localhost:8000) to access the interface.

Uploaded documents, profile details, and interaction history are stored in a local SQLite database under `~/.study_companion/studymate.db`.

## Front-end overview

The static interface lives under `static/`:

- `index.html` – GitHub-flavoured dashboard with navigation panels, planner board, and document preview column.
- `styles.css` – muted slate palette, badges, and panels to mimic a GitHub repository workspace.
- `main.js` – account-aware fetch helpers that wire the UI to the FastAPI endpoints plus planner generation and document previews.

## Testing

Run the automated checks with:

```bash
pytest
```

Tests rely on mock GPT responses and touch only the storage layer, so no network access is required.
