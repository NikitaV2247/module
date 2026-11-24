# Branch Protection Rules для ветки `main`

Настройки репозитория (Settings → Branches → Add branch protection rule),
действуют с 04.11.2026. Соответствуют требованиям Этапа 1 (Задача 2).

| Параметр | Значение |
|---|---|
| Branch name pattern | `main` |
| Require a pull request before merging | ✅ включено |
| Require approvals | 1 ревьюер (план: 2 с следующего спринта) |
| Dismiss stale pull request approvals on new pushes | ✅ |
| Require review from Code Owners | ✅ (CODEOWNERS: тимлид) |
| Require status checks to pass | ✅ — job `lint` (black/isort/flake8) и job `test` (pytest + покрытие) |
| Require branches to be up to date | ✅ |
| Require conversation resolution | ✅ — все замечания ревью закрыты до merge |
| Restrict pushes that create matching branches | ❌ прямой push в `main` запрещён всем |
| Include administrators | ✅ — правила действуют и для тимлида |
| Allow force pushes / deletions | ❌ запрещено |

## Порядок слияния

1. Разработчик ведёт ветку `feature/ISSUE-ID-short-name`.
2. Открывает Pull Request по шаблону (описание, Issue, тесты, скриншоты).
3. CI обязан пройти (обе джобы зелёные).
4. Ревьюер даёт минимум 2 замечания, разработчик вносит правки,
   замечания закрываются (Resolve conversation).
5. Approve → кнопка Merge активна → merge --no-ff в `main`.
6. Ветка удаляется автоматически; Issue закрывается по `Closes #N`.

## Milestones

- **v0.1.0 — Первый релиз** (04.11.2026): 28/28 задач закрыто, тег `v0.1.0`.
- **v0.5.0 — Автогенерация** (12.11.2026): `run_auto_week` + seed, 142 теста.
- **v0.6.0** (12.11.2026): пункты 7/8 меню объединены, 145 тестов.
- **v0.7.0 — Звонки по дням** (12.11.2026): сетки звонков из учебного плана, 171 тест.
- **v0.7.1** (12.11.2026): пункт 5 меню — экспорт недели группы в PDF, 175 тестов.
- **v0.7.2 — Преподаватели** (15.11.2026): один преподаватель на дисциплину, 195 тестов.
- **v0.7.3 — CI** (17.11.2026): смоук на «4-1П9», teacher-конфликты в конвейере, 150 тестов.

См. также: docs/img/branch_protection.png (скриншот настроек).
