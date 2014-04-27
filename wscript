# -*- Mode: python; py-indent-offset: 4; indent-tabs-mode: nil; coding: utf-8; -*-

"""
Copyright (c) 2014  Regents of the University of California,
                    Arizona Board of Regents,
                    Colorado State University,
                    University Pierre & Marie Curie, Sorbonne University,
                    Washington University in St. Louis,
                    Beijing Institute of Technology

This file is part of NFD (Named Data Networking Forwarding Daemon).
See AUTHORS.md for complete list of NFD authors and contributors.

NFD is free software: you can redistribute it and/or modify it under the terms
of the GNU General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version.

NFD is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
NFD, e.g., in COPYING.md file.  If not, see <http://www.gnu.org/licenses/>.
"""

import re

VERSION = re.search('^#define NFD_VERSION_STRING\\s+"(.*)"',
                    open("version.hpp").read(), re.M).group(1)
APPNAME = "nfd"
BUGREPORT = "http://redmine.named-data.net/projects/nfd"
URL = "https://github.com/named-data/NFD"

from waflib import Logs
import os

def options(opt):
    opt.load(['compiler_cxx', 'gnu_dirs'])
    opt.load(['boost', 'unix-socket', 'dependency-checker',
              'default-compiler-flags', 'coverage',
              'doxygen', 'sphinx_build'],
             tooldir=['.waf-tools'])

    nfdopt = opt.add_option_group('NFD Options')
    opt.addUnixOptions(nfdopt)
    opt.addDependencyOptions(nfdopt, 'libpcap')
    nfdopt.add_option('--without-libpcap', action='store_true', default=False,
                      dest='without_libpcap',
                      help='''Disable libpcap (Ethernet face support will be disabled)''')

    opt.addDependencyOptions(nfdopt, 'librt',     '(optional)')
    opt.addDependencyOptions(nfdopt, 'libresolv', '(optional)')

    nfdopt.add_option('--with-tests', action='store_true', default=False,
                      dest='with_tests', help='''Build unit tests''')
    nfdopt.add_option('--with-other-tests', action='store_true', default=False,
                      dest='with_other_tests', help='''Build other tests''')

def configure(conf):
    conf.load(['compiler_cxx', 'gnu_dirs',
               'default-compiler-flags',
               'boost', 'dependency-checker',
               'doxygen', 'sphinx_build'])

    conf.check_cfg(package='libndn-cxx', args=['--cflags', '--libs'],
                   uselib_store='NDN_CXX', mandatory=True)

    boost_libs = 'system chrono program_options'
    if conf.options.with_tests:
        conf.env['WITH_TESTS'] = 1
        conf.define('WITH_TESTS', 1);
        boost_libs += ' unit_test_framework'

    if conf.options.with_other_tests:
        conf.env['WITH_OTHER_TESTS'] = 1

    conf.check_boost(lib=boost_libs)

    if conf.env.BOOST_VERSION_NUMBER < 104800:
        Logs.error("Minimum required boost version is 1.48.0")
        Logs.error("Please upgrade your distribution or install custom boost libraries" +
                   " (http://redmine.named-data.net/projects/nfd/wiki/Boost_FAQ)")
        return

    conf.load('unix-socket')

    conf.checkDependency(name='librt', lib='rt', mandatory=False)
    conf.checkDependency(name='libresolv', lib='resolv', mandatory=False)
    if not conf.options.without_libpcap:
        conf.checkDependency(name='libpcap', lib='pcap', mandatory=True,
                             errmsg='not found, but required for Ethernet face support. '
                                    'Specify --without-libpcap to disable Ethernet face support.')

    conf.load('coverage')

    conf.find_program('bash', var='BASH')

    conf.define('DEFAULT_CONFIG_FILE', '%s/ndn/nfd.conf' % conf.env['SYSCONFDIR'])

    conf.write_config_header('config.hpp')

def build(bld):
    core = bld(
        target='core-objects',
        name='core-objects',
        features='cxx',
        source=bld.path.ant_glob(['core/**/*.cpp']),
        use='BOOST NDN_CXX LIBRT',
        includes='. core',
        export_includes='. core',
        )

    nfd_objects = bld(
        target='daemon-objects',
        name='daemon-objects',
        features='cxx',
        source=bld.path.ant_glob(['daemon/**/*.cpp'],
                                 excl=['daemon/face/ethernet-*.cpp',
                                       'daemon/face/unix-*.cpp',
                                       'daemon/main.cpp']),
        use='core-objects',
        includes='daemon',
        export_includes='daemon',
        )

    if bld.env['HAVE_LIBPCAP']:
        nfd_objects.source += bld.path.ant_glob('daemon/face/ethernet-*.cpp')
        nfd_objects.use += ' LIBPCAP'

    if bld.env['HAVE_UNIX_SOCKETS']:
        nfd_objects.source += bld.path.ant_glob('daemon/face/unix-*.cpp')

    bld(target='bin/nfd',
        features='cxx cxxprogram',
        source='daemon/main.cpp',
        use='daemon-objects',
        )

    rib_objects = bld(
        target='rib-objects',
        name='rib-objects',
        features='cxx',
        source=bld.path.ant_glob(['rib/**/*.cpp'],
                                 excl=['rib/main.cpp']),
        use='core-objects',
        )

    bld(target='bin/nrd',
        features='cxx cxxprogram',
        source='rib/main.cpp',
        use='rib-objects',
        )

    for app in bld.path.ant_glob('tools/*.cpp'):
        bld(features=['cxx', 'cxxprogram'],
            target='bin/%s' % (str(app.change_ext(''))),
            source=['tools/%s' % (str(app))],
            use='core-objects LIBRESOLV',
            )

    bld.recurse("tests")

    bld(features="subst",
        source='nfd.conf.sample.in',
        target='nfd.conf.sample',
        install_path="${SYSCONFDIR}/ndn",
        IF_HAVE_LIBPCAP="" if bld.env['HAVE_LIBPCAP'] else "; ")

    bld(features='subst',
        source='tools/nfd-status-http-server.py',
        target='bin/nfd-status-http-server',
        install_path="${BINDIR}",
        chmod=0755)

    if bld.env['SPHINX_BUILD']:
        bld(features="sphinx",
            builder="man",
            outdir="docs/manpages",
            config="docs/conf.py",
            source=bld.path.ant_glob('docs/manpages/**/*.rst'),
            install_path="${MANDIR}/",
            VERSION=VERSION)

    for script in bld.path.ant_glob('tools/*.sh'):
        bld(features='subst',
            source='tools/%s' % (str(script)),
            target='bin/%s' % (str(script.change_ext(''))),
            install_path="${BINDIR}",
            chmod=0755)

def docs(bld):
    from waflib import Options
    Options.commands = ['doxygen', 'sphinx'] + Options.commands

def doxygen(bld):
    if not bld.env.DOXYGEN:
        Logs.error("ERROR: cannot build documentation (`doxygen' is not found in $PATH)")
    else:
        bld(features="subst",
            name="doxygen-conf",
            source="docs/doxygen.conf.in",
            target="docs/doxygen.conf",
            VERSION=VERSION,
            )

        bld(features="doxygen",
            doxyfile='docs/doxygen.conf',
            use="doxygen-conf")

def sphinx(bld):
    if not bld.env.SPHINX_BUILD:
        bld.fatal("ERROR: cannot build documentation (`sphinx-build' is not found in $PATH)")
    else:
        bld(features="sphinx",
            outdir="docs",
            source=bld.path.ant_glob('docs/**/*.rst'),
            config="docs/conf.py",
            VERSION=VERSION)
