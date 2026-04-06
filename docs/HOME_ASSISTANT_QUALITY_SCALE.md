# Home Assistant quality scale and beta releases

Official references (update URLs if docs move):

- [Integration quality scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
- [Quality scale checklist](https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist/)

## Maintaining `quality_scale.yaml`

When you upgrade the minimum Home Assistant version (see [`hacs.json`](../hacs.json) and [`manifest.json`](../custom_components/washreminder/manifest.json)) or when a new HA major/beta cycle lands:

1. Open the **checklist** link above and scan for new or renamed rules.
2. Diff those expectations against [`custom_components/washreminder/quality_scale.yaml`](../custom_components/washreminder/quality_scale.yaml).
3. Update rule status (`done`, `todo`, `exempt`) and comments; adjust [`manifest.json`](../custom_components/washreminder/manifest.json) `quality_scale` only when the integration truly meets that tier.

The manifest `quality_scale` value is what you claim to users; the YAML file tracks detailed rule compliance.

## CI: stable vs pre-release Home Assistant

[`.github/workflows/validate.yaml`](../.github/workflows/validate.yaml) runs pytest twice:

- **stable** — installs from [`requirements_test.txt`](../requirements_test.txt) (pinned minimum versions).
- **beta** — installs the latest **pre-release** `homeassistant` and `pytest-homeassistant-custom-component` from PyPI so API drift surfaces early.

If the beta job fails because no compatible pre-releases exist yet, relax the beta pin or temporarily allow the job to fail until upstream publishes matching wheels.
