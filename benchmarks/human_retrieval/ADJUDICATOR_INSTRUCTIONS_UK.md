# Інструкція adjudicator C для M2-v2

Ви отримуєте лише de-identified пари, де оцінювачі A і B розійшлися. Ви не
бачите зайвих відповідей, source path або назви режиму пошуку.

Для кожної розбіжності прочитайте запитання й документ та виберіть остаточні:

- `relevance`: `2` — прямо відповідає, `1` — лише пов'язаний, `0` — не допомагає;
- `acceptable_citation`: `true` лише для прямої відповіді (`relevance=2`),
  інакше `false`;
- `temporal_status`: `current`, `historical` або `not_applicable` за явним
  статусом у тексті.

Додайте одну коротку причину: `relevance`, `citation`, `temporal` або `other`.
Не змінюйте й не переписуйте початкові judgments A/B. Якщо pair неможливо
однозначно вирішити з packet, позначте її координатору як `needs_review`; не
вигадуйте зовнішній факт.

Фінальний v2 qrel містить лише `query_id`, `document_id` і `final` з трьома
полями вище та reason. Полів `taxonomy` і ручного `abstention` у v2 немає.
