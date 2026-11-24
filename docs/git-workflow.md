# Порядок работы с Git в команде

## Модель ветвления

Проект использует простую модель **feature-веток**:

```
main                 — стабильная ветка, только проверенный код
└── feature/<имя>    — ветка конкретной задачи (создаётся от main)
```

## Правила

1. Тимлид создаёт репозиторий на GitHub и приглашает участников
   (Settings → Collaborators → Add people). Права: Разработчик —
   write, Тестировщик — write.
2. Каждая задача выполняется в отдельной ветке:
   `git checkout -b feature/schedule-generator`
3. Имя ветки — по шаблону `feature/task-name` (kebab-case).
4. Коммиты оформляются по стандарту Conventional Commits:
   - `feat:` — новая функциональность;
   - `fix:` — исправление ошибки;
   - `test:` — тесты;
   - `docs:` — документация;
   - `chore:` — служебные изменения.
   Пример: `feat: add user authorization stub`.
5. Перед слиянием ветки тестировщик запускает `pytest -v`;
   слияние в main выполняет тимлид через Pull Request (или
   `git merge --no-ff`).
6. Служебные файлы исключаются через `.gitignore`.

## Сценарий первой итерации (Задача 3 задания)

```bash
# 1. Тимлид: подготовка
git init -b main
git add README.md .gitignore requirements.txt
git commit -m "chore: initialize project structure"

# 2. Разработчик: задача из To Do
git checkout -b feature/schedule-generator
# ... реализация ...
git add src/generator.py
git commit -m "feat: add schedule generator with group and day queries"

# 3. Отправка ветки в общий репозиторий
git push -u origin feature/schedule-generator

# 4. Тимлид: проверка и слияние
git checkout main
git merge --no-ff feature/schedule-generator -m "merge: feature/schedule-generator"
git push origin main
```

## История проекта

Просмотр истории: `git log --graph --oneline --all`.
