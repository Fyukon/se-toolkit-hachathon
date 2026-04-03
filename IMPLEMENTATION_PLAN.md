# Implementation Plan

## Product Idea

- End user: student who manages their schedule and tasks in SingularityApp.
- Problem: it is hard to quickly understand what the day or week looks like, and it is inconvenient to manually update the schedule.
- Product idea: a Telegram-based assistant that syncs SingularityApp data, summarizes the day and week, and later lets the user change the schedule with natural language.

## Version 1

Goal: deliver one useful scenario end-to-end and make it production-like, not a prototype.

### Core feature

- Load data from the SingularityApp API.
- Generate a clear summary of the current day and week.

### Backend

- Authenticate and fetch data from the SingularityApp API.
- Normalize schedule data into a common internal format.
- Expose an endpoint for day/week summaries.
- Use LLM summarization to turn raw schedule data into a short human-readable report.

### Database

- Store users.
- Cache synchronized events and tasks.
- Save request history and generated summaries.

### Client

- Build a simple Telegram client or web client.
- Support commands like "show my day" and "show my week".
- Present results in a compact and readable format.

### Done criteria

- The user connects their account.
- The user receives an up-to-date summary of the day and week.
- Data comes from the API, not from mock data.
- Basic tests cover synchronization and summary generation.

## Version 2

Goal: add schedule control through LLM and make the product deployable.

### Core upgrade

- Let the user write natural language commands that change the schedule.

### Backend

- Parse LLM commands into actions.
- Ask for confirmation before applying changes.
- Update existing events, move tasks, and create new items.
- Handle time conflicts and validate changes.

### Database

- Store drafts of changes.
- Keep a log of user actions.
- Track execution status and errors.

### Client

- Build a Telegram Mini App as the main Version 2 interface.
- Add a command input for requests like "move my meeting two hours later".
- Show a confirmation screen before applying changes.
- Show the result after the change is applied.

### Product improvements

- Use LLM responses to explain what will change.
- Notify the user about conflicts and invalid commands.
- Deploy the product so it is accessible for use.
- Dockerize all services.

### Done criteria

- The user can both view and change the schedule.
- All changes go through confirmation.
- The product is deployed and usable.

## Build Order

1. Define the data model for users, events, tasks, and change requests.
2. Implement synchronization with the SingularityApp API.
3. Build the Version 1 summary flow and a simple client.
4. Add LLM action parsing and confirmation for changes.
5. Package everything with Docker and deploy Version 2.

## Important Constraint

- Telegram bots are blocked on university VMs, so Version 2 should use a Telegram Mini App or a web client as the deployable interface.
- A classic Telegram bot can still be useful during development, but it should not be the only production client.
