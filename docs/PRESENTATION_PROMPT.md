# Presentation Prompt

Use the prompt below in the AI tool that will generate the presentation.
Before запуском подставь свои данные в плейсхолдеры:

- `YOUR_NAME`
- `YOUR_EMAIL`
- `YOUR_GROUP`
- `YOUR_GITHUB_REPO_URL`
- `YOUR_DEPLOYED_PRODUCT_URL`
- `YOUR_DEMO_VIDEO_PATH_OR_URL`
- `YOUR_TA_FEEDBACK_POINTS`

If you do not have a public deployed URL yet, keep an explicit placeholder on the final slide instead of inventing one.

## Prompt

```text
Create a clean, professional 5-slide presentation for a university software engineering hackathon project. The presentation will later be exported to PDF, so every slide must work well both as slides and as a PDF document.

Language of the slides: English.
Tone: concise, technical, product-focused.
Visual style: modern, minimal, high contrast, easy to scan. Do not overload slides with text.

This presentation must strictly follow the 5-slide structure required by the hackathon task:

1. Title
2. Context
3. Implementation
4. Demo
5. Links

The Demo slide is the most important slide. It must visually prioritize the demo video over everything else.

Project information:

Product title:
SE Toolkit Planner

Project summary:
Telegram bot and Telegram Mini App for syncing SingularityApp tasks, storing them locally, generating day/week summaries, and performing natural-language task actions.

End user:
Student or knowledge worker who keeps tasks in SingularityApp.

Problem:
It is inconvenient to repeatedly open the calendar and task list just to understand what is planned for today or this week, or to quickly edit tasks from a chat/mobile-first interface.

One-sentence product idea:
Connect SingularityApp once and manage tasks through a Telegram bot and Mini App with summaries and natural-language actions.

Architecture / implementation stack:
- FastAPI backend
- database layer
- Telegram bot
- Telegram Mini App frontend
- SingularityApp integration via REST API token
- OpenRouter-based LLM parsing with model `google/gemma-4-26b-a4b-it`
- Dockerized services

Version 1 included:
- account connection with SingularityApp API token
- full task sync
- day summary
- week summary
- Telegram bot commands
- Mini App interface for connect, sync, and summaries

Version 2 included:
- natural-language action parsing
- supported actions: create task, move task, complete task
- draft before apply
- explicit confirmation before sending changes to SingularityApp
- ambiguity resolution when the command matches multiple tasks
- candidate selection with buttons in Telegram bot
- candidate selection in the web Mini App
- improved UI and safer execution flow

TA feedback addressed:
YOUR_TA_FEEDBACK_POINTS

Personal information for slide 1:
- Name: YOUR_NAME
- University email: YOUR_EMAIL
- Group: YOUR_GROUP

Links for slide 5:
- GitHub repo: YOUR_GITHUB_REPO_URL
- Deployed product: YOUR_DEPLOYED_PRODUCT_URL

Demo asset:
- Main demo video file or URL: YOUR_DEMO_VIDEO_PATH_OR_URL

Hard requirements:
- Create exactly 5 slides, no more and no less.
- Use these exact slide titles: Title, Context, Implementation, Demo, Links.
- Keep slide text compact and presentation-ready.
- Do not invent features that are not listed above.
- Do not invent a deployment link if it does not exist.
- Add a QR code for the GitHub repo.
- Add a QR code for the deployed product link if provided.
- If a deployed product link is missing, show a visible placeholder such as: "Add deployed URL here".
- Slide 4 must embed the provided demo video if the tool supports video embedding.
- If real video embedding is not supported, place a large video preview/poster frame with a play icon and a clickable video link, and mention that it is a pre-recorded demo with voice commentary under 2 minutes.
- Because the presentation is exported to PDF, slide 4 should still look meaningful in static form.

Slide-by-slide instructions:

Slide 1 - Title
- Show product title prominently.
- Include name, university email, and group.
- Add a short subtitle describing the product in one line.
- Optional visual: clean screenshot thumbnail of the bot or Mini App in the corner.

Slide 2 - Context
- Clearly state:
  - who the end user is
  - what problem the product solves
  - the product idea in one short sentence
- Keep to 3 compact bullet points or equivalent visual blocks.

Slide 3 - Implementation
- Explain how the product was built.
- Separate Version 1 and Version 2 clearly.
- Mention backend, database, Telegram bot, Mini App, SingularityApp integration, and LLM parsing.
- Explicitly include which TA feedback points were addressed.
- Prefer a simple architecture diagram or two-column layout over long paragraphs.

Slide 4 - Demo
- This is the most important slide.
- Make the demo video the dominant element on the slide.
- Use the provided full demo video asset.
- Add a short caption like:
  "Version 2 demo: connect, sync, summaries, natural-language task actions, and ambiguity resolution."
- If possible, use a poster frame from the actual video showing the product in action.
- Keep any additional text minimal.

Slide 5 - Links
- Include:
  - GitHub repo link
  - deployed product link
- Add a QR code for each link.
- Make the links readable in PDF form.
- If the deployed link is not available, leave a clearly marked placeholder rather than fabricating one.

Output requirements:
- Produce the final result as a polished 5-slide deck content plan ready for direct generation.
- Favor concise bullets over paragraphs.
- Use wording that sounds like a real completed student project.
- Make the result presentation-ready, not an outline for later rewriting.
```
