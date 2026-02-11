import os

# Root project folder
PROJECT_NAME = "social-poster"

# Folder structure
structure = {
    "": [
        "config.py",
        "main.py",
        "db.py",
        "scheduler.py",
        "poster.py",
        "requirements.txt",
        ".env.example",
        ".env",
        "README.md",
    ],
    "platforms": [
        "__init__.py",
        "base.py",
        "facebook.py",
        "instagram.py",
        "twitter.py",
        "youtube.py",
        "linkedin.py",
    ],
    "approval": [
        "__init__.py",
        "telegram_bot.py",
        "slack_bot.py",
    ],
    "media": [
        "__init__.py",
        "processor.py",
    ],
    "notifier": [
        "__init__.py",
        "alerts.py",
    ],
    "tests": [
        "__init__.py",
        "test_all.py",
        "test_db.py",
        "test_platforms.py",
        "test_telegram.py",
        "test_media.py",
        "test_poster.py",
    ],
    "data": [
        "posts.db",  # will just create empty file
    ],
    "data/media_cache": [],
    "logs": [
        "app.log",
    ],
}

def create_project():
    print(f"Creating project: {PROJECT_NAME}")
    os.makedirs(PROJECT_NAME, exist_ok=True)

    for folder, files in structure.items():
        folder_path = os.path.join(PROJECT_NAME, folder)
        os.makedirs(folder_path, exist_ok=True)

        for file in files:
            file_path = os.path.join(folder_path, file)

            # Create file if it doesn't exist
            if not os.path.exists(file_path):
                with open(file_path, "w", encoding="utf-8") as f:
                    if file.endswith(".py"):
                        f.write(f"# {file}\n")
                    elif file == "README.md":
                        f.write(f"# {PROJECT_NAME}\n")
                    else:
                        f.write("")
                print(f"Created: {file_path}")

    print("✅ Project structure created successfully!")

if __name__ == "__main__":
    create_project()
