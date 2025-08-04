# TechCrunch News Bot

A minimal Telegram bot built with Aiogram that fetches and delivers the latest news from [TechCrunch](https://techcrunch.com/) (or any other RSS/JSON feed) directly to your chat.  
It supports real-time subscription management, background updates, and a clean architecture for extending to other feeds.

## Features

- **RSS & JSON Feed support**  
  Works with both traditional RSS/Atom feeds and modern JSON Feed format.
- **Subscription management**  
  Users can enable or disable news delivery via inline buttons or `/settings` command.
- **Background polling**  
  Runs a periodic background task to check for new items and deliver them to subscribers.
- **Latest news on demand**  
  Use `/latest` to instantly get the most recent news without waiting for the next poll.
- **SQLite storage**  
  Keeps track of users, their subscription status, and last delivered article to avoid duplicates.
- **Error resilience**  
  Logs all exceptions and continues processing without interrupting the service.
