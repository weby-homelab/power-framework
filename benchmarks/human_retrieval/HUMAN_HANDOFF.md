# Передача M2-v2 незалежним оцінювачам

Використовуйте лише україномовні `annotation-packets/annotator-a-development.jsonl`
та `annotator-b-development.jsonl`. Обидва packets мають однакові чотири
кандидати на кожен запит і не містять назви режиму пошуку, source path,
hostname, персональних даних або sealed qrels.

Raw responses зберігайте **поза робочою копією** у restricted storage. Кожен
JSONL judgment містить лише `participant_id`, `query_id`, `document_id`,
`relevance` (`0`, `1`, `2`), `acceptable_citation` (`true` або `false`) і
`temporal_status` (`current`, `historical`, `not_applicable`). Окремих ручних
полів `abstention` або `taxonomy` у v2 немає.

Перед production обидва учасники незалежно проходять короткий calibration
packet. Production дозволяється лише після `compute_agreement.py
--protocol-version 2.0` і проходження preregistered gate. Після цього вони
незалежно оцінюють production packet; відповіді не обговорюються до створення
agreement receipt. Disagreement bundle передається третьому adjudicator лише
після production agreement. До retrieval координатор запускає
`validate_human_evidence.py`; sealed holdout залишається `do_not_open`.

Жоден pending-файл не є людським judgment, qrel, adjudication або release
claim. Frozen v1 не змінюється і не може задовольнити v2 calibration gate.
