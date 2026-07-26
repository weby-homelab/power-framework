# Known baseline failures

Nine baseline neural-determinism failures were skipped in the PR run and are
therefore unverified rather than counted as fixed. Their extended validation is
tracked in issue #187.

- `tests.test_neural_determinism.TestRerankedDeterminism::test_batch_1_and_8_same_top5[docker compose]`
- `tests.test_neural_determinism.TestRerankedDeterminism::test_batch_1_and_8_same_top5[gpg signing]`
- `tests.test_neural_determinism.TestRerankedDeterminism::test_batch_1_and_8_same_top5[power safety]`
- `tests.test_neural_determinism.TestRerankedDeterminism::test_batch_1_and_8_same_top5[tailscale vpn]`
- `tests.test_neural_determinism.TestSemanticDeterminism::test_all_queries_return_results`
- `tests.test_neural_determinism.TestSemanticDeterminism::test_in_process_repeats_produce_identical_top5[docker compose]`
- `tests.test_neural_determinism.TestSemanticDeterminism::test_in_process_repeats_produce_identical_top5[gpg signing]`
- `tests.test_neural_determinism.TestSemanticDeterminism::test_in_process_repeats_produce_identical_top5[power safety]`
- `tests.test_neural_determinism.TestSemanticDeterminism::test_in_process_repeats_produce_identical_top5[tailscale vpn]`
