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

## Fixed failures

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

## New failures

- None

## Common failures

- None
