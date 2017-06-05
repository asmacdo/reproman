# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the niceman package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Support for Debian(-based) distribution(s)."""
import copy
import os
from datetime import datetime

import attr
import collections

import pytz
import yaml

from niceman import utils
from .base import Distribution

import logging

# ??? In principle apt is relevant only for tracing and here we are
#     trying to collect everything Debian related, so it might not event
#     need apt
try:
    import apt
    import apt.utils as apt_utils
    import apt_pkg
    # TODO this one operates locally and not within Session
    # So we would somehow need to point it inside the session
    # if possible...  probably not without pain.  If we could
    # "mount" that env then rootdir could be provided into Cache...
    # bleh
    apt_cache = apt.Cache()
except ImportError:
    apt = None
    apt_utils = None
    apt_pkg = None
    apt_cache = None

# Pick a conservative max command-line
try:
    _MAX_LEN_CMDLINE = os.sysconf(str("SC_ARG_MAX")) // 2
except (ValueError, AttributeError):
    _MAX_LEN_CMDLINE = 2048

# To parse output of dpkg-query
import re
_DPKG_QUERY_PARSER = re.compile(
    "(?P<name>[^:]+)(:(?P<architecture>[^:]+))?: (?P<path>.*)$"
)

from niceman.distributions.base import PackageTracer
from niceman.support.exceptions import CommandError

lgr = logging.getLogger('niceman.distributions.debian')

from .base import SpecObject
from .base import Package
from .base import Distribution
from .base import TypedList
from .base import _register_with_representer

#
# Models
#

# TODO: flyweight/singleton ?
@attr.s
class APTSource(SpecObject):
    """APT origin information
    """
    name = attr.ib()
    component = attr.ib(default=None)
    archive = attr.ib(default=None)
    architecture = attr.ib(default=None)
    codename = attr.ib(default=None)
    origin = attr.ib(default=None)
    label = attr.ib(default=None)
    site = attr.ib(default=None)
    archive_uri = attr.ib(default=None)
    date = attr.ib(default=None)
_register_with_representer(APTSource)


@attr.s
class DEBPackage(Package):
    """Debian package information"""
    name = attr.ib()
    # Optional
    source_name = attr.ib(default=None)
    upstream_name = attr.ib(default=None)

    version = attr.ib(default=None)
    architecture = attr.ib(default=None)
    size = attr.ib(default=None)
    md5 = attr.ib(default=None)
    sha1 = attr.ib(default=None)
    sha256 = attr.ib(default=None)
    source_version = attr.ib(default=None)
    versions = attr.ib(default=None)
    install_date = attr.ib(default=None)
    apt_sources = TypedList(APTSource)
    files = attr.ib(default=attr.Factory(list))  # Might want a File structure for advanced tracking
_register_with_representer(DEBPackage)


@attr.s
class DebianDistribution(Distribution):
    """
    Class to provide Debian-based shell commands.
    """

    apt_sources = TypedList(APTSource)
    packages = TypedList(DEBPackage)

    def initiate(self, session):
        """
        Perform any initialization commands needed in the environment environment.

        Parameters
        ----------
        environment : object
            The Environment sub-class object.
        """
        lgr.debug("Adding Debian update to environment command list.")
        session.add_command(['apt-get', 'update'])
        #session.add_command(['apt-get', 'install', '-y', 'python-pip'])
        # session.set_env(DEBIAN_FRONTEND='noninteractive', this_session_only=True)

    def install_packages(self, session, use_version=True):
        """
        Install the packages associated to this distribution by the provenance
        into the environment.

        Parameters
        ----------
        session : object
        use_version : bool, optional
          Use version information if provided.
          TODO: support outside or deprecate
            
        """
        package_specs = []

        for package in self._provenance.packages:
            package_spec = package.name
            if use_version and package.version:
                package_spec += '=%s' % package.version
            package_specs.append(package_spec)

        session.add_command(
            # TODO: Pull env out of provenance for this command.
            ['apt-get', 'install', '-y'] + package_specs,
            # env={'DEBIAN_FRONTEND': 'noninteractive'}
        )
_register_with_representer(DebianDistribution)


class DebTracer(PackageTracer):
    """.deb-based (and using apt and dpkg) systems package tracer
    """

    # TODO: (Low Priority) handle cases from dpkg-divert

    def identify_distributions(self, files):
        try:
            out, err = self._session.run('cat /etc/debian_version')
            out, err = self._session.run('ls -l /etc/apt')
        except Exception as exc:
            lgr.debug("Did not detect Debian: %s", exc)
            return
        yield DebianDistribution(name="debian")  # the one and only!

    # TODO: should become a part of "normalization" where common
    # stuff floats up
    def identify_package_origins(self, packages):
        used_names = set()  # Set to avoid duplicate origin names
        unnamed_origin_map = {}  # Map unnamed origins to named origins
        raise RuntimeError("should be RFed")
        # Iterate over all package origins
        for p in packages:
            for v in p.version_table:
                for i, o in enumerate(v.get("apt_sources", [])):
                    # If we haven't seen this origin before, generate a
                    # name for it
                    if o not in unnamed_origin_map:
                        unnamed_origin_map[o] = \
                            self._create_named_origin(o, used_names)
                    # Now replace the package origin with the name of the
                    # yaml-prepared origin
                    v["apt_sources"][i] = unnamed_origin_map[o].name

        # Sort the origins by the name for the configuration file
        origins = sorted(unnamed_origin_map.values(), key=lambda k: k.name)

        return origins

    @staticmethod
    def _create_named_origin(o, used_names):
        # Create a unique name for the origin
        name_fmt = "apt_%s_%s_%s_%%d" % (o.origin, o.archive,
                                         o.component)
        name = utils.generate_unique_name(name_fmt,
                                          used_names)
        # Remember the created name
        used_names.add(name)
        # Create a named origin
        new_o = copy.deepcopy(o)
        new_o.name = name
        return new_o

    @staticmethod
    def _parse_dpkgquery_line(line):
        if line.startswith('diversion '):
            return None  # we are ignoring diversion details ATM  TODO
        res = _DPKG_QUERY_PARSER.match(line)
        if res:
            res = res.groupdict()
            if res['architecture'] is None:
                res.pop('architecture')
        return res

    def _get_packagefields_for_files(self, files):
        file_to_package_dict = {}

        # Find out how many files we can query at once
        max_len = max([len(f) for f in files])
        num_files = max((_MAX_LEN_CMDLINE - 13) // (max_len + 1), 1)

        for subfiles in (files[pos:pos + num_files]
                         for pos in range(0, len(files), num_files)):
            try:
                out, err = self._session(
                    ['dpkg-query', '-S'] + subfiles,
                    expect_stderr=True, expect_fail=True
                )
            except CommandError as exc:
                stderr = utils.to_unicode(exc.stderr, "utf-8")
                if 'no path found matching pattern' in stderr:
                    out = exc.stdout  # One file not found, so continue
                else:
                    raise  # some other fault -- handle it above

            out = utils.to_unicode(out, "utf-8")

            # Now go through the output and assign packages to files
            for outline in out.splitlines():
                # Note, we must split after ": " instead of ":" in case the
                # package name includes an architecture (like "zlib1g:amd64")
                # TODO: Handle query of /bin/sh better
                outdict = self._parse_dpkgquery_line(outline)
                if not outdict:
                    lgr.debug("Skipping line %s", outline)
                    continue

                found_name = outdict.pop('path')
                if not found_name:
                    raise ValueError("Record %s got no path defined... skipping"  % repr(outdict))
                # for now let's just return those dicts of fields not actual
                # packages since then we would need create/kill them all the time
                # to merge files etc... although could also be a part of "normalization"
                pkg = outdict  # DEBPackage(**outdict)
                lgr.debug("Identified file %r to belong to package %s",
                          found_name, pkg)
                file_to_package_dict[found_name] = pkg

        return file_to_package_dict

    def _create_package(self, name, architecture=None):
        if not apt_cache:
            return None
        try:
            query = name if not architecture else "%s:%s" % (name, architecture)
            pkg_info = apt_cache[query]
        except KeyError:  # Package not found
            lgr.warning("Was asked to create a spec for package %s but it was not found in apt", name)
            return None

        # prep our pkg object:
        installed_info = pkg_info.installed
        if architecture and installed_info.architecture and architecture != installed_info.architecture:
            # should match or we whine a lot  and TODO: fail in the future after switching from apt module
            lgr.warning(
                "For package %s got different architecture %s != %s. Using installed for now",
                name, architecture, installed_info.architecture
            )

        pkg = DEBPackage(
            name=name,
            # type="dpkg"
            version=installed_info.version,
            # candidate=pkg_info.candidate.version
            size=installed_info.size,
            architecture=installed_info.architecture,
            md5=installed_info.md5,
            sha1=installed_info.sha1,
            sha256=installed_info.sha256
        )
        if installed_info.source_name:
            pkg.source_name = pkg_info.installed.source_name
            pkg.source_version = pkg_info.installed.source_version
        pkg.files = []

        # Now get installation date
        try:
            pkg.install_date = str(
                pytz.utc.localize(
                    datetime.utcfromtimestamp(
                        os.path.getmtime(
                            "/var/lib/dpkg/info/" + name + ".list"))))
        except OSError:  # file not found
            pass

        # Compile Version Table
        pkg_versions = []
        for v in pkg_info.versions:
            v_info = {"version": v.version}
            origins = []
            for (pf, _) in v._cand.file_list:
                # Get the archive uri
                indexfile = v.package._pcache._list.find_index(pf)
                if indexfile:
                    archive_uri = indexfile.archive_uri("")
                else:
                    archive_uri = None

                # TODO: shouldn't be done per each package since
                #       common within session for all packages from the
                #       same Packages.  So should be done independently
                #       and once per Packages file
                # Get the release date
                rdate = self._find_release_date(
                    self._find_release_file(pf.filename))

                # Pull origin information from package file
                origin = APTSource(name=None,
                                   component=pf.component,
                                   codename=pf.codename,
                                   archive=pf.archive,
                                   architecture=pf.architecture,
                                   origin=pf.origin,
                                   label=pf.label,
                                   site=pf.site,
                                   archive_uri=archive_uri,
                                   date=rdate)

                # Now add our crafted origin to the list
                origins.append(origin)
            v_info["apt_sources"] = origins
            pkg_versions.append(v_info)

        pkg.version_table = pkg_versions

        lgr.debug("Found package %s", pkg)
        return pkg

    @staticmethod
    def _find_release_file(packages_filename):
        # The release filename is a substring of the package
        # filename (excluding the ending "Release" or "InRelease"
        # The split between the release filename and the package filename
        # is at an underscore, so split the package filename
        # at underscores and test for the release file:
        rfprefix = packages_filename
        assert os.path.isabs(packages_filename), \
            "must be given full path, got %s" % packages_filename
        while "_" in rfprefix:
            rfprefix = rfprefix.rsplit("_", 1)[0]
            for ending in ['_InRelease', '_Release']:
                release_filename = rfprefix + ending
                if os.path.exists(release_filename):
                    return release_filename
        # No file found
        return None

    @staticmethod
    def _find_release_date(rfile):
        # Extract and format the date from the release file
        rdate = None
        if rfile:
            rdate = apt_utils.get_release_date_from_release_file(rfile)
            if rdate:
                rdate = str(pytz.utc.localize(
                    datetime.utcfromtimestamp(rdate)))
        return rdate

