"""Reject known CI hosts before Stage73 private file or Drive operations.

A negative result does not certify host isolation or durable storage.
"""
import os

CI_ENV_MARKERS = frozenset((
    "CI", "GITHUB_ACTIONS", "GITHUB_RUN_ID", "RUNNER_TEMP", "RUNNER_OS",
    "CIRCLECI", "GITLAB_CI", "GITLAB_RUNNER_ID", "BUILDKITE",
    "JENKINS_URL", "TF_BUILD", "TEAMCITY_VERSION",
    "BITBUCKET_BUILD_NUMBER", "DRONE", "TRAVIS", "APPVEYOR",
    "CODEBUILD_BUILD_ID", "SYSTEM_TEAMFOUNDATIONCOLLECTIONURI",
))


def is_known_ci_host(environ=None):
    variables = os.environ if environ is None else environ
    return any(variables.get(key, "") != "" for key in CI_ENV_MARKERS)
