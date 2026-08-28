from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    host = Path(sys.argv[1]).resolve()
    bundle = Path(sys.argv[2]).resolve()
    expected = "b8c4db7f3246d21c53a1b5633915be16bb84a633"
    os.chdir(host / "backend")
    sys.path.insert(0, str(host / "backend"))

    from app.cli import module_migrations
    from app.cli.modules import _environment_values, _installer
    from app.platform.modules import installer as installer_module
    from app.platform.modules.bundle import staged_ocp_bundle
    from app.platform.modules.discovery import FirstPartyModuleDiscovery
    from app.platform.modules.installer import installed_backend_distribution_paths

    actual = os.popen(f"git -C '{host}' rev-parse HEAD").read().strip()
    if actual != expected:
        raise SystemExit(f"Host contract mismatch: expected {expected}, got {actual}")

    class CutoverDiscovery(FirstPartyModuleDiscovery):
        def __init__(self) -> None:
            super().__init__({})

    # The pinned host rejects duplicate IDs before package verification. This
    # scoped substitution models the documented cutover without altering host code.
    installer_module.FirstPartyModuleDiscovery = CutoverDiscovery
    module_migrations.FirstPartyModuleDiscovery = CutoverDiscovery

    builtin_frontend = host / "frontend/frontend-modules/analysis-areas"
    parked_frontend = host / "frontend/.analysis-areas.builtin-contract-test"
    if parked_frontend.exists():
        raise SystemExit(f"Temporary cutover path already exists: {parked_frontend}")

    builtin_frontend.rename(parked_frontend)
    try:
        os.environ.update({"ENABLED_MODULES": "", "OCP_FRONTEND_MODULES": ""})
        with TemporaryDirectory(prefix="ocp-analysis-areas-contract-") as temporary:
            root = Path(temporary)
            installer = _installer(root)
            with staged_ocp_bundle(bundle) as (package_root, package):
                verified = installer.verify_installable(package_root)
                assert verified.bundle_sha256 == package.bundle_sha256
            with staged_ocp_bundle(bundle) as (package_root, _package):
                installed = installer.install(package_root)
            assert installed.enabled is False
            assert installer.enablement_environment().runtime_backend_paths == ""
            installed_paths = installed_backend_distribution_paths(root)
            assert len(installed_paths) == 1
            history = installed_paths[0] / "ocp_module_analysis_areas/migrations/history"
            assert (history / "20260814_0014_analysis_areas.py").is_file()
            assert (history / "20260818_0025_osm_external_links.py").is_file()
            assert installer.enable("analysis-areas").enabled is True
            frontend_environment = {
                **os.environ,
                **_environment_values(installer.enablement_environment()),
            }
            subprocess.run(
                ["corepack", "pnpm", "typecheck"],
                cwd=host / "frontend",
                env=frontend_environment,
                check=True,
            )
            assert installer.disable("analysis-areas").enabled is False
            assert history.is_dir()
            assert installer.enable("analysis-areas").enabled is True
            print(
                "host contract passed: verify, install-disabled, enable, disable, re-enable; "
                f"sha256={verified.bundle_sha256}"
            )
    finally:
        parked_frontend.rename(builtin_frontend)


if __name__ == "__main__":
    main()
