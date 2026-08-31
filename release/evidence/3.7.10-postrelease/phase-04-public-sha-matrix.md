# Public SHA-256 matrix

Fresh public Release downloads were compared with the GitHub asset API digest,
the public `SHA256SUMS` file, the published manifest, and the published receipt.
The API digest is recorded with the `sha256:` prefix; file hashes use bare
lowercase SHA-256 values.

| Asset | Download | GitHub API | SHA256SUMS | Manifest/receipt | Result |
| --- | --- | --- | --- | --- | --- |
| `SHA256SUMS` | `7eebb361d0c54a9c8f375a1bd2294b2a6fd1aa4af40ddd9b6771ee3d8268d0af` | `sha256:7eebb361d0c54a9c8f375a1bd2294b2a6fd1aa4af40ddd9b6771ee3d8268d0af` | n/a | n/a | PASS |
| `power-framework-3.7.10.spdx.json` | `c2c86216d62676da88e6178794309cd8cc9daffc3d2267973700ece04523df3e` | `sha256:c2c86216d62676da88e6178794309cd8cc9daffc3d2267973700ece04523df3e` | match | match | PASS |
| `power-framework.release-baseline.json` | `2f3dfa0eeae38ac8a6724fe90d84a7886fd65bf3f16a4cc5efed6d603ff49032` | `sha256:2f3dfa0eeae38ac8a6724fe90d84a7886fd65bf3f16a4cc5efed6d603ff49032` | match | receipt match | PASS |
| `power-framework.release-receipt.json` | `7faec4376fcaaf70a075c00b84e146d22820cfb6dfb2f08183bb62d278163abe` | `sha256:7faec4376fcaaf70a075c00b84e146d22820cfb6dfb2f08183bb62d278163abe` | n/a | self-binding n/a | PASS |
| `power-profile-acceptance.json` | `83af86ed2a3db0e6b836ca8efded9638ad1a1e22ed964f0d9662fd0c78d9bbf7` | `sha256:83af86ed2a3db0e6b836ca8efded9638ad1a1e22ed964f0d9662fd0c78d9bbf7` | match | match | PASS |
| `power-release-manifest.json` | `1aac24ee51e6f1f36a313bbca932fd8fe77abbbdc7b0835174df05bfdc4527f4` | `sha256:1aac24ee51e6f1f36a313bbca932fd8fe77abbbdc7b0835174df05bfdc4527f4` | match | receipt match | PASS |
| `power-web-3.7.10.spdx.json` | `0bab3337f62a0a46741f9b85cd2c8119e43be9f641cc89101abc0dd6c04fdefb` | `sha256:0bab3337f62a0a46741f9b85cd2c8119e43be9f641cc89101abc0dd6c04fdefb` | match | match | PASS |
| `power_framework-3.7.10-py3-none-any.whl` | `f06592d63a7b1176890d5d69f9f9031955f1b78dd020994c3f43e239c54bdda2` | `sha256:f06592d63a7b1176890d5d69f9f9031955f1b78dd020994c3f43e239c54bdda2` | match | match | PASS |
| `power_framework-3.7.10.tar.gz` | `4b828a7cb99fcaa704675cce5d94b20462205b46d9dadb0d628002c5770d1bae` | `sha256:4b828a7cb99fcaa704675cce5d94b20462205b46d9dadb0d628002c5770d1bae` | match | match | PASS |
