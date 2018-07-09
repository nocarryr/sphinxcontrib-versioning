"""Common objects used throughout the project."""

import atexit
import functools
import logging
import os
import shutil
import tempfile
import weakref
import textwrap
import shlex
import subprocess
import venv

import click


class Config(object):
    """The global configuration and state of the running program."""

    def __init__(self):
        """Constructor."""
        self._already_set = set()
        self._program_state = dict()

        # Booleans.
        self.banner_greatest_tag = False
        self.banner_recent_tag = False
        self.greatest_tag = False
        self.invert = False
        self.no_colors = False
        self.no_local_conf = False
        self.recent_tag = False
        self.show_banner = False

        # Strings.
        self.banner_main_ref = 'master'
        self.chdir = None
        self.git_root = None
        self.local_conf = None
        self.priority = None
        self.push_remote = 'origin'
        self.root_ref = 'master'

        # Tuples.
        self.grm_exclude = tuple()
        self.overflow = tuple()
        self.sort = tuple()
        self.whitelist_branches = tuple()
        self.whitelist_tags = tuple()

        # Integers.
        self.verbose = 0

    def __contains__(self, item):
        """Implement 'key in Config'.

        :param str item: Key to search for.

        :return: If item in self._program_state.
        :rtype: bool
        """
        return item in self._program_state

    def __iter__(self):
        """Yield names and current values of attributes that can be set from Sphinx config files."""
        for name in (n for n in dir(self) if not n.startswith('_') and not callable(getattr(self, n))):
            yield name, getattr(self, name)

    def __repr__(self):
        """Class representation."""
        attributes = ('_program_state', 'verbose', 'root_ref', 'overflow')
        key_value_attrs = ', '.join('{}={}'.format(a, repr(getattr(self, a))) for a in attributes)
        return '<{}.{} {}>'.format(self.__class__.__module__, self.__class__.__name__, key_value_attrs)

    def __setitem__(self, key, value):
        """Implement Config[key] = value, updates self._program_state.

        :param str key: Key to set in self._program_state.
        :param value: Value to set in self._program_state.
        """
        self._program_state[key] = value

    @classmethod
    def from_context(cls):
        """Retrieve this class' instance from the current Click context.

        :return: Instance of this class.
        :rtype: Config
        """
        try:
            ctx = click.get_current_context()
        except RuntimeError:
            return cls()
        return ctx.find_object(cls)

    def pop(self, *args):
        """Pop item from self._program_state.

        :param iter args: Passed to self._program_state.

        :return: Object from self._program_state.pop().
        """
        return self._program_state.pop(*args)

    def update(self, params, ignore_set=False, overwrite=False):
        """Set instance values from dictionary.

        :param dict params: Click context params.
        :param bool ignore_set: Skip already-set values instead of raising AttributeError.
        :param bool overwrite: Allow overwriting already-set values.
        """
        log = logging.getLogger(__name__)
        valid = {i[0] for i in self}
        for key, value in params.items():
            if not hasattr(self, key):
                raise AttributeError("'{}' object has no attribute '{}'".format(self.__class__.__name__, key))
            if key not in valid:
                message = "'{}' object does not support item assignment on '{}'"
                raise AttributeError(message.format(self.__class__.__name__, key))
            if key in self._already_set:
                if ignore_set:
                    log.debug('%s already set in config, skipping.', key)
                    continue
                if not overwrite:
                    message = "'{}' object does not support item re-assignment on '{}'"
                    raise AttributeError(message.format(self.__class__.__name__, key))
            setattr(self, key, value)
            self._already_set.add(key)


class HandledError(click.ClickException):
    """Abort the program."""

    def __init__(self):
        """Constructor."""
        super(HandledError, self).__init__(None)

    def show(self, **_):
        """Error messages should be logged before raising this exception."""
        logging.critical('Failure.')


class TempDir(object):
    """Similar to TemporaryDirectory in Python 3.x but with tuned weakref implementation."""

    def __init__(self, defer_atexit=False):
        """Constructor.

        :param bool defer_atexit: cleanup() to atexit instead of after garbage collection.
        """
        self.name = tempfile.mkdtemp('sphinxcontrib_versioning')
        if defer_atexit:
            atexit.register(shutil.rmtree, self.name, True)
            return
        try:
            weakref.finalize(self, shutil.rmtree, self.name, True)
        except AttributeError:
            weakref.proxy(self, functools.partial(shutil.rmtree, self.name, True))

    def __enter__(self):
        """Return directory path."""
        return self.name

    def __exit__(self, *_):
        """Cleanup when exiting context."""
        self.cleanup()

    def cleanup(self):
        """Recursively delete directory."""
        shutil.rmtree(self.name, onerror=lambda *a: os.chmod(a[1], __import__('stat').S_IWRITE) or os.unlink(a[1]))
        if os.path.exists(self.name):
            raise IOError(17, "File exists: '{}'".format(self.name))

def _version_from_setup_py(script_name):
    cmd_str = 'python {} --version'.format(script_name)
    r = subprocess.check_output(shlex.split(cmd_str), stderr=subprocess.STDOUT)
    if isinstance(r, bytes):
        r = r.decode('UTF-8')
    lines = r.splitlines()
    normalized_version = lines[-1]
    if len(lines) == 1 or 'Normalizing' not in lines[0]:
        return normalized_version, normalized_version

    str_version = lines[0].split('Normalizing')[1].split(' to ')[0]
    if '"' in str_version:
        str_version = str_version.strip('"')
    if "'" in str_version:
        str_version = str_version.strip("'")
    return normalized_version, str_version

def _name_from_setup_py(script_name):
    cmd_str = 'python {} --name'.format(script_name)
    r = subprocess.check_output(shlex.split(cmd_str))
    if isinstance(r, bytes):
        r = r.decode('UTF-8')
    return r.splitlines()[0]

class EnvBuilder(venv.EnvBuilder):
    ACTIVATE_THIS = textwrap.dedent("""\
        try:
            __file__
        except NameError:
            raise AssertionError(
                "You must run this like execfile('path/to/activate_this.py', dict(__file__='path/to/activate_this.py'))")
        import sys
        import os

        old_os_path = os.environ.get('PATH', '')
        os.environ['PATH'] = os.path.dirname(os.path.abspath(__file__)) + os.pathsep + old_os_path
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if sys.platform == 'win32':
            site_packages = os.path.join(base, 'Lib', 'site-packages')
        else:
            site_packages = os.path.join(base, 'lib', 'python%s' % sys.version[:3], 'site-packages')
        prev_sys_path = list(sys.path)
        import site
        site.addsitedir(site_packages)
        sys.real_prefix = sys.prefix
        sys.prefix = base
        # Move the added items to the front of the path:
        new_sys_path = []
        for item in list(sys.path):
            if item not in prev_sys_path:
                new_sys_path.append(item)
                sys.path.remove(item)
        sys.path[:0] = new_sys_path
    """)
    def create(self, env_dir):
        super(EnvBuilder, self).create(env_dir)
        context = self.__context
        self.__context = None
        return context
    def post_setup(self, context):
        activate_this = os.path.join(context.bin_path, 'activate_this.py')
        with open(activate_this, 'w') as f:
            f.write(self.ACTIVATE_THIS)
        self.__context = context

class TempEnv(TempDir):
    def __init__(self, defer_atexit=False):
        self.name = tempfile.mkdtemp('sphinxcontrib_versioning')
        self.venv_path = os.path.join(self.name, 'venv')
        self.venv_builder = EnvBuilder()
        self.context = self.venv_builder.create(self.venv_path)
        self.editable_installs = {}
    @property
    def env_exe(self):
        return self.context.env_exe
    @property
    def bin_path(self):
        return self.context.bin_path
    def run_python(self, cmd_str):
        cmd_str = '{self.env_exe} {cmd_str}'.format(self=self, cmd_str=cmd_str)
        r = subprocess.check_output(shlex.split(cmd_str))
        if isinstance(r, bytes):
            r = r.decode('UTF-8')
        return r
    def pip_install(self, *requirements):
        requirements = ' '.join(requirements)
        cmd_str = '-m pip install {}'.format(requirements)
        r = self.run_python(cmd_str)
        return r
    def pip_install_editable(self, path):
        if os.path.basename(path) != 'setup.py':
            script_name = os.path.join(path, 'setup.py')
        else:
            script_name = path
            path = os.path.dirname(script_name)
        if not os.path.exists(script_name):
            print('no script_name for {}'.format(path))
            return None
        pkg_name = _name_from_setup_py(script_name)
        self.uninstall_editable(pkg_name)

        cmd_str = '-m pip install -e {}'.format(path)
        r = self.run_python(cmd_str)
        self.editable_installs[pkg_name] = script_name
        return pkg_name
    def uninstall_editable(self, pkg_name):
        cmd_str = '-m pip uninstall -y {}'.format(pkg_name)
        r = self.run_python(cmd_str)
        if pkg_name in self.editable_installs:
            del self.editable_installs[pkg_name]
    def clone_local_env(self):
        requirements = self.get_local_requirements()
        print('detected packages: {}'.format(requirements))
        r = self.pip_install(*requirements)
        print(r)
    @classmethod
    def get_local_requirements(cls):
        cmd_str = 'pip freeze --local --exclude-editable'
        r = subprocess.check_output(shlex.split(cmd_str))
        if isinstance(r, bytes):
            r = r.decode('UTF-8')
        return r.splitlines()
    def __enter__(self):
        return self
    def __str__(self):
        return self.name
