import os
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from kpops.cli.pipeline_config import HelmConfig, PipelineConfig
from kpops.pipeline_deployer.streams_bootstrap.exception import ReleaseNotFoundException
from kpops.pipeline_deployer.streams_bootstrap.helm_wrapper import (
    HelmCommandConfig,
    HelmTemplate,
    HelmWrapper,
    load_helm_manifest,
)
from kpops.pipeline_deployer.streams_bootstrap.streams_bootstrap_application_type import (
    ApplicationType,
)

DEFAULTS_PATH = Path(__file__).parent / "resources"


class TestHelmWrapper:
    @pytest.fixture
    def helm_wrapper(self) -> HelmWrapper:
        config = PipelineConfig(
            defaults_path=DEFAULTS_PATH,
            environment="development",
            streams_bootstrap_helm_config=HelmConfig(
                repository_name="test-repository", url="fake"
            ),
        )
        helm_config = config.streams_bootstrap_helm_config
        helm_config.diff.enable = False
        return HelmWrapper(helm_config=helm_config)

    @pytest.fixture
    def helm_wrapper_with_tls_config(self) -> HelmWrapper:
        config = PipelineConfig(
            defaults_path=DEFAULTS_PATH,
            environment="development",
            streams_bootstrap_helm_config=HelmConfig(
                repository_name="test-repository",
                url="fake",
                ca_file=Path("a_file.ca"),
                insecure_skip_tls_verify=True,
            ),
        )
        helm_config = config.streams_bootstrap_helm_config
        helm_config.diff.enable = False
        return HelmWrapper(helm_config=helm_config)

    @pytest.fixture(autouse=True)
    def temp_file_mock(self, mocker: MockerFixture) -> MagicMock:
        temp_file_mock = mocker.patch("tempfile.NamedTemporaryFile")
        temp_file_mock.return_value.__enter__.return_value.name = "values.yaml"
        return temp_file_mock

    @pytest.fixture
    def run_command(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch.object(HelmWrapper, "_HelmWrapper__run_command")

    def test_should_call_run_command_method_when_helm_install_with_defaults(
        self, run_command: MagicMock
    ):
        config = PipelineConfig(defaults_path=DEFAULTS_PATH, environment="development")
        helm_wrapper = HelmWrapper(helm_config=config.streams_bootstrap_helm_config)

        helm_wrapper.helm_upgrade_install(
            release_name="test-release",
            namespace="test-namespace",
            values={"commandLine": "test"},
            app=ApplicationType.STREAMS_APP.value,
            dry_run=False,
        )
        run_command.assert_called_once_with(
            [
                "helm",
                "upgrade",
                "test-release",
                "bakdata-streams-bootstrap/streams-app",
                "--install",
                "--timeout=5m0s",
                "--namespace",
                "test-namespace",
                "--values",
                "values.yaml",
                "--wait",
            ],
            dry_run=False,
        )

    def test_should_include_configured_tls_parameters_on_add(
        self, helm_wrapper_with_tls_config: HelmWrapper, run_command: MagicMock
    ):
        helm_wrapper_with_tls_config.helm_repo_add()
        run_command.assert_has_calls(
            [
                mock.call(
                    [
                        "helm",
                        "repo",
                        "add",
                        "test-repository",
                        "fake",
                        "--ca-file",
                        "a_file.ca",
                        "--insecure-skip-tls-verify",
                    ],
                    dry_run=False,
                ),
                mock.call(
                    ["helm", "repo", "update"],
                    dry_run=False,
                ),
            ]
        )

    def test_should_include_configured_tls_parameters_on_update(
        self, helm_wrapper_with_tls_config: HelmWrapper, run_command: MagicMock
    ):

        helm_wrapper_with_tls_config.helm_upgrade_install(
            release_name="test-release",
            namespace="test-namespace",
            values={},
            app="test-chart",
            dry_run=False,
        )

        run_command.assert_called_once_with(
            [
                "helm",
                "upgrade",
                "test-release",
                "test-repository/test-chart",
                "--install",
                "--timeout=5m0s",
                "--namespace",
                "test-namespace",
                "--values",
                "values.yaml",
                "--ca-file",
                "a_file.ca",
                "--insecure-skip-tls-verify",
                "--wait",
            ],
            dry_run=False,
        )

    def test_should_call_helm_install_overriding_repo_and_chart(
        self, helm_wrapper: HelmWrapper, run_command: MagicMock
    ):
        helm_wrapper.helm_upgrade_install(
            release_name="test-release",
            namespace="test-namespace",
            values={"commandLine": "test"},
            app=ApplicationType.STREAMS_APP.value,
            dry_run=False,
            local_chart_path=Path("my/fake/dir/chart"),
        )
        run_command.assert_called_once_with(
            [
                "helm",
                "upgrade",
                "test-release",
                os.path.join("my", "fake", "dir", "chart"),
                "--install",
                "--timeout=5m0s",
                "--namespace",
                "test-namespace",
                "--values",
                "values.yaml",
                "--wait",
            ],
            dry_run=False,
        )

    def test_should_call_run_command_method_when_helm_install_with_non_defaults(
        self,
        helm_wrapper: HelmWrapper,
        run_command: MagicMock,
    ):
        helm_wrapper.helm_upgrade_install(
            release_name="test-release",
            namespace="test-namespace",
            values={"commandLine": "test"},
            app=ApplicationType.STREAMS_APP.value,
            dry_run=True,
            helm_command_config=HelmCommandConfig(
                debug=True,
                force=True,
                timeout="120s",
                wait=True,
                wait_for_jobs=True,
            ),
        )
        run_command.assert_called_once_with(
            [
                "helm",
                "upgrade",
                "test-release",
                "test-repository/streams-app",
                "--install",
                "--timeout=120s",
                "--namespace",
                "test-namespace",
                "--values",
                "values.yaml",
                "--dry-run",
                "--debug",
                "--force",
                "--wait",
                "--wait-for-jobs",
            ],
            dry_run=True,
        )

    def test_should_call_run_command_method_when_helm_install_with_non_defaults_from_env(
        self, helm_wrapper: HelmWrapper, run_command: MagicMock
    ):
        os.environ["HELM_COMMAND_CONFIG_debug"] = "True"
        os.environ["HELM_COMMAND_CONFIG_timeout"] = "130s"
        helm_wrapper.helm_upgrade_install(
            release_name="test-release",
            namespace="test-namespace",
            values={"commandLine": "test"},
            app=ApplicationType.STREAMS_APP.value,
            dry_run=True,
            helm_command_config=HelmCommandConfig(),
        )

        run_command.assert_called_once_with(
            [
                "helm",
                "upgrade",
                "test-release",
                "test-repository/streams-app",
                "--install",
                "--timeout=130s",
                "--namespace",
                "test-namespace",
                "--values",
                "values.yaml",
                "--dry-run",
                "--debug",
                "--wait",
            ],
            dry_run=True,
        )

    def test_should_call_run_command_method_when_uninstalling_streams_app(
        self, helm_wrapper: HelmWrapper, run_command: MagicMock
    ):
        helm_wrapper.helm_uninstall(
            namespace="test-namespace",
            release_name="test-release",
            dry_run=False,
        )
        run_command.assert_called_once_with(
            ["helm", "uninstall", "--namespace", "test-namespace", "test-release"],
            dry_run=False,
        )

    def test_should_call_run_command_method_when_installing_streams_app__with_dry_run(
        self,
        helm_wrapper: HelmWrapper,
        mocker: MockerFixture,
    ):
        config = PipelineConfig(defaults_path=DEFAULTS_PATH, environment="development")
        helm_wrapper = HelmWrapper(helm_config=config.streams_bootstrap_helm_config)

        run_command = mocker.patch.object(helm_wrapper, "_HelmWrapper__run_command")
        helm_wrapper.helm_uninstall(
            namespace="test-namespace",
            release_name="test-release",
            dry_run=True,
        )
        run_command.assert_called_once_with(
            [
                "helm",
                "uninstall",
                "--namespace",
                "test-namespace",
                "test-release",
                "--dry-run",
            ],
            dry_run=True,
        )

    def test_validate_console_output(self):
        with pytest.raises(RuntimeError):
            HelmWrapper.parse_helm_command_stderr_output(
                "A specific\n eRrOr was found in this line"
            )
        with pytest.raises(ReleaseNotFoundException):
            HelmWrapper.parse_helm_command_stderr_output(
                "New \nmessage\n ReLease: noT foUnD"
            )
        try:
            HelmWrapper.parse_helm_command_stderr_output(
                "This is \njust WaRnIng nothing more"
            )
        except RuntimeError as e:
            pytest.fail(
                f"validate_console_output() raised RuntimeError unexpectedly!\nError message: {e}"
            )
        try:
            HelmWrapper.parse_helm_command_stderr_output(
                "This is \njust WaRnIng nothing more"
            )
        except ReleaseNotFoundException:
            pytest.fail(
                f"validate_console_output() raised ReleaseNotFoundException unexpectedly!\nError message: {ReleaseNotFoundException}"
            )

    def test_trim_release_name_with_suffix(self, helm_wrapper: HelmWrapper):
        name = helm_wrapper.trim_release_name(
            "example-component-name-too-long-fake-fakefakefakefakefake", suffix="-clean"
        )
        assert name == "example-component-name-too-long-fake-fakefakefa-clean"
        assert len(name) == 53

    def test_diff(self, helm_wrapper: HelmWrapper):
        templates = [HelmTemplate("a.yaml", {})]
        assert helm_wrapper._helm_diff(templates, templates) == [
            (
                {},
                {},
            ),
        ]

        # test matching corresponding template files based on their filename
        assert helm_wrapper._helm_diff(
            [
                HelmTemplate("a.yaml", {"a": 1}),
                HelmTemplate("b.yaml", {"b": 1}),
            ],
            [
                HelmTemplate("a.yaml", {"a": 2}),
                HelmTemplate("c.yaml", {"c": 1}),
            ],
        ) == [
            (
                {"a": 1},
                {"a": 2},
            ),
            (
                {"b": 1},
                {},
            ),
            (
                {},
                {"c": 1},
            ),
        ]

        # test no current release
        assert helm_wrapper._helm_diff((), [HelmTemplate("a.yaml", {"a": 1})]) == [
            (
                {},
                {"a": 1},
            ),
        ]

    def test_load_manifest(self):
        stdout = """---
# Resource: chart/templates/test1.yaml
"""
        with pytest.raises(ValueError):
            helm_templates = list(load_helm_manifest(stdout))
            assert len(helm_templates) == 0

        stdout = """---
# Source: chart/templates/test2.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
    labels:
        foo: bar
"""

        helm_template = HelmTemplate.load("test2.yaml", stdout)
        assert helm_template.filepath == "test2.yaml"
        assert helm_template.template == {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {"labels": {"foo": "bar"}},
        }

        helm_templates = list(load_helm_manifest(stdout))
        assert len(helm_templates) == 1
        helm_template = helm_templates[0]
        assert isinstance(helm_template, HelmTemplate)
        assert helm_template.filepath == "chart/templates/test2.yaml"
        assert helm_template.template == {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {"labels": {"foo": "bar"}},
        }

        stdout = """---
# Source: chart/templates/test3a.yaml
data:
    - a: 1
    - b: 2
---
# Source: chart/templates/test3b.yaml
foo: bar
"""
        helm_templates = list(load_helm_manifest(stdout))
        assert len(helm_templates) == 2
        assert all(
            isinstance(helm_template, HelmTemplate) for helm_template in helm_templates
        )
        assert helm_templates[0].filepath == "chart/templates/test3a.yaml"
        assert helm_templates[0].template == {"data": [{"a": 1}, {"b": 2}]}
        assert helm_templates[1].filepath == "chart/templates/test3b.yaml"
        assert helm_templates[1].template == {"foo": "bar"}

        stdout = """Release "test" has been upgraded. Happy Helming!
NAME: test
LAST DEPLOYED: Wed Nov 23 16:37:17 2022
NAMESPACE: test-namespace
STATUS: pending-upgrade
REVISION: 8
TEST SUITE: None
HOOKS:
MANIFEST:
---
# Source: chart/templates/test3a.yaml
data:
    - a: 1
    - b: 2
---
# Source: chart/templates/test3b.yaml
foo: bar
"""
        helm_templates = list(load_helm_manifest(stdout))
        assert len(helm_templates) == 2
        assert all(
            isinstance(helm_template, HelmTemplate) for helm_template in helm_templates
        )
        assert helm_templates[0].filepath == "chart/templates/test3a.yaml"
        assert helm_templates[0].template == {"data": [{"a": 1}, {"b": 2}]}
        assert helm_templates[1].filepath == "chart/templates/test3b.yaml"
        assert helm_templates[1].template == {"foo": "bar"}

    def test_get_manifest(self, run_command: MagicMock):
        run_command.return_value = """Release "test-release" has been upgraded. Happy Helming!
NAME: test-release
---
# Source: chart/templates/test.yaml
data:
    - a: 1
    - b: 2
"""
        helm_templates = list(
            HelmWrapper._helm_get_manifest("test-release", "test-namespace")
        )
        run_command.assert_called_once_with(
            [
                "helm",
                "get",
                "manifest",
                "test-release",
                "--namespace",
                "test-namespace",
            ],
            dry_run=True,
        )
        assert len(helm_templates) == 1
        assert helm_templates[0].filepath == "chart/templates/test.yaml"
        assert helm_templates[0].template == {"data": [{"a": 1}, {"b": 2}]}

        run_command.side_effect = ReleaseNotFoundException()
        assert HelmWrapper._helm_get_manifest("test-release", "test-namespace") == ()

    def test_should_call_run_command_method_when_helm_uninstall_with_untrimmed_release_name(
        self, helm_wrapper: HelmWrapper, run_command: MagicMock
    ):
        helm_wrapper.helm_uninstall(
            namespace="test-namespace",
            release_name="long-name-which-indicates-trimming-this-trim-is-dirty-and-this-suffix-should-be-gone-after",
            dry_run=False,
            suffix="-clean",
        )
        run_command.assert_called_once_with(
            [
                "helm",
                "uninstall",
                "--namespace",
                "test-namespace",
                "long-name-which-indicates-trimming-this-trim-is-clean",
            ],
            dry_run=False,
        )

    def test_should_call_run_command_method_when_helm_install_with_untrimmed_release_name(
        self, helm_wrapper: HelmWrapper, run_command: MagicMock
    ):
        os.environ["HELM_COMMAND_CONFIG_debug"] = "True"
        os.environ["HELM_COMMAND_CONFIG_timeout"] = "130s"
        helm_wrapper.helm_upgrade_install(
            release_name="long-name-which-indicates-trimming-this-trim-is-dirty-and-this-suffix-should-be-gone-after",
            namespace="test-namespace",
            values={"commandLine": "test"},
            app=ApplicationType.STREAMS_APP.value,
            dry_run=True,
            suffix="-clean",
            helm_command_config=HelmCommandConfig(),
        )

        run_command.assert_called_once_with(
            [
                "helm",
                "upgrade",
                "long-name-which-indicates-trimming-this-trim-is-clean",
                "test-repository/streams-app",
                "--install",
                "--timeout=130s",
                "--namespace",
                "test-namespace",
                "--values",
                "values.yaml",
                "--dry-run",
                "--debug",
                "--wait",
            ],
            dry_run=True,
        )
