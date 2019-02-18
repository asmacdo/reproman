# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the reproman package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for run and jobs interfaces.
"""

import logging
from mock import patch
import os
import os.path as op

import pytest

from reproman.api import jobs
from reproman.api import run
from reproman.utils import chpwd
from reproman.utils import swallow_logs
from reproman.utils import swallow_outputs
from reproman.support.exceptions import ResourceNotFoundError
from reproman.tests import fixtures
from reproman.tests.utils import create_tree


# Tests that do not require a resource, registry, or orchestator.


@pytest.mark.parametrize("command", [None, []],
                         ids=["None", "[]"])
def test_run_no_command(command):
    with pytest.raises(ValueError) as exc:
        run(command=command)
    assert "No command" in str(exc)


def test_run_no_resource():
    with pytest.raises(ValueError) as exc:
        run(command="blahbert")
    assert "No resource" in str(exc)


def test_run_list():
    with swallow_outputs() as output:
        run(list_=True)
        assert "local" in output.out
        assert "plain" in output.out


# Tests that require `context`.


job_registry = fixtures.job_registry_fixture()
resource_manager = fixtures.resource_manager_fixture(scope="module")


@pytest.fixture(scope="function")
def context(tmpdir, resource_manager, job_registry):
    """Fixture that provides context for a test run.

    The return value is a dictionary with the following items:

    - run_fn: `interface.run`, patched so that it uses a local registry and
      temporary resource manager.

    - jobs_fn: `interface.jobs`, patched so that it uses the same local
      registry and resource manager as run_fn.

    - registry: a LocalRegistry instance.

    - directory: temporary path that is the current directory when run_fn is
      called.
    """
    path = str(tmpdir)

    # TODO: Use contextlib.ExitStack() for these nested with's once we drop py2
    # support.

    def run_fn(*args, **kwargs):
        with chpwd(path):
            # Patch home to avoid populating testing machine with jobs when
            # using local shell.
            with patch.dict(os.environ, {"HOME": path}):
                with patch("reproman.interface.run.get_manager",
                           return_value=resource_manager):
                    with patch("reproman.interface.run.LocalRegistry",
                               job_registry):
                        return run(*args, **kwargs)

    registry = job_registry()

    def jobs_fn(*args, **kwargs):
        with patch("reproman.interface.jobs.get_manager",
                   return_value=resource_manager):
            with patch("reproman.interface.jobs.LREG", registry):
                return jobs(*args, **kwargs)

    return {"directory": path,
            "registry": registry,
            "run_fn": run_fn,
            "jobs_fn": jobs_fn}


def test_run_resource_specification(context):
    path = context["directory"]
    run = context["run_fn"]

    create_tree(
        path,
        tree={"js0.yaml": "resource_name: name-via-js",
              "js1.yaml": ("resource_id: id-via-js\n"
                           "resource_name: name-via-js")})

    # Can specify name via job spec.
    with pytest.raises(ResourceNotFoundError) as exc:
        run(command=["doesnt", "matter"],
            job_specs=["js0.yaml"])
    assert "name-via-js" in str(exc)

    # If job spec as name and ID, ID takes precedence.
    with pytest.raises(ResourceNotFoundError) as exc:
        run(command=["doesnt", "matter"],
            job_specs=["js1.yaml"])
    assert "id-via-js" in str(exc)

    # Command-line overrides job spec.
    with pytest.raises(ResourceNotFoundError) as exc:
        run(command=["doesnt", "matter"], resref="fromcli",
            job_specs=["js1.yaml"])
    assert "fromcli" in str(exc)


def test_run_and_fetch(context):
    path = context["directory"]
    run = context["run_fn"]
    jobs = context["jobs_fn"]
    registry = context["registry"]

    create_tree(
        path,
        tree={"js0.yaml": ("resource_name: myshell\n"
                           "command_str: 'touch ok'\n"
                           "outputs: ['ok']")})

    run(job_specs=["js0.yaml"])

    with swallow_logs(new_level=logging.INFO) as log:
        with swallow_outputs() as output:
            jobs(queries=[], status=True)
            assert "myshell" in output.out
            assert len(registry.find_job_files()) == 1
            jobs(queries=[], action="fetch", all_=True)
            assert len(registry.find_job_files()) == 0
            jobs(queries=[], status=True)
            assert "No jobs" in log.out

    assert op.exists(op.join(path, "ok"))


def test_run_and_follow(context):
    path = context["directory"]
    run = context["run_fn"]
    jobs = context["jobs_fn"]
    registry = context["registry"]

    run(command=["touch", "ok"], outputs=["ok"], resref="myshell",
        follow=True)

    with swallow_logs(new_level=logging.INFO) as log:
        jobs(queries=[])
        assert len(registry.find_job_files()) == 0
        assert "No jobs" in log.out

    assert op.exists(op.join(path, "ok"))


def test_jobs_auto_fetch_with_query(context):
    path = context["directory"]
    run = context["run_fn"]
    jobs = context["jobs_fn"]
    registry = context["registry"]

    run(command=["touch", "ok"], outputs=["ok"], resref="myshell")

    jobfiles = registry.find_job_files()
    assert len(jobfiles) == 1
    jobid = list(jobfiles.keys())[0]
    with swallow_outputs():
        jobs(queries=[jobid[3:]])
    assert len(registry.find_job_files()) == 0
    assert op.exists(op.join(path, "ok"))


def test_jobs_query_unknown(context):
    run = context["run_fn"]
    jobs = context["jobs_fn"]
    registry = context["registry"]

    run(command=["doesntmatter"], resref="myshell")

    jobfiles = registry.find_job_files()
    assert len(jobfiles) == 1
    jobid = list(jobfiles.keys())[0]
    with swallow_logs(new_level=logging.WARNING) as log:
        jobs(queries=[jobid + "-trailing-garbage"])
        assert "No jobs matched" in log.out
    assert len(registry.find_job_files()) == 1


def test_jobs_delete(context):
    path = context["directory"]
    run = context["run_fn"]
    jobs = context["jobs_fn"]
    registry = context["registry"]

    run(command=["touch", "ok"], outputs=["ok"], resref="myshell")

    # Must explicit specify jobs to delete.
    with pytest.raises(ValueError):
        jobs(queries=[], action="delete")

    jobfiles = registry.find_job_files()
    assert len(jobfiles) == 1
    jobid = list(jobfiles.keys())[0]
    with swallow_outputs():
        jobs(queries=[jobid[3:]], action="delete")
    assert len(registry.find_job_files()) == 0
    assert not op.exists(op.join(path, "ok"))


def test_jobs_show(context):
    run = context["run_fn"]
    jobs = context["jobs_fn"]
    registry = context["registry"]

    run(command=["touch", "ok"], outputs=["ok"], resref="myshell")
    assert len(registry.find_job_files()) == 1

    with swallow_outputs() as output:
        jobs(queries=[], action="show", status=True)
        # `show`, as opposed to `list`, is detailed, multiline display.
        assert len(output.out.splitlines()) > 1
        assert "myshell" in output.out
        assert "status:" in output.out


def test_jobs_unknown_action(context):
    run = context["run_fn"]
    jobs = context["jobs_fn"]
    run(command=["doesntmatter"], resref="myshell")
    with pytest.raises(RuntimeError):
        jobs(queries=[], action="you don't know me")


def test_jobs_ambig_id_match(context):
    run = context["run_fn"]
    jobs = context["jobs_fn"]
    registry = context["registry"]

    run(command=["doesntmatter0"], resref="myshell")
    run(command=["doesntmatter1"], resref="myshell")

    jobfiles = registry.find_job_files()
    assert len(jobfiles) == 2
    jobid0, jobid1 = jobfiles.keys()

    # Start of ID is year, so first characters should be the same.
    assert jobid0[0] == jobid1[0], "test assumption is wrong"

    with pytest.raises(ValueError) as exc:
        jobs(queries=[jobid0[0], jobid1[0]])
    assert "matches multiple jobs" in str(exc)
