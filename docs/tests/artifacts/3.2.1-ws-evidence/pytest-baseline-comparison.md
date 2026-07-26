# Pytest baseline comparison

## Baseline failed nodeids

- `tests.test_neural_determinism.TestRerankedDeterminism::test_batch_1_and_8_same_top5[docker compose]`
- `tests.test_neural_determinism.TestRerankedDeterminism::test_batch_1_and_8_same_top5[gpg signing]`
- `tests.test_neural_determinism.TestRerankedDeterminism::test_batch_1_and_8_same_top5[power safety]`
- `tests.test_neural_determinism.TestRerankedDeterminism::test_batch_1_and_8_same_top5[tailscale vpn]`
- `tests.test_neural_determinism.TestSemanticDeterminism::test_all_queries_return_results`
- `tests.test_neural_determinism.TestSemanticDeterminism::test_in_process_repeats_produce_identical_top5[docker compose]`
- `tests.test_neural_determinism.TestSemanticDeterminism::test_in_process_repeats_produce_identical_top5[gpg signing]`
- `tests.test_neural_determinism.TestSemanticDeterminism::test_in_process_repeats_produce_identical_top5[power safety]`
- `tests.test_neural_determinism.TestSemanticDeterminism::test_in_process_repeats_produce_identical_top5[tailscale vpn]`
- `tests.test_perf_optimizations.TestBoundedRerank::test_hybrid_reranked_uses_hermetic_reranker`

## PR failed nodeids

- None

## Executed fixed failures

- `tests.test_perf_optimizations.TestBoundedRerank::test_hybrid_reranked_uses_hermetic_reranker`

## Baseline failures skipped in the PR run (unverified)

- `tests.test_neural_determinism.TestRerankedDeterminism::test_batch_1_and_8_same_top5[docker compose]`
- `tests.test_neural_determinism.TestRerankedDeterminism::test_batch_1_and_8_same_top5[gpg signing]`
- `tests.test_neural_determinism.TestRerankedDeterminism::test_batch_1_and_8_same_top5[power safety]`
- `tests.test_neural_determinism.TestRerankedDeterminism::test_batch_1_and_8_same_top5[tailscale vpn]`
- `tests.test_neural_determinism.TestSemanticDeterminism::test_all_queries_return_results`
- `tests.test_neural_determinism.TestSemanticDeterminism::test_in_process_repeats_produce_identical_top5[docker compose]`
- `tests.test_neural_determinism.TestSemanticDeterminism::test_in_process_repeats_produce_identical_top5[gpg signing]`
- `tests.test_neural_determinism.TestSemanticDeterminism::test_in_process_repeats_produce_identical_top5[power safety]`
- `tests.test_neural_determinism.TestSemanticDeterminism::test_in_process_repeats_produce_identical_top5[tailscale vpn]`

## New failures

- None

## Common failures

- None
